from pydantic import BaseModel, EmailStr


class UserCreateRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    display_name: str


class UserUpdateRequest(BaseModel):
    email: EmailStr | None = None
    username: str | None = None
    display_name: str | None = None


