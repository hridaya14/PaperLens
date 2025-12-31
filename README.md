<!-- Improved compatibility of back to top link: See: https://github.com/othneildrew/Best-README-Template/pull/73 -->

<a id="readme-top"></a>

<!-- PROJECT SHIELDS -->

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![Unlicense License][license-shield]][license-url]
[![LinkedIn][linkedin-shield]][linkedin-url]

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/othneildrew/Best-README-Template">
    <img src="images/logo.png" alt="Logo" width="80" height="80">
  </a>

  <h3 align="center">PaperLens</h3>

  <p align="center">
    A Research Paper Curation & Retrieval-Augmented Generation (RAG) Platform!
    <br />
    <a href="https://github.com/othneildrew/Best-README-Template"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/othneildrew/Best-README-Template">View Demo</a>
    &middot;
    <a href="https://github.com/othneildrew/Best-README-Template/issues/new?labels=bug&template=bug-report---.md">Report Bug</a>
    &middot;
    <a href="https://github.com/othneildrew/Best-README-Template/issues/new?labels=enhancement&template=feature-request---.md">Request Feature</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->

## About The Project

[![Product][product-screenshot]](https://example.com)

**PaperLens** is an open-source, research-oriented system designed to help researchers **ingest, organize, read, and query scientific papers at scale**.

The platform automatically fetches papers from **arXiv**, indexes them using semantic embeddings, and enables **hallucination-minimized, paper-grounded LLM responses** through a modular RAG architecture.

PaperLens is built to support **ongoing research workflows**, not just one-off Q&A:

- Continuous paper ingestion
- Category-wise organization
- Retrieval grounded strictly in paper content
- Extensible, production-ready backend design

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

- [![FastAPI][FastAPI]][FastAPI-url]
- [![Streamlit][Streamlit]][Streamlit-url]
- [![Apache Airflow][Airflow]][Airflow-url]
- [![OpenSearch][OpenSearch]][OpenSearch-url]
- [![Docker][Docker]][Docker-url]
- [![Jina AI][Jina]][Jina-url]
- [![OpenAI][OpenAI]][OpenAI-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->

## Getting Started

### Prerequisites

- Docker Desktop (with Docker Compose)
- Python 3.12+
- `uv` package manager: https://docs.astral.sh/uv/
- 8GB+ RAM, 20GB+ free disk space

---

### Setup

```bash
# 1. Clone the repository
git clone <repository-url>
cd PaperLens
```

```bash
# 2. Configure environment variables
cp .env.example .env
# Add:
# - Jina AI embeddings API key
# - OpenAI-compatible LLM API key
```

```bash
# 3. Install dependencies (for development)
uv sync
```

```bash
# 4. Start all services
docker compose up --build -d
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE EXAMPLES -->

## Usage

Use this space to show useful examples of how a project can be used. Additional screenshots, code examples and demos work well in this space. You may also link to more resources.

_For more examples, please refer to the [Documentation](https://example.com)_

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ROADMAP -->

## Roadmap

### Implemented

- [x] Automated arXiv paper ingestion using Airflow
- [x] Semantic indexing with OpenSearch and Jina AI embeddings
- [x] Modular, model-agnostic LLM generation layer
- [x] Streamlit-based paper reading and RAG UI
- [x] Fully dockerized, one-command setup

### Planned

- [ ] **Redis caching** for faster retrieval and response times
- [ ] **Category-based paper repository UI**
- [ ] **Paper-specific RAG** (single-paper querying, NotebookLM-style)
- [ ] **Daily paper ingestion reports** (category-wise summaries)
- [ ] **Langfuse integration** for tracing, evaluation, and prompt versioning
- [ ] Feedback-driven prompt and model refinement

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTRIBUTING -->

## Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".
Don't forget to give the project a star! Thanks again!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Top contributors:

<a href="https://github.com/othneildrew/Best-README-Template/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=othneildrew/Best-README-Template" alt="contrib.rocks image" />
</a>

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- LICENSE -->

## License

Distributed under the Unlicense License. See `LICENSE.txt` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTACT -->

## Contact

Your Name - [@your_twitter](https://twitter.com/your_username) - email@example.com

Project Link: [https://github.com/your_username/repo_name](https://github.com/your_username/repo_name)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ACKNOWLEDGMENTS -->

## Acknowledgments

- [Choose an Open Source License](https://choosealicense.com)
- [GitHub Emoji Cheat Sheet](https://www.webpagefx.com/tools/emoji-cheat-sheet)
- [Malven's Flexbox Cheatsheet](https://flexbox.malven.co/)
- [Malven's Grid Cheatsheet](https://grid.malven.co/)
- [Img Shields](https://shields.io)
- [GitHub Pages](https://pages.github.com)
- [Font Awesome](https://fontawesome.com)
- [React Icons](https://react-icons.github.io/react-icons/search)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->

[contributors-shield]: https://img.shields.io/github/contributors/hridaya14/PaperLens.svg?style=for-the-badge
[contributors-url]: https://github.com/othneildrew/Best-README-Template/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/hridaya14/PaperLens.svg?style=for-the-badge
[forks-url]: https://github.com/hridaya14/PaperLens/network/members
[stars-shield]: https://img.shields.io/github/stars/hridaya14/PaperLens.svg?style=for-the-badge
[stars-url]: https://github.com/hridaya14/PaperLens/stargazers
[issues-shield]: https://img.shields.io/github/issues/hridaya14/PaperLens.svg?style=for-the-badge
[issues-url]: https://github.com/hridaya14/PaperLens/issues
[license-shield]: https://img.shields.io/github/license/hridaya14/PaperLens.svg?style=for-the-badge
[license-url]: https://github.com/hridaya14/PaperLens/blob/master/LICENSE.txt
[linkedin-shield]: https://img.shields.io/badge/-LinkedIn-black.svg?style=for-the-badge&logo=linkedin&colorB=555
[linkedin-url]: https://www.linkedin.com/in/hridaya-sharma-55513717b/
[product-screenshot]: public/architecture.png
[FastAPI]: https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white
[FastAPI-url]: https://fastapi.tiangolo.com/
[Streamlit]: https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white
[Streamlit-url]: https://streamlit.io/
[Airflow]: https://img.shields.io/badge/Apache%20Airflow-017CEE?style=for-the-badge&logo=apacheairflow&logoColor=white
[Airflow-url]: https://airflow.apache.org/
[OpenSearch]: https://img.shields.io/badge/OpenSearch-005EB8?style=for-the-badge&logo=opensearch&logoColor=white
[OpenSearch-url]: https://opensearch.org/
[Docker]: https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white
[Docker-url]: https://www.docker.com/
[Jina]: https://img.shields.io/badge/Jina%20AI-0A192F?style=for-the-badge&logo=data:image/svg+xml;base64,&logoColor=white
[Jina-url]: https://jina.ai/
[OpenAI]: https://img.shields.io/badge/OpenAI-000000?style=for-the-badge&logo=openai&logoColor=white
[OpenAI-url]: https://platform.openai.com/
