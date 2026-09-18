"""
API routes: /api/v1/products — Quản lý sản phẩm & tồn kho (kho hàng).

Phân quyền:
- Xem (list/detail): mọi user đã đăng nhập (admin/agent/manager) — agent cần
  xem tồn kho khi tư vấn khách qua ticket.
- Tạo sản phẩm, thêm variant, sửa tồn kho: admin, manager.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.product import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantOut,
)
from app.services import product_service
from app.services.auth_service import get_current_user, require_roles

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=list[ProductOut])
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    search: str | None = Query(None, description="Tìm theo tên sản phẩm"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list:
    return product_service.get_products(db, skip=skip, limit=limit, search=search)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return product_service.get_product_or_404(db, product_id)


@router.post(
    "",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    return product_service.create_product(db, payload)


@router.put(
    "/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    return product_service.update_product(db, product_id, payload)


@router.post(
    "/{product_id}/variants",
    response_model=ProductVariantOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def add_variant(product_id: int, payload: ProductVariantCreate, db: Session = Depends(get_db)):
    """Thêm 1 tổ hợp size/màu mới cho sản phẩm (vd: nhập thêm màu mới về)."""
    return product_service.add_variant(db, product_id, payload)


@router.patch(
    "/variants/{variant_id}/stock",
    response_model=ProductVariantOut,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def update_variant_stock(variant_id: int, stock_quantity: int, db: Session = Depends(get_db)):
    """Sửa trực tiếp số lượng tồn kho — dùng khi nhập hàng mới hoặc kiểm kho."""
    return product_service.update_variant_stock(db, variant_id, stock_quantity)
