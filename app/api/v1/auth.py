"""
API routes: /api/v1/auth
- POST /login        : đăng nhập, trả về JWT access token
- GET  /me           : thông tin user đang đăng nhập
- POST /register     : admin tạo tài khoản mới cho nhân viên (agent/manager/admin)
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.database import get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserOut
from app.services.auth_service import authenticate_user, get_current_user, require_roles
from app.services.user_service import create_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """
    Đăng nhập bằng email (điền vào field `username` của OAuth2 form) + password.
    Trả về JWT access token dùng cho các request tiếp theo (header:
    `Authorization: Bearer <token>`).
    """
    user = authenticate_user(db, email=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không đúng",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user.email, "user_id": user.id, "role": user.role.value},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=access_token)


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    """Trả về thông tin tài khoản đang đăng nhập (dùng để hiển thị trên UI)."""
    return current_user


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
def register_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    """Chỉ admin mới có quyền tạo tài khoản mới cho agent/manager/admin khác."""
    return create_user(db, payload)
