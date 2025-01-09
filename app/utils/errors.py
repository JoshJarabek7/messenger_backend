from typing import Optional

from fastapi import HTTPException


class APIError(HTTPException):
    """Base API error class with predefined status codes and messages."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)


class NotFoundError(APIError):
    """Resource not found error."""

    def __init__(self, resource: str, resource_id: Optional[str] = None):
        detail = f"{resource} not found"
        if resource_id:
            detail = f"{resource} with id {resource_id} not found"
        super().__init__(status_code=404, detail=detail)


class UnauthorizedError(APIError):
    """Authentication error."""

    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(status_code=401, detail=detail)


class ForbiddenError(APIError):
    """Authorization error."""

    def __init__(self, detail: str = "Not authorized to perform this action"):
        super().__init__(status_code=403, detail=detail)


class ConflictError(APIError):
    """Resource conflict error."""

    def __init__(self, detail: str):
        super().__init__(status_code=409, detail=detail)


class ValidationError(APIError):
    """Input validation error."""

    def __init__(self, detail: str):
        super().__init__(status_code=400, detail=detail)


# Common error messages
def WORKSPACE_NOT_FOUND(id):
    return NotFoundError("Workspace", str(id))


def CHANNEL_NOT_FOUND(id):
    return NotFoundError("Channel", str(id))


def CONVERSATION_NOT_FOUND(id):
    return NotFoundError("Conversation", str(id))


def USER_NOT_FOUND(id):
    return NotFoundError("User", str(id))


def MESSAGE_NOT_FOUND(id):
    return NotFoundError("Message", str(id))


def NOT_WORKSPACE_MEMBER():
    return ForbiddenError("Not a member of this workspace")


def NOT_CHANNEL_MEMBER():
    return ForbiddenError("Not a member of this channel")


def NOT_CONVERSATION_PARTICIPANT():
    return ForbiddenError("Not a participant in this conversation")


def ADMIN_REQUIRED():
    return ForbiddenError("Admin access required for this action")


def USER_EXISTS(field):
    return ConflictError(f"A user with this {field} already exists")


def ALREADY_MEMBER(resource):
    return ConflictError(f"Already a member of this {resource}")


def INVALID_CREDENTIALS():
    return UnauthorizedError("Invalid email or password")


def INVALID_TOKEN():
    return UnauthorizedError("Invalid or expired token")


def MISSING_TOKEN():
    return UnauthorizedError("No authentication token provided")
