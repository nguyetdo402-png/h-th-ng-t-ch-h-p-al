"""
API routes cho AI Draft — sinh gợi ý AI và quy trình DUYỆT trước khi gửi khách.

  POST /api/v1/tickets/{ticket_id}/ai-draft   : sinh 1 draft mới (gọi AI)
  GET  /api/v1/tickets/{ticket_id}/ai-drafts  : xem lịch sử các draft của ticket
  PATCH /api/v1/ai-drafts/{draft_id}/approve  : DUYỆT draft -> gửi cho khách

Phân quyền: admin, manager, hoặc agent đang được gán ticket đó.
Đây là nơi duy nhất áp dụng nguyên tắc "AI chỉ sinh nháp, con người phải duyệt".
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.ai_draft import AiDraftApprove, AiDraftOut
from app.services import ai_draft_service, ticket_service
from app.services.auth_service import get_current_user

router = APIRouter(tags=["AI Drafts"])


def _ensure_can_access_ticket(db: Session, ticket_id: int, current_user: User) -> None:
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    if not ticket_service.user_can_access_ticket(current_user, ticket):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thao tác AI draft trên ticket này",
        )


@router.post(
    "/tickets/{ticket_id}/ai-draft",
    response_model=AiDraftOut,
    status_code=status.HTTP_201_CREATED,
)
def generate_ai_draft(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Yêu cầu AI phân tích ticket: gợi ý category, priority, và soạn câu trả lời NHÁP.
    Kết quả LUÔN được lưu với is_approved=False — chưa gửi cho khách hàng.
    """
    _ensure_can_access_ticket(db, ticket_id, current_user)
    return ai_draft_service.generate_ai_draft(db, ticket_id)


@router.get("/tickets/{ticket_id}/ai-drafts", response_model=list[AiDraftOut])
def list_ai_drafts(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Xem lại toàn bộ các draft AI đã sinh cho ticket này (kể cả đã/chưa duyệt)."""
    _ensure_can_access_ticket(db, ticket_id, current_user)
    return ai_draft_service.get_ai_drafts(db, ticket_id)


@router.patch("/ai-drafts/{draft_id}/approve", response_model=AiDraftOut)
def approve_ai_draft(
    draft_id: int,
    payload: AiDraftApprove,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    DUYỆT một draft: đây là bước duy nhất khiến nội dung được coi là "đã gửi cho khách"
    (được ghi vào InteractionHistory với sender_type=agent). Agent có thể gửi kèm
    `edited_response` nếu muốn chỉnh sửa nội dung trước khi duyệt.
    """
    draft = ai_draft_service.get_ai_draft_or_404(db, draft_id)
    _ensure_can_access_ticket(db, draft.ticket_id, current_user)
    return ai_draft_service.approve_ai_draft(db, draft_id, payload)
