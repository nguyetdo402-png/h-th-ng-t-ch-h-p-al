"""
API routes: /api/v1/customers — Quản lý khách hàng.

Phân quyền:
- Xem (list/detail): mọi user đã đăng nhập (admin/agent/manager).
- Tạo/Sửa: admin, manager.
- Xoá: chỉ admin.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate
from app.services import customer_service
from app.services.auth_service import get_current_user, require_roles

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("", response_model=list[CustomerOut])
def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, description="Tìm theo tên hoặc email"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list:
    return customer_service.get_customers(db, skip=skip, limit=limit, search=search)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return customer_service.get_customer_or_404(db, customer_id)


@router.post(
    "",
    response_model=CustomerOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    return customer_service.create_customer(db, payload)


@router.put(
    "/{customer_id}",
    response_model=CustomerOut,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def update_customer(customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)):
    return customer_service.update_customer(db, customer_id, payload)


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("admin"))],
)
def delete_customer(customer_id: int, db: Session = Depends(get_db)) -> None:
    customer_service.delete_customer(db, customer_id)
