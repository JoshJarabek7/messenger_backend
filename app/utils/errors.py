from fastapi import HTTPException
from typing import Optional

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
WORKSPACE_NOT_FOUND = lambda id: NotFoundError("Workspace", str(id))
CHANNEL_NOT_FOUND = lambda id: NotFoundError("Channel", str(id))
CONVERSATION_NOT_FOUND = lambda id: NotFoundError("Conversation", str(id))
USER_NOT_FOUND = lambda id: NotFoundError("User", str(id))
MESSAGE_NOT_FOUND = lambda id: NotFoundError("Message", str(id))

NOT_WORKSPACE_MEMBER = lambda: ForbiddenError("Not a member of this workspace")
NOT_CHANNEL_MEMBER = lambda: ForbiddenError("Not a member of this channel")
NOT_CONVERSATION_PARTICIPANT = lambda: ForbiddenError("Not a participant in this conversation")
ADMIN_REQUIRED = lambda: ForbiddenError("Admin access required for this action")

USER_EXISTS = lambda field: ConflictError(f"A user with this {field} already exists")
ALREADY_MEMBER = lambda resource: ConflictError(f"Already a member of this {resource}")

INVALID_CREDENTIALS = lambda: UnauthorizedError("Invalid email or password")
INVALID_TOKEN = lambda: UnauthorizedError("Invalid or expired token")
MISSING_TOKEN = lambda: UnauthorizedError("No authentication token provided") 