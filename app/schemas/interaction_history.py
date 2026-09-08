"""Pydantic schemas cho InteractionHistory (lịch sử hội thoại của ticket)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.interaction_history import AttachmentType, SenderType


class InteractionCreate(BaseModel):
    """
    Dùng khi agent chủ động ghi thêm 1 mục vào lịch sử (vd: trả lời khách,
    ghi chú nội bộ). Nhân viên KHÔNG được tự chọn sender_type (không được giả
    danh khách hàng/hệ thống) — endpoint luôn ghi cứng sender_type=agent ở
    tầng service, bất kể client gửi gì lên, nên field này chỉ giữ lại content.
    """

    content: str = Field(min_length=1)


class InteractionUpdate(BaseModel):
    """Dùng khi sửa lại nội dung một mục lịch sử đã ghi (vd: sửa lỗi chính tả)."""

    content: str = Field(min_length=1)


class InteractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    sender_type: SenderType
    content: str
    attachment_url: str | None = None
    attachment_type: AttachmentType | None = None
    attachment_filename: str | None = None
    created_at: datetime
