from typing import Callable

import pytest

from app.core.text_splitter import TextSplitter


@pytest.fixture
def text_splitter() -> TextSplitter:
    return TextSplitter()


def test_default_initialization():
    """Test default initialization of TextSplitter."""
    splitter = TextSplitter()
    assert splitter.chunk_size == 1000
    assert splitter.chunk_overlap == 200
    assert splitter.separators == ["\n\n", "\n", ". ", " ", ""]
    assert splitter.keep_separator is True
    assert splitter.strip_whitespace is True
    assert splitter.length_function == len


def test_custom_initialization():
    """Test custom initialization of TextSplitter."""

    def custom_length(text: str) -> int:
        return len(text.split())

    splitter = TextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        separators=["\n", " "],
        keep_separator=False,
        strip_whitespace=False,
        length_function=custom_length,
    )

    assert splitter.chunk_size == 500
    assert splitter.chunk_overlap == 100
    assert splitter.separators == ["\n", " "]
    assert splitter.keep_separator is False
    assert splitter.strip_whitespace is False
    assert splitter.length_function == custom_length


def test_split_text_empty(text_splitter: TextSplitter):
    """Test splitting empty text."""
    assert text_splitter.split_text("") == [""]


def test_split_text_small(text_splitter: TextSplitter):
    """Test splitting a small text that fits in one chunk."""
    text = "This is a small text."
    chunks = text_splitter.split_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_text_paragraphs(text_splitter: TextSplitter):
    """Test splitting text with paragraphs."""
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = text_splitter.split_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_text_large():
    """Test splitting a large text into multiple chunks."""
    splitter = TextSplitter(chunk_size=20, chunk_overlap=5)
    text = "This is a longer text that should be split into multiple chunks."
    chunks = splitter.split_text(text)
    assert len(chunks) > 1
    # Verify content is preserved (ignoring extra spaces)
    assert " ".join("".join(chunks).split()) == text


def test_split_text_with_custom_separators():
    """Test splitting text with custom separators."""
    splitter = TextSplitter(
        chunk_size=20,
        chunk_overlap=5,
        separators=["|||", "||", "|"],
    )

    text = "chunk1|||chunk2|||chunk3||part1|part2|part3"
    chunks = splitter.split_text(text)

    assert len(chunks) > 1
    assert "chunk1" in chunks[0]


def test_split_text_without_separator(text_splitter: TextSplitter):
    """Test splitting text without a natural separator."""
    text = "First sentence. Second sentence. Third sentence."
    chunks = text_splitter.split_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_text_strip_whitespace(text_splitter: TextSplitter):
    """Test that whitespace is handled correctly."""
    text = "  Multiple spaces and line breaks  \n\n"
    chunks = text_splitter.split_text(text)
    assert len(chunks) == 1
    assert chunks[0] == "Multiple spaces and line breaks"


def test_split_text_preserve_whitespace():
    """Test that significant whitespace is preserved."""
    splitter = TextSplitter(strip_whitespace=False)
    text = "  Multiple    spaces    and\n\nline   breaks  "
    chunks = splitter.split_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_text_custom_length_function():
    """Test using a custom length function."""

    def custom_length(text: str) -> int:
        return len(text.split())

    splitter = TextSplitter(
        chunk_size=5,  # Split after 5 words
        length_function=custom_length,
    )
    text = "This is a test of custom length function implementation"
    chunks = splitter.split_text(text)
    assert len(chunks) > 1
    # Verify content is preserved
    assert " ".join("".join(chunks).split()) == text


def test_split_text_with_all_separators(text_splitter: TextSplitter):
    """Test splitting text with all types of separators."""
    text = "First paragraph with multiple sentences.\n\nSecond paragraph on new line.\n\nThird paragraph with spaces and dots."
    chunks = text_splitter.split_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_text_edge_cases(text_splitter: TextSplitter):
    """Test edge cases."""
    assert text_splitter.split_text("") == [""]  # Empty string
    assert text_splitter.split_text("a") == ["a"]  # Single character
    assert text_splitter.split_text(" ") == [""]  # Only whitespace
