"""Pydantic schemas cho User + Token (đăng nhập/phân quyền)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: UserRole = UserRole.AGENT


class UserCreate(UserBase):
    """Dùng khi admin tạo tài khoản mới cho nhân viên."""

    password: str = Field(min_length=6, max_length=128)


class UserUpdate(BaseModel):
    """Cho phép cập nhật một phần thông tin (name, role, is_active)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: UserRole | None = None
    is_active: bool | None = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Nội dung giải mã được từ JWT (dùng nội bộ, không trả ra API)."""

    sub: str | None = None  # email của user
    user_id: int | None = None
    role: str | None = None
