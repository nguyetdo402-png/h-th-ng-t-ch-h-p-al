"""
API routes: /api/v1/customer-auth — Đăng ký/đăng nhập cho KHÁCH HÀNG, và
trang "Tài khoản của tôi" (đơn hàng + lịch sử ticket/chat của chính khách).

Tách biệt hoàn toàn khỏi /api/v1/auth (dành cho nhân viên nội bộ: admin/
manager/agent). Xem app/services/customer_auth_service.py để biết cách 2 hệ
thống JWT không xung đột với nhau dù dùng chung hàm mã hoá ở core/security.py.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.database import get_db
from app.models.customer import Customer
from app.models.interaction_history import SenderType
from app.schemas.customer import CustomerOut
from app.schemas.customer_auth import CustomerLoginRequest, CustomerRegister, CustomerToken
from app.schemas.interaction_history import InteractionCreate, InteractionOut, InteractionUpdate
from app.schemas.order import OrderDetailOut
from app.schemas.ticket import TicketOut
from app.services import interaction_service, order_service, ticket_service
from app.services.customer_auth_service import (
    authenticate_customer,
    get_current_customer,
    register_customer,
)

router = APIRouter(prefix="/customer-auth", tags=["Customer Auth"])


@router.post("/register", response_model=CustomerToken, status_code=status.HTTP_201_CREATED)
def register(payload: CustomerRegister, db: Session = Depends(get_db)) -> CustomerToken:
    """
    Đăng ký tài khoản khách hàng. Nếu email đã tồn tại (hồ sơ do nhân viên tạo
    trước đó, chưa có mật khẩu), tài khoản đó sẽ được "claim" thay vì báo lỗi.
    Trả về access_token luôn để khách vào thẳng hệ thống, không cần đăng nhập lại.
    """
    customer = register_customer(db, payload)
    access_token = create_access_token(
        data={"sub": customer.email, "customer_id": customer.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return CustomerToken(access_token=access_token)


@router.post("/login", response_model=CustomerToken)
def login(payload: CustomerLoginRequest, db: Session = Depends(get_db)) -> CustomerToken:
    customer = authenticate_customer(db, email=payload.email, password=payload.password)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không đúng",
        )
    access_token = create_access_token(
        data={"sub": customer.email, "customer_id": customer.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return CustomerToken(access_token=access_token)


@router.get("/me", response_model=CustomerOut)
def read_current_customer(current_customer: Customer = Depends(get_current_customer)) -> Customer:
    return current_customer


@router.get("/me/orders", response_model=list[OrderDetailOut])
def read_my_orders(
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
) -> list:
    """Toàn bộ đơn hàng của chính khách hàng đang đăng nhập (trang 'Tài khoản của tôi')."""
    return order_service.get_orders(db, customer_id=current_customer.id, limit=200)


@router.get("/me/tickets", response_model=list[TicketOut])
def read_my_tickets(
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
) -> list:
    """Toàn bộ ticket hỗ trợ của chính khách hàng đang đăng nhập, mới nhất trước."""
    return ticket_service.get_tickets(db, customer_id=current_customer.id, limit=200)


@router.get("/me/tickets/{ticket_id}/interactions", response_model=list[InteractionOut])
def read_my_ticket_interactions(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
) -> list:
    """
    Lịch sử hội thoại (chat) của MỘT ticket cụ thể — chỉ khi ticket đó thuộc
    về chính khách hàng đang đăng nhập. Trả 404 (không phải 403) nếu ticket
    không thuộc về họ, để không lộ thông tin ticket của khách khác tồn tại
    hay không.
    """
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    if ticket.customer_id != current_customer.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy ticket id={ticket_id}",
        )
    # Lọc bỏ tin nhắn "system" (log nội bộ: phân công agent, lỗi phân loại AI...)
    # — cùng nguyên tắc với luồng chat công khai (public_chat_service.to_state_out):
    # khách hàng không bao giờ được thấy log vận hành nội bộ.
    interactions = interaction_service.get_interactions(db, ticket_id)
    return [i for i in interactions if i.sender_type != SenderType.SYSTEM]


@router.patch("/me/tickets/{ticket_id}/cancel", response_model=TicketOut)
def cancel_my_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
):
    """Khách hàng tự huỷ yêu cầu hỗ trợ của chính mình (chuyển sang 'closed')."""
    return ticket_service.cancel_ticket_by_customer(db, ticket_id, current_customer.id)


@router.post(
    "/me/tickets/{ticket_id}/interactions",
    response_model=InteractionOut,
    status_code=status.HTTP_201_CREATED,
)
def send_my_message(
    ticket_id: int,
    payload: InteractionCreate,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
):
    """
    Khách hàng ĐÃ ĐĂNG NHẬP gửi thêm tin nhắn vào ticket của chính mình, dùng
    ở trang "Tài khoản của tôi" — lối đi thay thế cho widget chat ẩn danh
    (vốn dựa vào access_token lưu ở localStorage, dễ mất khi khách đóng
    tab/trình duyệt). Nếu ticket đang 'closed', tự động mở lại (về 'new').
    """
    return interaction_service.create_message_by_customer(
        db, ticket_id, current_customer.id, payload
    )


@router.post(
    "/me/tickets/{ticket_id}/attachments",
    response_model=InteractionOut,
    status_code=status.HTTP_201_CREATED,
)
def send_my_attachment(
    ticket_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
):
    """
    Khách hàng ĐÃ ĐĂNG NHẬP gửi kèm 1 ảnh/video vào ticket của chính mình, dùng
    ở trang "Tài khoản của tôi" — bản dành cho khách đã đăng nhập của
    POST /public/chat/{ticket_id}/attachments (chat ẩn danh).
    """
    return interaction_service.create_attachment_by_customer(
        db, ticket_id, current_customer.id, file
    )


@router.put(
    "/me/tickets/{ticket_id}/interactions/{interaction_id}",
    response_model=InteractionOut,
)
def update_my_interaction(
    ticket_id: int,
    interaction_id: int,
    payload: InteractionUpdate,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
):
    """Khách hàng tự sửa lại nội dung MỘT TIN NHẮN DO CHÍNH MÌNH GỬI."""
    return interaction_service.update_interaction_by_customer(
        db, ticket_id, interaction_id, current_customer.id, payload
    )


@router.delete(
    "/me/tickets/{ticket_id}/interactions/{interaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_my_interaction(
    ticket_id: int,
    interaction_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
) -> None:
    """Khách hàng tự xoá MỘT TIN NHẮN DO CHÍNH MÌNH GỬI."""
    interaction_service.delete_interaction_by_customer(
        db, ticket_id, interaction_id, current_customer.id
    )
