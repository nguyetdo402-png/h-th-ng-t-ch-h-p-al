"""SQLAlchemy model: Ticket — yêu cầu hỗ trợ của khách hàng."""

import enum
import secrets
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _generate_access_token() -> str:
    """
    Sinh mã tra cứu ngẫu nhiên, không đoán được (khác với ticket.id là số tự
    tăng dễ đoán). Khách dùng mã này (thay vì chỉ email) để tra cứu lại hội
    thoại — ngăn người khác đoán ticket_id rồi xem trộm bằng email đoán được.
    """
    return secrets.token_urlsafe(16)


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TicketPrioritySource(str, enum.Enum):
    """
    Đánh dấu mức ưu tiên hiện tại của ticket đến từ đâu:
      - AI: do AI tự phân loại (lúc tạo ticket, hoặc agent bấm "Đề xuất lại (AI)").
      - MANUAL: do nhân viên/admin tự tay chọn (ghi đè gợi ý AI hoặc đặt từ đầu).
    Chỉ để hiển thị cho nhân viên biết "cái này AI gợi ý hay người tự đặt" —
    không ảnh hưởng tới logic xử lý ticket nào khác.
    """

    AI = "ai"
    MANUAL = "manual"


class TicketStatus(str, enum.Enum):
    NEW = "new"
    PROCESSING = "processing"
    WAITING = "waiting"
    CLOSED = "closed"


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Mã tra cứu ngẫu nhiên (không phải mật khẩu, nhưng không đoán được như
    # ticket.id). Trả về cho khách 1 lần khi tạo ticket; khách cần mã này
    # (kèm ticket_id) để xem lại hội thoại hoặc gửi tin nhắn tiếp theo.
    access_token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=_generate_access_token, nullable=False
    )

    priority: Mapped[TicketPriority] = mapped_column(
        Enum(TicketPriority, native_enum=False),
        default=TicketPriority.MEDIUM,
        nullable=False,
        index=True,
    )
    # Nguồn gốc của mức ưu tiên hiện tại (AI tự đề xuất, hay nhân viên tự đặt).
    # Mặc định "manual" vì ticket tạo thủ công bởi nhân viên (không qua chat
    # widget) thì AI chưa từng đánh giá gì cả.
    priority_source: Mapped[TicketPrioritySource] = mapped_column(
        Enum(TicketPrioritySource, native_enum=False),
        default=TicketPrioritySource.MANUAL,
        nullable=False,
    )
    # Nhóm vấn đề do AI tự động phân loại khi ticket được tạo từ tin nhắn khách
    # (vd: "Lỗi kỹ thuật", "Thanh toán/Hoá đơn"...). Nullable vì ticket tạo thủ
    # công bởi nhân viên có thể chưa được AI phân loại.
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, native_enum=False),
        default=TicketStatus.NEW,
        nullable=False,
        index=True,
    )

    # Mốc thời gian ticket chuyển sang "closed" lần gần nhất — dùng để tính
    # thời gian xử lý (closed_at - created_at). Khác với updated_at (bị ghi
    # đè bởi MỌI thay đổi trên ticket, không chỉ riêng việc đóng), nên không
    # thể dùng updated_at để tính thời gian xử lý một cách tin cậy.
    # None nếu ticket chưa từng đóng, hoặc đã bị mở lại (reopen).
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Nullable: ticket mới tạo có thể chưa được gán cho agent nào.
    assigned_to_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Nullable: khách có thể nhắn tin hỏi chung, không liên quan đơn hàng cụ
    # thể nào. Khi có, giúp nhân viên biết ngay ticket này liên quan đơn nào
    # (vd: khiếu nại giao hàng chậm, đổi trả sản phẩm...).
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # --- Relationships ---
    customer: Mapped["Customer"] = relationship("Customer", back_populates="tickets")
    assigned_agent: Mapped["User | None"] = relationship("User", back_populates="tickets")
    order: Mapped["Order | None"] = relationship("Order", back_populates="tickets")

    interactions: Mapped[list["InteractionHistory"]] = relationship(
        "InteractionHistory",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="InteractionHistory.created_at",
    )
    ai_drafts: Mapped[list["AiDraft"]] = relationship(
        "AiDraft",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="AiDraft.id",
    )

    def __repr__(self) -> str:
        return f"<Ticket id={self.id} status={self.status} priority={self.priority}>"
