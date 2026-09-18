"""
Pydantic schemas cho luồng tự đăng ký/đăng nhập của KHÁCH HÀNG.

Tách biệt hoàn toàn khỏi app/schemas/user.py (dành cho nhân viên nội bộ) —
khách hàng và nhân viên là 2 loại tài khoản khác nhau, không dùng chung
endpoint hay JWT payload (xem customer_auth_service.py để biết cách phân
biệt token khách hàng vs token nhân viên).
"""

from pydantic import BaseModel, EmailStr, Field


class CustomerRegister(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    phone: str | None = Field(default=None, max_length=20)


class CustomerLoginRequest(BaseModel):
    email: EmailStr
    password: str


class CustomerToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
