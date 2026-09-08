"""
SQLAlchemy model: AiDraft — kết quả gợi ý của AI cho một ticket.

Nguyên tắc quan trọng: AI KHÔNG BAO GIỜ gửi trực tiếp cho khách hàng.
Mọi kết quả (phân loại, priority gợi ý, câu trả lời nháp) đều được lưu ở đây
với is_approved=False. Chỉ khi agent bấm "Duyệt" trên giao diện, hệ thống mới:
  1) set is_approved = True
  2) copy draft_response sang InteractionHistory (sender_type=agent) để gửi khách
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AiDraft(Base):
    __tablename__ = "ai_drafts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Gợi ý phân loại & mức độ ưu tiên do AI đề xuất (agent có thể chấp nhận
    # hoặc sửa lại priority thật của Ticket dựa trên gợi ý này).
    suggested_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suggested_priority: Mapped[str | None] = mapped_column(String(20), nullable=True)

    draft_response: Mapped[str] = mapped_column(Text, nullable=False)

    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="ai_drafts")

    def __repr__(self) -> str:
        return f"<AiDraft id={self.id} ticket_id={self.ticket_id} approved={self.is_approved}>"
