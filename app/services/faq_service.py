"""
Business logic cho FaqEntry:
  - CRUD cơ bản (admin/manager quản lý).
  - find_matching_faqs(): so khớp nội dung ticket (title + description + lịch
    sử tương tác) với `keywords` của từng FAQ đang active, trả về danh sách
    FAQ liên quan kèm từ khóa nào đã khớp.

Thuật toán so khớp: substring, không phân biệt hoa/thường, đã bỏ dấu tiếng
Việt ở CẢ HAI phía (nội dung ticket lẫn từ khóa FAQ) trước khi so sánh. Bỏ dấu
là vì nhân viên hoặc khách có thể gõ không dấu ("doi tra", "hang loi"), so
khớp có dấu tuyệt đối sẽ bỏ sót các trường hợp này. Đây là cách tiếp cận đơn
giản (rule-based), không cần thêm mô hình AI/embedding riêng cho việc này.
"""

import re
import unicodedata

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.faq import FaqEntry
from app.schemas.faq import FaqCreate, FaqUpdate


def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt, hạ chữ thường — dùng để so khớp không phân biệt dấu/hoa-thường."""
    normalized = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    # Riêng chữ "đ" NFD không tách dấu như các nguyên âm có dấu, cần thay tay.
    without_marks = without_marks.replace("đ", "d").replace("Đ", "D")
    return without_marks.lower()


def get_faqs(db: Session, active_only: bool = False) -> list[FaqEntry]:
    query = db.query(FaqEntry)
    if active_only:
        query = query.filter(FaqEntry.is_active.is_(True))
    return query.order_by(FaqEntry.id.desc()).all()


def get_faq_or_404(db: Session, faq_id: int) -> FaqEntry:
    faq = db.query(FaqEntry).filter(FaqEntry.id == faq_id).first()
    if not faq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy FAQ id={faq_id}"
        )
    return faq


def create_faq(db: Session, payload: FaqCreate) -> FaqEntry:
    faq = FaqEntry(**payload.model_dump())
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


def update_faq(db: Session, faq_id: int, payload: FaqUpdate) -> FaqEntry:
    faq = get_faq_or_404(db, faq_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(faq, field, value)
    db.commit()
    db.refresh(faq)
    return faq


def delete_faq(db: Session, faq_id: int) -> None:
    faq = get_faq_or_404(db, faq_id)
    db.delete(faq)
    db.commit()


def _build_ticket_matching_text(ticket) -> str:
    """Gộp title + description + nội dung các tương tác của ticket thành 1 đoạn văn bản để so khớp."""
    parts = [ticket.title or "", ticket.description or ""]
    for interaction in ticket.interactions:
        parts.append(interaction.content or "")
    return "\n".join(parts)


def find_matching_faqs_for_ticket(db: Session, ticket, limit: int = 3) -> list[dict]:
    """Tiện ích: so khớp FAQ trực tiếp từ 1 đối tượng Ticket (dùng ở cả API lẫn ai_draft_service)."""
    text = _build_ticket_matching_text(ticket)
    return find_matching_faqs(db, text, limit=limit)


def find_matching_faqs(db: Session, text: str, limit: int = 3) -> list[dict]:
    """
    So khớp `text` (thường là title + description + nội dung tương tác của 1
    ticket, gộp lại) với từ khóa của các FAQ đang active.

    Trả về tối đa `limit` FAQ, sắp theo số từ khóa khớp giảm dần (khớp càng
    nhiều từ khóa càng liên quan). Mỗi phần tử: {"faq": FaqEntry, "matched_keywords": [...]}.
    """
    if not text or not text.strip():
        return []

    normalized_text = _strip_accents(text)
    faqs = get_faqs(db, active_only=True)

    scored: list[dict] = []
    for faq in faqs:
        keyword_list = [k.strip() for k in faq.keywords.split(",") if k.strip()]
        matched = []
        for kw in keyword_list:
            normalized_kw = _strip_accents(kw)
            if not normalized_kw:
                continue
            # Dùng \b (ranh giới từ) thay vì so khớp chuỗi con thô, để tránh
            # khớp nhầm: vd từ khóa ngắn "hư" (-> "hu" sau khi bỏ dấu) không
            # được phép khớp vào giữa chữ "nhưng" (-> "nhung") chỉ vì chứa
            # substring "hu". \b chỉ khớp khi "hu" đứng thành 1 từ/cụm riêng.
            pattern = r"(?<!\w)" + re.escape(normalized_kw) + r"(?!\w)"
            if re.search(pattern, normalized_text):
                matched.append(kw)
        if matched:
            scored.append({"faq": faq, "matched_keywords": matched})

    scored.sort(key=lambda item: len(item["matched_keywords"]), reverse=True)
    return scored[:limit]
