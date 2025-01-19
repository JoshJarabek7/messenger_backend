from enum import Enum


class FileType(str, Enum):
    """Types of files that can be uploaded."""

    # Document types
    PDF = "pdf"
    DOCUMENT = "document"  # Word docs, text files, etc.
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    MARKDOWN = "markdown"
    HTML = "html"
    XML = "xml"
    RTF = "rtf"

    # Media types
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"

    # Email and communication
    EMAIL = "email"

    # Archive types
    ARCHIVE = "archive"

    # eBook types
    EBOOK = "ebook"

    # Code and config
    CODE = "code"
    CONFIG = "config"

    # Other types
    OTHER = "other"

    @classmethod
    def from_mime_type(cls, mime_type: str) -> "FileType":
        """Determine FileType from MIME type."""
        mime_map = {
            # Document formats
            "application/pdf": cls.PDF,
            "text/plain": cls.DOCUMENT,
            "text/csv": cls.SPREADSHEET,
            "text/markdown": cls.MARKDOWN,
            "text/html": cls.HTML,
            "text/xml": cls.XML,
            "text/rtf": cls.RTF,
            "application/rtf": cls.RTF,
            "application/msword": cls.DOCUMENT,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": cls.DOCUMENT,
            "application/vnd.ms-excel": cls.SPREADSHEET,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": cls.SPREADSHEET,
            "application/vnd.ms-powerpoint": cls.PRESENTATION,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": cls.PRESENTATION,
            # Media formats
            "image/": cls.IMAGE,
            "video/": cls.VIDEO,
            "audio/": cls.AUDIO,
            # Email formats
            "message/rfc822": cls.EMAIL,
            "application/vnd.ms-outlook": cls.EMAIL,
            # Archive formats
            "application/zip": cls.ARCHIVE,
            "application/x-tar": cls.ARCHIVE,
            "application/x-gzip": cls.ARCHIVE,
            # eBook formats
            "application/epub+zip": cls.EBOOK,
            "application/x-mobipocket-ebook": cls.EBOOK,
            # Code formats
            "text/x-python": cls.CODE,
            "application/javascript": cls.CODE,
            "text/javascript": cls.CODE,
            "application/x-httpd-php": cls.CODE,
            "text/x-java": cls.CODE,
            "text/x-c": cls.CODE,
            # Config formats
            "application/x-yaml": cls.CONFIG,
            "application/toml": cls.CONFIG,
            "application/x-ini": cls.CONFIG,
        }

        # Check exact matches first
        if mime_type in mime_map:
            return mime_map[mime_type]

        # Check prefix matches
        for mime_prefix, file_type in mime_map.items():
            if mime_prefix.endswith("/") and mime_type.startswith(mime_prefix):
                return file_type

        return cls.OTHER

    @classmethod
    def from_filename(cls, filename: str) -> "FileType":
        """Determine FileType from file extension."""
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        ext_map = {
            # Document formats
            "pdf": cls.PDF,
            "txt": cls.DOCUMENT,
            "doc": cls.DOCUMENT,
            "docx": cls.DOCUMENT,
            "rtf": cls.RTF,
            "odt": cls.DOCUMENT,
            "csv": cls.SPREADSHEET,
            "xls": cls.SPREADSHEET,
            "xlsx": cls.SPREADSHEET,
            "ods": cls.SPREADSHEET,
            "ppt": cls.PRESENTATION,
            "pptx": cls.PRESENTATION,
            "odp": cls.PRESENTATION,
            "md": cls.MARKDOWN,
            "markdown": cls.MARKDOWN,
            "html": cls.HTML,
            "htm": cls.HTML,
            "xml": cls.XML,
            # Media formats
            "jpg": cls.IMAGE,
            "jpeg": cls.IMAGE,
            "png": cls.IMAGE,
            "gif": cls.IMAGE,
            "webp": cls.IMAGE,
            "tiff": cls.IMAGE,
            "bmp": cls.IMAGE,
            "mp4": cls.VIDEO,
            "mov": cls.VIDEO,
            "avi": cls.VIDEO,
            "mp3": cls.AUDIO,
            "wav": cls.AUDIO,
            "ogg": cls.AUDIO,
            # Email formats
            "eml": cls.EMAIL,
            "msg": cls.EMAIL,
            # Archive formats
            "zip": cls.ARCHIVE,
            "tar": cls.ARCHIVE,
            "gz": cls.ARCHIVE,
            # eBook formats
            "epub": cls.EBOOK,
            "mobi": cls.EBOOK,
            # Code formats
            "py": cls.CODE,
            "js": cls.CODE,
            "java": cls.CODE,
            "cpp": cls.CODE,
            "c": cls.CODE,
            "cs": cls.CODE,
            "php": cls.CODE,
            "rb": cls.CODE,
            "go": cls.CODE,
            "rs": cls.CODE,
            "swift": cls.CODE,
            "kt": cls.CODE,
            "ts": cls.CODE,
            # Config formats
            "yaml": cls.CONFIG,
            "yml": cls.CONFIG,
            "toml": cls.CONFIG,
            "ini": cls.CONFIG,
            # Other formats
            "tex": cls.DOCUMENT,
            "rst": cls.MARKDOWN,
            "org": cls.MARKDOWN,
        }
        return ext_map.get(ext, cls.OTHER)
