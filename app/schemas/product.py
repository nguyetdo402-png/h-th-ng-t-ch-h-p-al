"""Pydantic schemas cho Product / ProductVariant (sản phẩm & tồn kho)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductVariantCreate(BaseModel):
    size: str = Field(min_length=1, max_length=20)
    color: str = Field(min_length=1, max_length=50)
    stock_quantity: int = Field(default=0, ge=0)


class ProductVariantUpdate(BaseModel):
    """Dùng để sửa tồn kho / thêm variant mới cho 1 sản phẩm đã có."""

    stock_quantity: int = Field(ge=0)


class ProductVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    size: str
    color: str
    stock_quantity: int


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    price: float = Field(gt=0)
    image_url: str | None = Field(default=None, max_length=500)
    # Cho phép tạo sản phẩm kèm luôn danh sách variant (size/màu/tồn kho ban đầu).
    variants: list[ProductVariantCreate] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price: float | None = Field(default=None, gt=0)
    image_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    price: float
    image_url: str | None
    is_active: bool
    created_at: datetime
    variants: list[ProductVariantOut] = []
