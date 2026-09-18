"""Business logic CRUD cho Customer."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate


def get_customer_or_404(db: Session, customer_id: int) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy khách hàng id={customer_id}",
        )
    return customer


def get_customers(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
) -> list[Customer]:
    """Lấy danh sách khách hàng, hỗ trợ tìm kiếm theo tên hoặc email."""
    query = db.query(Customer)
    if search:
        like = f"%{search}%"
        query = query.filter((Customer.name.ilike(like)) | (Customer.email.ilike(like)))
    return query.order_by(Customer.id.desc()).offset(skip).limit(limit).all()


def get_or_create_customer_by_email(
    db: Session, name: str, email: str, phone: str | None = None
) -> Customer:
    """
    Dùng cho luồng chat công khai (khách không cần đăng nhập): tìm khách hàng theo
    email; nếu chưa có thì tạo mới. Nếu đã có, cập nhật lại tên/SĐT nếu khách
    gửi thông tin mới (vd: khách đổi tên hiển thị hoặc bổ sung SĐT ở lần nhắn sau).
    """
    customer = db.query(Customer).filter(Customer.email == email).first()
    if customer:
        if name and name.strip() and name.strip() != customer.name:
            customer.name = name.strip()
        if phone and phone.strip() and phone.strip() != customer.phone:
            customer.phone = phone.strip()
        db.commit()
        db.refresh(customer)
        return customer

    customer = Customer(name=name.strip(), email=email, phone=(phone.strip() if phone else None))
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def create_customer(db: Session, payload: CustomerCreate) -> Customer:
    existing = db.query(Customer).filter(Customer.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email khách hàng đã tồn tại",
        )
    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def update_customer(db: Session, customer_id: int, payload: CustomerUpdate) -> Customer:
    customer = get_customer_or_404(db, customer_id)

    update_data = payload.model_dump(exclude_unset=True)

    new_email = update_data.get("email")
    if new_email and new_email != customer.email:
        existing = db.query(Customer).filter(Customer.email == new_email).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email khách hàng đã tồn tại",
            )

    for field, value in update_data.items():
        setattr(customer, field, value)

    db.commit()
    db.refresh(customer)
    return customer


def delete_customer(db: Session, customer_id: int) -> None:
    customer = get_customer_or_404(db, customer_id)
    db.delete(customer)
    db.commit()
