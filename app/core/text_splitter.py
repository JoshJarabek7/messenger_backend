from typing import Callable, List, Optional


class TextSplitter:
    """A recursive text splitter that breaks down text into chunks based on multiple levels of separators."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Optional[List[str]] = None,
        keep_separator: bool = True,
        strip_whitespace: bool = True,
        length_function: Callable[[str], int] = len,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]
        self.keep_separator = keep_separator
        self.strip_whitespace = strip_whitespace
        self.length_function = length_function

    def split_text(self, text: str) -> List[str]:
        """Split text into chunks recursively using multiple separators."""
        if not text:
            return [""]

        if self.strip_whitespace:
            text = text.strip()

        # If text is small enough, return it as a single chunk
        if self.length_function(text) <= self.chunk_size:
            return [text]

        chunks = []
        for separator in self.separators:
            if not separator:
                # No more separators to try, force split by chunk_size
                current_chunk = []
                current_length = 0
                words = text.split()

                for word in words:
                    word_length = self.length_function(word + " ")
                    if current_length + word_length > self.chunk_size and current_chunk:
                        chunks.append(" ".join(current_chunk))
                        # Keep some overlap
                        overlap_start = max(0, len(current_chunk) - self.chunk_overlap)
                        current_chunk = current_chunk[overlap_start:] + [word]
                        current_length = sum(
                            self.length_function(w + " ") for w in current_chunk
                        )
                    else:
                        current_chunk.append(word)
                        current_length += word_length

                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                break

            parts = text.split(separator)
            current_chunk = []
            current_length = 0

            for i, part in enumerate(parts):
                if not part:
                    continue

                piece = part + (
                    separator if self.keep_separator and i < len(parts) - 1 else ""
                )
                piece_length = self.length_function(piece)

                # If a single piece is larger than chunk_size, recursively split it
                if piece_length > self.chunk_size:
                    # Try to split this piece with the next separator in the list
                    next_separator_index = self.separators.index(separator) + 1
                    if next_separator_index < len(self.separators):
                        sub_chunks = TextSplitter(
                            chunk_size=self.chunk_size,
                            chunk_overlap=self.chunk_overlap,
                            separators=self.separators[next_separator_index:],
                            keep_separator=self.keep_separator,
                            strip_whitespace=False,  # Don't strip since we're in the middle of text
                            length_function=self.length_function,
                        ).split_text(piece)

                        # Add each sub-chunk, maintaining chunk size limits
                        for sub_chunk in sub_chunks:
                            sub_length = self.length_function(sub_chunk)
                            if (
                                current_length + sub_length > self.chunk_size
                                and current_chunk
                            ):
                                chunks.append("".join(current_chunk))
                                current_chunk = []
                                current_length = 0
                            current_chunk.append(sub_chunk)
                            current_length += sub_length
                    else:
                        # No more separators, force split by chunk_size
                        piece_words = piece.split()
                        for word in piece_words:
                            word_length = self.length_function(word + " ")
                            if (
                                current_length + word_length > self.chunk_size
                                and current_chunk
                            ):
                                chunks.append(" ".join(current_chunk))
                                current_chunk = []
                                current_length = 0
                            current_chunk.append(word)
                            current_length += word_length
                    continue

                # If adding this piece would exceed chunk_size, start a new chunk
                if current_length + piece_length > self.chunk_size and current_chunk:
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_length = 0

                current_chunk.append(piece)
                current_length += piece_length

            if current_chunk:
                chunks.append("".join(current_chunk))

            if chunks:
                # Successfully split with this separator
                break

        # If we couldn't split the text with any separator, force split it
        if not chunks:
            return [text[: self.chunk_size]]

        return chunks
