"""
SQLAlchemy model: FaqEntry — câu trả lời mẫu (FAQ) do admin/manager soạn sẵn,
gắn với 1 tập từ khóa (vd: "size, đổi trả, hàng lỗi").

Mục đích: khi agent xử lý ticket, hệ thống tự động so khớp nội dung ticket với
`keywords` của từng FAQ để:
  1. Hiển thị trực tiếp cho agent các FAQ liên quan ngay trên trang chi tiết
     ticket (agent đọc và tự trả lời, không cần gọi AI).
  2. Đưa các FAQ liên quan vào ngữ cảnh (prompt) khi gọi AI sinh draft, để AI
     ưu tiên bám theo đúng chính sách cửa hàng đã soạn sẵn thay vì tự bịa.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FaqEntry(Base):
    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    question: Mapped[str] = mapped_column(String(255), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    # Danh sách từ khóa, lưu dạng chuỗi phân tách bởi dấu phẩy, ví dụ:
    # "size, đổi size, bảng size". Không dùng bảng riêng vì số lượng từ khóa
    # mỗi FAQ thường rất nhỏ (2-6 từ) — JOIN thêm 1 bảng con là thừa phức tạp.
    # Việc parse/so khớp nằm ở app/services/faq_service.py.
    keywords: Mapped[str] = mapped_column(String(500), nullable=False)

    # Cho phép admin tạm tắt 1 FAQ mà không cần xóa hẳn (vd: chính sách đang
    # được xem xét lại).
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<FaqEntry id={self.id} question={self.question!r}>"
