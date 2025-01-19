from typing import Sequence

from app.core.text_splitter import TextSplitter
from app.core.vector import vectorize


class EmbeddingService:
    """
    Service for managing text chunking and embedding generation.

    This service provides:
    1. Text chunking with configurable strategies
    2. Embedding generation for text content
    3. Specialized chunking for different content types
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: list[str] | None = None,
    ):
        """
        Initialize the embedding service.

        Args:
            chunk_size: Maximum size of text chunks
            chunk_overlap: Number of characters to overlap between chunks
            separators: List of separators for text splitting, ordered by priority
        """
        self.default_separators: list[str] = [
            "\n\n",  # Paragraphs
            "\n",  # Lines
            ". ",  # Sentences
            ", ",  # Clauses
            " ",  # Words
            "",  # Characters
        ]

        self.text_splitter = TextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators or self.default_separators,
        )

        # File type specific separators
        self.file_type_separators: dict[str, list[str]] = {
            "text/markdown": ["\n## ", "\n# ", "\n### ", "\n\n", "\n", ". ", " ", ""],
            "text/code": ["\n\n\n", "\n\n", "\ndef ", "\nclass ", "\n", ". ", " ", ""],
            "text/plain": ["\n\n", "\n", ". ", " ", ""],
            "application/pdf": ["\n\n", "\n", ". ", " ", ""],
        }

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate an embedding vector for the given text.

        Args:
            text: The text to generate an embedding for

        Returns:
            List of floats representing the embedding vector
        """
        return vectorize(text=text)

    def chunk_text(
        self,
        text: str,
        file_type: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> Sequence[str]:
        """
        Split text into chunks using appropriate strategy.

        Args:
            text: The text to split into chunks
            file_type: Optional MIME type to use specialized splitting strategy
            chunk_size: Optional override for chunk size
            chunk_overlap: Optional override for chunk overlap

        Returns:
            List of text chunks
        """
        # Get appropriate separators for file type
        separators: list[str] = (
            self.file_type_separators.get(file_type, self.default_separators)
            if file_type
            else self.default_separators
        )

        # Create specialized splitter if needed
        if chunk_size or chunk_overlap or file_type:
            splitter = TextSplitter(
                chunk_size=chunk_size or self.text_splitter.chunk_size,
                chunk_overlap=chunk_overlap or self.text_splitter.chunk_overlap,
                separators=separators,
            )
            return splitter.split_text(text=text)

        # Use default splitter
        return self.text_splitter.split_text(text=text)
