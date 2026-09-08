"""
SQLAlchemy models: Product / ProductVariant — sản phẩm & tồn kho của shop quần áo.

Một Product là "mẫu áo/quần" chung (vd: "Áo thun basic"). Vì quần áo luôn có
nhiều size/màu với số lượng tồn khác nhau, mỗi tổ hợp size+màu là 1
ProductVariant riêng — đây chính là nơi quản lý KHO (stock_quantity).

Ví dụ: Product "Áo thun basic" có thể có các variant:
    - Size S / Màu Trắng / tồn 20
    - Size M / Màu Trắng / tồn 15
    - Size M / Màu Đen   / tồn 0   (hết hàng)
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Giá niêm yết chung cho sản phẩm (VNĐ). Có thể coi là giá mặc định;
    # nếu sau này cần giá riêng theo variant thì thêm cột price ở ProductVariant.
    price: Mapped[float] = mapped_column(Numeric(12, 0), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductVariant.id",
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r}>"


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        # Không cho phép tạo trùng 2 variant cùng size+màu cho cùng 1 sản phẩm.
        UniqueConstraint("product_id", "size", "color", name="uq_variant_product_size_color"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    size: Mapped[str] = mapped_column(String(20), nullable=False)  # vd: "S", "M", "L", "XL"
    color: Mapped[str] = mapped_column(String(50), nullable=False)  # vd: "Trắng", "Đen"
    # Số lượng tồn kho hiện tại — đây là cột "kho" thực sự của hệ thống.
    stock_quantity: Mapped[int] = mapped_column(default=0, nullable=False)

    product: Mapped["Product"] = relationship("Product", back_populates="variants")

    @property
    def product_name(self) -> str:
        """
        Tiện ích cho các nơi hiển thị variant kèm tên sản phẩm cha (vd: tóm tắt
        đơn hàng ở trang "Tài khoản của tôi") mà không cần join/query thủ công
        ở tầng schema — chỉ cần đảm bảo `.product` đã được eager-load trước
        (xem order_service.py dùng selectinload) để tránh N+1 query.
        """
        return self.product.name
    order_items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="product_variant"
    )

    def __repr__(self) -> str:
        return (
            f"<ProductVariant id={self.id} product_id={self.product_id} "
            f"size={self.size} color={self.color} stock={self.stock_quantity}>"
        )
