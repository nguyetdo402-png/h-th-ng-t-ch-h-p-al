"""Pydantic schemas cho Order / OrderItem (đơn hàng của khách)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import OrderStatus
from app.schemas.customer import CustomerOut
from app.schemas.product import ProductVariantOut


class OrderItemCreate(BaseModel):
    product_variant_id: int
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    customer_id: int
    shipping_address: str | None = Field(default=None, max_length=500)
    items: list[OrderItemCreate] = Field(min_length=1)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_variant_id: int
    quantity: int
    unit_price: float
    product_variant: ProductVariantOut


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    status: OrderStatus
    shipping_address: str | None
    total_amount: float
    created_at: datetime
    updated_at: datetime


class OrderDetailOut(OrderOut):
    customer: CustomerOut
    items: list[OrderItemOut] = []
