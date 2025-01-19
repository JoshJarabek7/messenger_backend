from app.core.schema import BaseResponse


class Token(BaseResponse):
    """Token response schema."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
