"""
API routes: /api/v1/users — Quản lý tài khoản nhân viên.

Việc TẠO user nằm ở /api/v1/auth/register (chỉ admin). File này chỉ xử lý
xem danh sách / chi tiết / cập nhật / vô hiệu hoá — cần thiết để, ví dụ,
frontend lấy danh sách agent hiển thị trong dropdown "Phân công ticket".
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserOut, UserUpdate
from app.services import user_service
from app.services.auth_service import get_current_user, require_roles

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserOut])
def list_users(
    role: UserRole | None = Query(None, description="Lọc theo role, vd: agent"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list:
    """
    Danh sách nhân viên. Mọi user đã đăng nhập đều xem được — cần thiết để
    hiển thị dropdown chọn agent khi phân công ticket.
    """
    users = user_service.get_users(db, skip=skip, limit=limit)
    if role:
        users = [u for u in users if u.role == role]
    return users


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return user_service.get_user_or_404(db, user_id)


@router.put(
    "/{user_id}",
    response_model=UserOut,
    dependencies=[Depends(require_roles("admin"))],
)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    """Chỉ admin được sửa thông tin/role/is_active của user khác."""
    return user_service.update_user(db, user_id, payload)


@router.patch(
    "/{user_id}/deactivate",
    response_model=UserOut,
    dependencies=[Depends(require_roles("admin"))],
)
def deactivate_user(user_id: int, db: Session = Depends(get_db)):
    """Vô hiệu hoá tài khoản (không xoá cứng, giữ toàn vẹn dữ liệu ticket đã gán)."""
    return user_service.deactivate_user(db, user_id)
