"""
API routes: /api/v1/orders — Quản lý đơn hàng (nhân viên nhập đơn giúp khách).

Phân quyền:
- Xem (list/detail): mọi user đã đăng nhập.
- Tạo đơn / cập nhật trạng thái: mọi user đã đăng nhập (agent cũng cần tạo đơn
  khi khách đặt hàng qua chat/điện thoại, không giới hạn riêng cho admin).
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import OrderStatus
from app.models.user import User
from app.schemas.order import OrderCreate, OrderDetailOut, OrderStatusUpdate
from app.services import order_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("", response_model=list[OrderDetailOut])
def list_orders(
    status_filter: OrderStatus | None = Query(None, alias="status"),
    customer_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list:
    return order_service.get_orders(
        db, skip=skip, limit=limit, status_filter=status_filter, customer_id=customer_id
    )


@router.get("/{order_id}", response_model=OrderDetailOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return order_service.get_order_or_404(db, order_id)


@router.post("", response_model=OrderDetailOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Tạo đơn hàng mới — tự động kiểm tra và trừ tồn kho theo từng variant."""
    return order_service.create_order(db, payload)


@router.patch("/{order_id}/status", response_model=OrderDetailOut)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Cập nhật trạng thái đơn — chuyển sang 'cancelled' sẽ tự hoàn lại tồn kho."""
    return order_service.update_order_status(db, order_id, payload)
