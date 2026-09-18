"""
Business logic cho AiDraft: build ngữ cảnh ticket từ DB, gọi ai_service để sinh
gợi ý/câu trả lời, lưu kết quả (luôn với is_approved=False), và xử lý việc
agent "Duyệt" draft để gửi cho khách.

Đây là tầng DUY NHẤT được phép:
  - Đọc dữ liệu ticket/interactions từ DB để đưa vào ai_service.
  - Ghi AiDraft mới vào DB.
  - Khi duyệt: copy nội dung sang InteractionHistory (sender_type=agent).

ai_service.py không tự đọc/ghi DB — toàn bộ việc đó nằm ở đây, giữ đúng
nguyên tắc tách bạch "AI logic" khỏi "business/persistence logic".
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.ai_draft import AiDraft
from app.models.interaction_history import InteractionHistory, SenderType
from app.models.ticket import Ticket
from app.schemas.ai_draft import AiDraftApprove
from app.services import ai_service, faq_service
from app.services.ticket_service import get_ticket_or_404


def _build_ticket_context(ticket: Ticket, db: Session) -> ai_service.TicketContext:
    """
    Chuyển dữ liệu Ticket (kèm lịch sử tương tác) trong DB thành TicketContext
    để đưa vào ai_service. Chỉ lấy các trường văn bản tự do — không đưa email/
    số điện thoại của Customer vào đây (ai_service.anonymize_data sẽ tự ẩn PII
    nếu chúng lỡ xuất hiện lồng trong title/description/nội dung tương tác).

    Đồng thời so khớp ticket với các FAQ (câu trả lời mẫu theo từ khóa, xem
    app/services/faq_service.py) để đưa vào faq_context — giúp AI bám sát
    đúng chính sách cửa hàng thay vì tự suy diễn.
    """
    interactions = sorted(ticket.interactions, key=lambda i: i.created_at)
    matched_faqs = faq_service.find_matching_faqs_for_ticket(db, ticket)
    return {
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority.value,
        "status": ticket.status.value,
        "interactions": [
            {"sender_type": i.sender_type.value, "content": i.content} for i in interactions
        ],
        "faq_context": [
            {"question": m["faq"].question, "answer": m["faq"].answer} for m in matched_faqs
        ],
    }


def get_ai_drafts(db: Session, ticket_id: int) -> list[AiDraft]:
    """Trả về toàn bộ draft (kể cả đã duyệt/chưa duyệt) của 1 ticket, mới nhất trước."""
    get_ticket_or_404(db, ticket_id)
    return (
        db.query(AiDraft)
        .filter(AiDraft.ticket_id == ticket_id)
        .order_by(AiDraft.id.desc())
        .all()
    )


def get_ai_draft_or_404(db: Session, draft_id: int) -> AiDraft:
    draft = db.query(AiDraft).filter(AiDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy AI draft id={draft_id}",
        )
    return draft


def generate_ai_draft(db: Session, ticket_id: int) -> AiDraft:
    """
    Sinh một bản gợi ý AI mới cho ticket: phân loại + priority đề xuất + câu trả lời nháp.
    Luôn lưu với is_approved=False — KHÔNG BAO GIỜ gửi thẳng cho khách hàng ở bước này.
    """
    ticket = get_ticket_or_404(db, ticket_id)
    ticket_context = _build_ticket_context(ticket, db)

    try:
        classification = ai_service.classify_and_summarize(ticket_context)
        draft_response = ai_service.generate_draft_response(ticket_context)
    except (RuntimeError, ValueError) as exc:
        # Lỗi gọi AI (thiếu API key, lỗi mạng, provider không hợp lệ, ...)
        # -> trả 502 Bad Gateway thay vì để lộ traceback nội bộ ra ngoài.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Không thể sinh gợi ý AI: {exc}",
        ) from exc

    draft = AiDraft(
        ticket_id=ticket.id,
        suggested_category=classification["suggested_category"],
        suggested_priority=classification["suggested_priority"],
        draft_response=draft_response,
        is_approved=False,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def approve_ai_draft(db: Session, draft_id: int, payload: AiDraftApprove) -> AiDraft:
    """
    Duyệt một AI draft:
      1. Nếu agent có sửa nội dung (edited_response), dùng bản đã sửa; ngược lại
         giữ nguyên draft_response do AI sinh.
      2. Đánh dấu is_approved=True, ghi approved_at.
      3. Copy nội dung cuối cùng vào InteractionHistory với sender_type=agent —
         đây là bước DUY NHẤT khiến nội dung được xem là "đã gửi cho khách".

    Một draft đã duyệt thì không được duyệt lại lần nữa (tránh gửi trùng).
    """
    draft = get_ai_draft_or_404(db, draft_id)

    if draft.is_approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Draft này đã được duyệt trước đó",
        )

    final_content = (payload.edited_response or draft.draft_response).strip()
    if not final_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nội dung câu trả lời không được để trống",
        )

    draft.draft_response = final_content
    draft.is_approved = True
    draft.approved_at = datetime.now(timezone.utc)

    db.add(
        InteractionHistory(
            ticket_id=draft.ticket_id,
            sender_type=SenderType.AGENT,
            content=final_content,
        )
    )

    db.commit()
    db.refresh(draft)
    return draft
