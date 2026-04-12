"""
vetgpt/config/__init__.py

Configuration package.
"""

from .book_registry import (
    BOOK_REGISTRY,
    BookMeta,
    OPEN_ACCESS,
    detect_book,
    books_by_species,
    books_by_status,
    print_registry_summary,
)

__all__ = [
    "BOOK_REGISTRY",
    "BookMeta",
    "OPEN_ACCESS",
    "PENDING_LICENSE",
    "detect_book",
    "books_by_species",
    "books_by_status",
    "print_registry_summary",
]