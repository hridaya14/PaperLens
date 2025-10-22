from functools import lru_cache

from src.config import get_settings

from .parser import PDFParserService


@lru_cache(maxsize=1)
def make_pdf_parser_service() -> PDFParserService:
    """Create cached PDF parser service using Docling."""

    # Get settings from centralized config
    settings = get_settings()

    # Create PDF parser with settings
    return PDFParserService(
        max_pages=settings.pdf_parser.max_pages,
        max_file_size_mb=settings.pdf_parser.max_file_size_mb,
        do_ocr=settings.pdf_parser.do_ocr,
        do_table_structure=settings.pdf_parser.do_table_structure,
    )


def reset_pdf_parser() -> None:
    """
    Reset the cached instance using lru_cache's built-in cache management.
    Useful for testing or when configuration changes.
    """
    make_pdf_parser_service.cache_clear()
