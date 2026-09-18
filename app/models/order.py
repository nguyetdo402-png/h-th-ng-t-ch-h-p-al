"""
SQLAlchemy models: Order / OrderItem — đơn hàng của khách hàng.

Không có giỏ hàng/thanh toán online (theo yêu cầu) — đơn hàng được nhân viên
tạo trực tiếp trong trang quản trị (vd: khách nhắn tin/gọi điện đặt hàng, nhân
viên nhập đơn giúp khách), tương tự cách nhiều shop nhỏ vận hành thực tế.

Khi tạo đơn: mỗi OrderItem trừ tồn kho (ProductVariant.stock_quantity) ngay lập
tức và LƯU LẠI đơn giá tại thời điểm đặt (unit_price) — để sau này đổi giá sản
phẩm không làm sai lệch đơn hàng cũ.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OrderStatus(str, enum.Enum):
    PENDING = "pending"  # Mới tạo, chờ xác nhận
    CONFIRMED = "confirmed"  # Đã xác nhận, chuẩn bị giao
    SHIPPING = "shipping"  # Đang giao
    COMPLETED = "completed"  # Đã giao thành công
    CANCELLED = "cancelled"  # Đã huỷ (khi huỷ, tồn kho được hoàn lại)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, native_enum=False),
        default=OrderStatus.PENDING,
        nullable=False,
        index=True,
    )
    shipping_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Tổng tiền = tổng (unit_price * quantity) của các OrderItem, tính sẵn khi
    # tạo đơn để hiển thị nhanh mà không cần join/tính lại mỗi lần.
    total_amount: Mapped[float] = mapped_column(Numeric(14, 0), nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    customer: Mapped["Customer"] = relationship("Customer", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )
    tickets: Mapped[list["Ticket"]] = relationship("Ticket", back_populates="order")

    def __repr__(self) -> str:
        return f"<Order id={self.id} status={self.status} total={self.total_amount}>"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    # Đơn giá tại thời điểm đặt hàng (chụp lại từ Product.price lúc tạo đơn).
    unit_price: Mapped[float] = mapped_column(Numeric(12, 0), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product_variant: Mapped["ProductVariant"] = relationship(
        "ProductVariant", back_populates="order_items"
    )

    def __repr__(self) -> str:
        return f"<OrderItem order_id={self.order_id} variant={self.product_variant_id} qty={self.quantity}>"
