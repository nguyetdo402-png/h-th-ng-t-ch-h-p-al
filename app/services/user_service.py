"""Business logic CRUD cho User (tài khoản nhân viên hệ thống)."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy user id={user_id}",
        )
    return user


def get_users(db: Session, skip: int = 0, limit: int = 50) -> list[User]:
    return db.query(User).order_by(User.id.desc()).offset(skip).limit(limit).all()


def create_user(db: Session, payload: UserCreate) -> User:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email đã được sử dụng",
        )

    user = User(
        name=payload.name,
        email=payload.email,
        role=payload.role,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: int, payload: UserUpdate) -> User:
    user = get_user_or_404(db, user_id)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, user_id: int) -> User:
    """Vô hiệu hoá tài khoản thay vì xoá cứng (giữ toàn vẹn dữ liệu ticket đã gán)."""
    user = get_user_or_404(db, user_id)
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user
