"""
Hàm bảo mật cấp thấp: hash/verify password (bcrypt) và tạo/giải mã JWT.
Không phụ thuộc vào DB hay FastAPI — chỉ xử lý mật mã thuần tuý.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(plain_password: str) -> str:
    """Băm mật khẩu trước khi lưu vào DB."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """So khớp mật khẩu người dùng nhập với hash đã lưu."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    Tạo JWT access token.
    `data` thường chứa {"sub": user.email, "role": user.role, "user_id": user.id}.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Giải mã JWT. Trả về payload nếu hợp lệ, None nếu token sai/hết hạn."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
