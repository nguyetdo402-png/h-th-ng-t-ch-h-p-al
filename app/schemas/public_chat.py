"""
Pydantic schemas cho luồng chat công khai (khách hàng nhắn tin, KHÔNG cần đăng nhập).

Khách chỉ cần cung cấp tên/email khi tạo ticket lần đầu — không có mật khẩu,
không có JWT. Đây là lựa chọn thiết kế có chủ đích: khách không cần đăng ký
tài khoản. Tuy nhiên, để tra cứu lại hoặc gửi tiếp tin nhắn vào một ticket đã
tồn tại, khách phải kèm theo `access_token` — một mã ngẫu nhiên không đoán
được, được hệ thống trả về đúng 1 lần khi ticket được tạo. Việc này thay thế
cách định danh cũ (chỉ email + ticket_id, vốn dễ bị đoán vì ticket_id là số
tự tăng và email khách không hề bí mật).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.interaction_history import AttachmentType, SenderType
from app.models.order import OrderStatus
from app.models.ticket import TicketPriority, TicketStatus
from app.schemas.product import ProductVariantOut


class PublicOrderItemSummary(BaseModel):
    """Tóm tắt 1 item trong đơn — đủ để khách nhận ra đơn hàng, không có giá."""

    model_config = ConfigDict(from_attributes=True)

    quantity: int
    product_variant: ProductVariantOut


class PublicOrderSummary(BaseModel):
    """
    Thông tin đơn hàng ở mức tối thiểu, dùng cho widget chat công khai để khách
    chọn "yêu cầu này liên quan đơn nào". CỐ Ý không có shipping_address,
    total_amount, hay thông tin Customer (tên/email/SĐT) — vì endpoint này chỉ
    yêu cầu email (không có access_token/mật khẩu) nên không nên trả PII nhạy
    cảm ra ngoài, tránh việc dò email hàng loạt để lấy địa chỉ/SĐT khách khác.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OrderStatus
    created_at: datetime
    items: list[PublicOrderItemSummary] = []


class PublicChatMessageIn(BaseModel):
    """Payload khi khách gửi 1 tin nhắn (lần đầu hoặc tiếp theo)."""

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=20)
    message: str = Field(min_length=1)
    # Nếu khách đang tiếp tục 1 cuộc hội thoại đã có (ticket chưa đóng), gửi kèm
    # ticket_id + access_token (mã nhận được khi tạo ticket) để nối tiếp vào
    # đúng ticket đó thay vì tạo ticket mới. Thiếu hoặc sai access_token ->
    # hệ thống coi như tạo ticket mới (không lộ thông tin ticket cũ).
    ticket_id: int | None = None
    access_token: str | None = Field(default=None, max_length=64)
    # Optional: đơn hàng mà yêu cầu này liên quan tới (khiếu nại, hỏi tình trạng
    # giao hàng...). Chỉ áp dụng khi tạo ticket MỚI (bỏ qua nếu đang nối tiếp).
    order_id: int | None = None


class PublicMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_type: SenderType
    content: str
    attachment_url: str | None = None
    attachment_type: AttachmentType | None = None
    attachment_filename: str | None = None
    created_at: datetime


class PublicTicketStateOut(BaseModel):
    """
    Trạng thái hội thoại trả về cho widget chat của khách sau mỗi lần gửi/tải lại.
    Được build thủ công ở service layer (không dùng from_attributes trực tiếp trên
    Ticket vì Ticket không có field `messages`).
    """

    ticket_id: int
    # Mã tra cứu — chỉ khách đang giữ mã này mới đọc/tiếp tục được hội thoại.
    # Frontend cần lưu lại giá trị này (vd: localStorage) ngay khi nhận được.
    access_token: str
    status: TicketStatus
    priority: TicketPriority
    category: str | None = None
    order_id: int | None = None
    messages: list[PublicMessageOut] = []
