"""SQLAlchemy model: User — nhân viên hệ thống (admin/agent/manager)."""

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    AGENT = "agent"
    MANAGER = "manager"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False), default=UserRole.AGENT, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Chống brute-force: đếm số lần nhập sai mật khẩu liên tiếp; đủ ngưỡng thì
    # khoá tạm bằng locked_until (xem app/core/login_lockout.py). Reset về 0/
    # None ngay khi đăng nhập đúng lại.
    failed_login_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Một agent (User) có thể được gán xử lý nhiều Ticket.
    tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket", back_populates="assigned_agent"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
