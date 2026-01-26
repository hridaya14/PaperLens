import asyncio
import logging
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

logger = logging.getLogger(__name__)


class NIMEmbeddingsClient:
    """
    Client for NVIDIA NIM embedding models using OpenAI-compatible API.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        model: str = "nvidia/llama-3.2-nemoretriever-1b-vlm-embed-v1",
        embedding_dim: Optional[int] = None,
        max_workers: int = 4,
    ):
        """
        :param api_key: NVIDIA API key
        :param base_url: NVIDIA NIM base URL
        :param model: Embedding model name
        :param embedding_dim: Optional sanity check
        :param max_workers: Thread pool size for async compatibility
        """
        self.model = model
        self.embedding_dim = embedding_dim

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        logger.info("NVIDIA NIM embeddings client initialized")

    # Internal sync call
    def _embed_sync(
        self,
        inputs: List[str],
        input_type: str,
    ) -> List[List[float]]:
        response = self.client.embeddings.create(
            model=self.model,
            input=inputs,
            encoding_format="float",
            extra_body={
              "modality": ["text"] * len(inputs),
              "input_type": input_type,
              "truncate": "NONE",
            },
        )

        embeddings = [item.embedding for item in response.data]

        if self.embedding_dim is not None:
            for emb in embeddings:
                if len(emb) != self.embedding_dim:
                    raise ValueError(
                        f"Expected embedding dim {self.embedding_dim}, got {len(emb)}"
                    )

        return embeddings

    # Public async APIs
    async def embed_passages(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> List[List[float]]:
        """
        Embed text passages for indexing.
        """
        loop = asyncio.get_running_loop()
        embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            try:
                batch_embeddings = await loop.run_in_executor(
                    self.executor,
                    self._embed_sync,
                    batch,
                    "passage",
                )
                embeddings.extend(batch_embeddings)

                logger.debug(f"Embedded batch of {len(batch)} passages")

            except Exception as e:
                logger.error(f"Error embedding passages: {e}")
                raise

        logger.info(f"Successfully embedded {len(texts)} passages")
        return embeddings

    async def embed_query(self, query: str) -> List[float]:
        """
        Embed a search query.
        """
        loop = asyncio.get_running_loop()

        try:
            embedding = await loop.run_in_executor(
                self.executor,
                self._embed_sync,
                [query],
                "query",
            )
            return embedding[0]

        except Exception as e:
            logger.error(f"Error embedding query: {e}")
            raise

    # Lifecycle
    async def close(self):
        self.executor.shutdown(wait=False)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

