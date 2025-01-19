import io
from typing import Optional

import magic
import pytesseract
from PIL import Image
from unstructured.partition.auto import partition


class FileParser:
    """Handles detection and parsing of various file types using unstructured library."""

    SUPPORTED_MIME_TYPES = {
        # Text files
        "text/plain": True,
        "text/markdown": True,
        "text/html": True,
        "text/csv": True,
        # Document files
        "application/pdf": True,
        "application/msword": True,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": True,
        # Spreadsheets
        "application/vnd.ms-excel": True,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": True,
        # Presentations
        "application/vnd.ms-powerpoint": True,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": True,
        # Data files
        "application/json": True,
        "application/xml": True,
        "application/yaml": True,
        # Images
        "image/jpeg": "image",
        "image/png": "image",
        "image/gif": "image",
        "image/tiff": "image",
    }

    @staticmethod
    def detect_mime_type(file_content: bytes) -> str:
        """Detect MIME type of file content."""
        mime = magic.Magic(mime=True)
        return mime.from_buffer(file_content)

    @staticmethod
    def should_parse(mime_type: str) -> bool:
        """Determine if we should attempt to parse this file type."""
        return mime_type in FileParser.SUPPORTED_MIME_TYPES

    @staticmethod
    def parse_file(file_content: bytes, mime_type: str) -> Optional[str]:
        """Parse file content based on its MIME type."""
        if not FileParser.should_parse(mime_type):
            return None

        # Handle images separately since they need OCR
        if FileParser.SUPPORTED_MIME_TYPES[mime_type] == "image":
            return FileParser.parse_image(file_content)

        # For all other file types, use unstructured
        file_like = io.BytesIO(file_content)
        elements = partition(file=file_like, content_type=mime_type)
        return "\n".join(str(element) for element in elements)

    @staticmethod
    def parse_image(content: bytes) -> str:
        """Parse images using OCR."""
        image_file = io.BytesIO(content)
        image = Image.open(image_file)

        # Convert image to RGB if necessary
        if image.mode not in ("L", "RGB"):
            image = image.convert("RGB")

        # Perform OCR
        text = pytesseract.image_to_string(image)
        return text.strip()
