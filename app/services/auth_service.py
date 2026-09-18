"""
Xử lý xác thực & phân quyền:
- authenticate_user(): kiểm tra email/password khi login.
- get_current_user(): dependency giải mã JWT -> trả về User đang đăng nhập.
- require_roles(): dependency factory để giới hạn endpoint theo role (RBAC).
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.login_lockout import ensure_not_locked, register_failed_attempt, reset_login_attempts
from app.core.security import decode_access_token, verify_password
from app.database import get_db
from app.models.user import User

# tokenUrl phải khớp với đường dẫn thật của endpoint login (dùng để sinh docs Swagger).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """
    Trả về User nếu email/password đúng và tài khoản đang active, ngược lại None.
    Nếu tài khoản đang bị khoá tạm (nhập sai quá 5 lần) hoặc vừa chạm ngưỡng khoá
    ở chính lần gọi này, raise HTTPException 423 thay vì trả None.
    """
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        return None

    ensure_not_locked(user)

    if not verify_password(password, user.hashed_password):
        register_failed_attempt(user, db)
        return None

    reset_login_attempts(user, db)
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency dùng trong mọi route cần đăng nhập:
        current_user: User = Depends(get_current_user)
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Không thể xác thực thông tin đăng nhập",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("user_id")
    if user_id is None:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception

    return user


def require_roles(*allowed_roles: str):
    """
    Dependency factory để giới hạn endpoint theo role, dùng như sau:
        @router.post(..., dependencies=[Depends(require_roles("admin", "manager"))])

    Hoặc lấy luôn user hiện tại:
        current_user: User = Depends(require_roles("admin"))
    """

    def _checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Yêu cầu quyền: {', '.join(allowed_roles)}",
            )
        return current_user

    return _checker
