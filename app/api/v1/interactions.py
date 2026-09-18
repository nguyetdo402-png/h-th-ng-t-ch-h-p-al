"""
API routes: /api/v1/tickets/{ticket_id}/interactions — Lịch sử hội thoại của ticket.

Phân quyền:
- Xem: mọi nhân viên đã đăng nhập.
- Thêm mới: admin, manager, hoặc agent đang được gán ticket đó.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.interaction_history import InteractionCreate, InteractionOut, InteractionUpdate
from app.services import interaction_service, ticket_service
from app.services.auth_service import get_current_user, require_roles

router = APIRouter(prefix="/tickets", tags=["Interactions"])


@router.get("/{ticket_id}/interactions", response_model=list[InteractionOut])
def list_interactions(
    ticket_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list:
    """Lấy toàn bộ lịch sử hội thoại của 1 ticket, theo thứ tự thời gian."""
    return interaction_service.get_interactions(db, ticket_id)


@router.post(
    "/{ticket_id}/interactions",
    response_model=InteractionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_interaction(
    ticket_id: int,
    payload: InteractionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ghi thêm 1 mục vào lịch sử hội thoại (trả lời khách, ghi chú nội bộ...).
    Luôn được ghi với sender_type=agent — nhân viên không được chọn giả danh
    khách hàng/hệ thống (xem interaction_service.create_interaction).

    Chỉ admin, manager, hoặc agent đang được gán ticket này mới được thêm.
    """
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    if not ticket_service.user_can_access_ticket(current_user, ticket):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thêm hội thoại vào ticket này",
        )
    return interaction_service.create_interaction(db, ticket_id, payload)


@router.put("/{ticket_id}/interactions/{interaction_id}", response_model=InteractionOut)
def update_interaction(
    ticket_id: int,
    interaction_id: int,
    payload: InteractionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sửa nội dung một mục lịch sử (vd: sửa lỗi chính tả). Không áp dụng cho
    nhật ký hệ thống (sender_type=system) — xem interaction_service để biết lý do.
    Quyền: admin, manager, hoặc agent đang được gán ticket này.
    """
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    if not ticket_service.user_can_access_ticket(current_user, ticket):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền sửa hội thoại của ticket này",
        )
    return interaction_service.update_interaction(db, ticket_id, interaction_id, payload)


@router.delete(
    "/{ticket_id}/interactions/{interaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def delete_interaction(ticket_id: int, interaction_id: int, db: Session = Depends(get_db)) -> None:
    """
    Xoá một mục lịch sử. Giới hạn ở admin/manager (chặt hơn quyền sửa) vì xoá
    là thao tác không thể hoàn tác, ảnh hưởng tới tính toàn vẹn audit trail.
    """
    interaction_service.delete_interaction(db, ticket_id, interaction_id)
