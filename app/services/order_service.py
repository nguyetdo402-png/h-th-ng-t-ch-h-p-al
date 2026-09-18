"""
Business logic cho Order / OrderItem.

Quy tắc kho hàng:
    - Khi TẠO đơn: kiểm tra đủ tồn kho cho từng variant, nếu đủ thì TRỪ ngay
      (stock_quantity -= quantity). Nếu bất kỳ dòng nào không đủ hàng, huỷ toàn
      bộ thao tác (rollback) — không tạo đơn nửa vời.
    - Khi HUỶ đơn (chuyển status -> cancelled): HOÀN lại tồn kho tương ứng.
      Chỉ hoàn 1 lần — nếu đơn đã ở trạng thái cancelled rồi thì không hoàn lại nữa.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import ProductVariant
from app.schemas.order import OrderCreate, OrderStatusUpdate


def get_order_or_404(db: Session, order_id: int) -> Order:
    order = (
        db.query(Order)
        .options(selectinload(Order.customer), selectinload(Order.items).selectinload(OrderItem.product_variant).selectinload(ProductVariant.product))
        .filter(Order.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng id={order_id}",
        )
    return order


def get_orders(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status_filter: OrderStatus | None = None,
    customer_id: int | None = None,
) -> list[Order]:
    query = db.query(Order).options(
        selectinload(Order.customer), selectinload(Order.items).selectinload(OrderItem.product_variant).selectinload(ProductVariant.product)
    )
    if status_filter:
        query = query.filter(Order.status == status_filter)
    if customer_id:
        query = query.filter(Order.customer_id == customer_id)
    return query.order_by(Order.id.desc()).offset(skip).limit(limit).all()


def get_orders_by_customer_email(db: Session, email: str) -> list[Order]:
    """Dùng cho widget chat công khai: khách xem lại đơn hàng của chính mình theo email."""
    return (
        db.query(Order)
        .join(Customer, Order.customer_id == Customer.id)
        .options(
            selectinload(Order.customer),
            selectinload(Order.items).selectinload(OrderItem.product_variant).selectinload(ProductVariant.product),
        )
        .filter(Customer.email == email)
        .order_by(Order.id.desc())
        .all()
    )


def create_order(db: Session, payload: OrderCreate) -> Order:
    customer = db.query(Customer).filter(Customer.id == payload.customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy khách hàng id={payload.customer_id}",
        )

    order = Order(customer_id=payload.customer_id, shipping_address=payload.shipping_address)
    db.add(order)
    db.flush()  # cần order.id trước khi tạo OrderItem

    total_amount = 0.0
    for item_payload in payload.items:
        variant = (
            db.query(ProductVariant)
            .filter(ProductVariant.id == item_payload.product_variant_id)
            .first()
        )
        if not variant:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy biến thể sản phẩm id={item_payload.product_variant_id}",
            )
        if variant.stock_quantity < item_payload.quantity:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Sản phẩm '{variant.product.name}' (size {variant.size}, màu {variant.color}) "
                    f"chỉ còn {variant.stock_quantity} trong kho, không đủ {item_payload.quantity} yêu cầu."
                ),
            )

        unit_price = float(variant.product.price)
        variant.stock_quantity -= item_payload.quantity
        db.add(
            OrderItem(
                order_id=order.id,
                product_variant_id=variant.id,
                quantity=item_payload.quantity,
                unit_price=unit_price,
            )
        )
        total_amount += unit_price * item_payload.quantity

    order.total_amount = total_amount
    db.commit()
    db.refresh(order)
    return order


def update_order_status(db: Session, order_id: int, payload: OrderStatusUpdate) -> Order:
    order = get_order_or_404(db, order_id)

    was_cancelled = order.status == OrderStatus.CANCELLED
    order.status = payload.status

    # Hoàn kho khi đơn chuyển sang huỷ (và trước đó chưa từng bị huỷ).
    if payload.status == OrderStatus.CANCELLED and not was_cancelled:
        for item in order.items:
            item.product_variant.stock_quantity += item.quantity

    db.commit()
    db.refresh(order)
    return order
