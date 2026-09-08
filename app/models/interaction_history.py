"""SQLAlchemy model: InteractionHistory — lịch sử tin nhắn/sự kiện trong 1 ticket."""

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SenderType(str, enum.Enum):
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"  # vd: log đổi trạng thái, thông báo tự động, draft đã duyệt...
    BOT = "bot"  # tin nhắn chào tự động gửi ngay khi khách nhắn lần đầu (chưa có agent xử lý)


class AttachmentType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"


class InteractionHistory(Base):
    __tablename__ = "interaction_histories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_type: Mapped[SenderType] = mapped_column(
        Enum(SenderType, native_enum=False), nullable=False
    )
    # Với tin nhắn chỉ có ảnh/video (không gõ chữ), content vẫn được set 1 câu
    # mô tả ngắn (vd: "[Hình ảnh]") để nơi nào chỉ hiển thị text (thông báo,
    # tin nhắn hệ thống liệt kê...) vẫn có nội dung hợp lý để hiện ra.
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # --- File đính kèm (ảnh/video) — NULL nếu tin nhắn chỉ có chữ ---
    attachment_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attachment_type: Mapped[AttachmentType | None] = mapped_column(
        Enum(AttachmentType, native_enum=False), nullable=True
    )
    # Tên file gốc lúc khách upload (để hiển thị/tải về đúng tên), khác với
    # tên file vật lý lưu trên đĩa (được đổi thành UUID để tránh trùng/ghi đè).
    attachment_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="interactions")

    def __repr__(self) -> str:
        return f"<InteractionHistory id={self.id} ticket_id={self.ticket_id} sender={self.sender_type}>"
