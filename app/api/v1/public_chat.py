"""
API routes: /api/v1/public/chat — Kênh chat công khai cho khách hàng.

KHÔNG yêu cầu đăng nhập (không dùng get_current_user / JWT) — đúng theo lựa chọn
thiết kế: khách chỉ cần điền tên/email khi nhắn tin, không cần tài khoản/mật khẩu.

    POST /api/v1/public/chat                  : gửi 1 tin nhắn (tạo ticket mới nếu
                                                  chưa có ticket_id, hoặc nối vào ticket
                                                  đang mở nếu có). Lần đầu sẽ tự động
                                                  chào khách + AI tự phân loại mức ưu tiên.
    GET  /api/v1/public/chat/{ticket_id}       : lấy lại toàn bộ hội thoại (để widget
                                                  poll tin nhắn mới), yêu cầu ?email=...
                                                  khớp với email khách đã dùng khi tạo ticket.
    POST /api/v1/public/chat/{ticket_id}/attachments : gửi kèm 1 file ảnh/video vào
                                                  hội thoại đang mở (multipart/form-data).
"""

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.database import get_db
from app.schemas.public_chat import (
    PublicChatMessageIn,
    PublicOrderSummary,
    PublicTicketStateOut,
)
from app.services import order_service, public_chat_service

router = APIRouter(prefix="/public/chat", tags=["Public Chat"])


@router.get("/orders", response_model=list[PublicOrderSummary])
@limiter.limit("20/minute")
def list_my_orders(
    request: Request,
    email: str = Query(..., description="Email khách hàng"),
    db: Session = Depends(get_db),
):
    """
    Khách xem lại các đơn hàng của chính mình (theo email) — dùng để chọn đơn
    liên quan trước khi gửi yêu cầu hỗ trợ (vd: khiếu nại đơn #12).

    LƯU Ý BẢO MẬT: endpoint này chỉ yêu cầu email (không có access_token hay
    mật khẩu), nên CHỦ Ý chỉ trả về thông tin tối thiểu (PublicOrderSummary:
    id, trạng thái, sản phẩm) — KHÔNG có địa chỉ giao hàng, tổng tiền, hay
    thông tin cá nhân của khách. Việc này giới hạn thiệt hại nếu ai đó dò
    email hàng loạt, đồng thời vẫn đủ để khách nhận ra đúng đơn hàng của mình.
    """
    return order_service.get_orders_by_customer_email(db, email)


@router.post("", response_model=PublicTicketStateOut, status_code=201)
@limiter.limit("10/minute")
def send_message(request: Request, payload: PublicChatMessageIn, db: Session = Depends(get_db)):
    """
    Khách gửi 1 tin nhắn. Nếu không kèm `ticket_id` + `access_token` hợp lệ
    (hoặc ticket đó đã đóng/không khớp), một ticket mới sẽ được tạo: khách
    được chào tự động ngay, AI tự phân loại nhóm vấn đề + mức ưu tiên, và
    ticket được đẩy vào hàng chờ để admin phân công cho nhân viên xử lý.

    Response trả về kèm `access_token` — client (widget) cần lưu lại giá trị
    này (vd: localStorage) để dùng cho các lần gọi tiếp theo.
    """
    ticket = public_chat_service.submit_message(db, payload)
    return public_chat_service.to_state_out(ticket)


@router.get("/{ticket_id}", response_model=PublicTicketStateOut)
@limiter.limit("30/minute")
def get_conversation(
    request: Request,
    ticket_id: int,
    access_token: str = Query(..., description="Mã tra cứu nhận được khi tạo ticket"),
    db: Session = Depends(get_db),
):
    """Lấy lại toàn bộ hội thoại của 1 ticket (dùng để widget khách tải/poll lại)."""
    ticket = public_chat_service.get_conversation(db, ticket_id, access_token)
    return public_chat_service.to_state_out(ticket)


@router.post("/{ticket_id}/attachments", response_model=PublicTicketStateOut, status_code=201)
@limiter.limit("10/minute")
def upload_attachment(
    request: Request,
    ticket_id: int,
    access_token: str = Form(..., description="Mã tra cứu nhận được khi tạo ticket"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Khách gửi kèm 1 ảnh/video vào hội thoại đang mở (vd: ảnh chụp sản phẩm lỗi,
    video quay lại sự cố). Chỉ chấp nhận file ảnh/video trong giới hạn dung
    lượng cấu hình (xem settings.MAX_IMAGE_SIZE_MB / MAX_VIDEO_SIZE_MB) — yêu
    cầu ticket đã tồn tại (khách phải nhắn tin lần đầu trước qua POST /public/chat).
    """
    ticket = public_chat_service.submit_attachment(db, ticket_id, access_token, file)
    return public_chat_service.to_state_out(ticket)
