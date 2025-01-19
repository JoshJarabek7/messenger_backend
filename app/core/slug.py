import re

from unidecode import unidecode


def create_slug(text: str) -> str:
    """
    Create a URL-friendly slug from text.

    Args:
        text: The text to convert to a slug


    Returns:
        A lowercase string with spaces and special chars replaced with hyphens
    """
    slug = unidecode(text).lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    return slug
