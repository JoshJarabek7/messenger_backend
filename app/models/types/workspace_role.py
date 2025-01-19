from enum import Enum


class WorkspaceRole(str, Enum):
    """User roles within a workspace."""

    ADMIN = "admin"
    MEMBER = "member"
    OWNER = "owner"