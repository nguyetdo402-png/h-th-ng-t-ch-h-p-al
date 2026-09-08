"""SQLAlchemy model: Customer — khách hàng gửi ticket hỗ trợ."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Nullable CÓ CHỦ Ý: khách hàng có thể tồn tại mà chưa từng tự đăng ký
    # (vd: nhân viên tạo hồ sơ khi ghi nhận ticket qua điện thoại). Khách chỉ
    # đăng nhập được sau khi tự đăng ký qua /api/v1/customer-auth/register —
    # xem app/services/customer_auth_service.py để biết luồng "claim" tài
    # khoản khi email đã tồn tại nhưng chưa có mật khẩu.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Chống brute-force khi đăng nhập, cùng cơ chế với tài khoản nhân viên —
    # xem app/core/login_lockout.py.
    failed_login_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Một khách hàng có thể tạo nhiều ticket.
    tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket", back_populates="customer", cascade="all, delete-orphan"
    )
    # Một khách hàng có thể có nhiều đơn hàng.
    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="customer", cascade="all, delete-orphan", order_by="Order.id.desc()"
    )

    def __repr__(self) -> str:
        return f"<Customer id={self.id} email={self.email}>"
