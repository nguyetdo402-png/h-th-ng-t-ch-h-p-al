"""
API routes: /api/v1/tickets — Tạo / Phân công / Cập nhật trạng thái Ticket.

Phân quyền:
- Tạo ticket: chỉ admin, manager (agent không được tự tạo ticket thủ công).
- Xem (list/detail): admin, manager xem toàn bộ; agent CHỈ xem được ticket
  đang được gán cho chính mình (áp dụng cả banner "Cần xử lý ưu tiên").
- Sửa thông tin chung (title/description/priority): admin, manager.
- Phân công (assign) cho agent: admin, manager.
- Cập nhật trạng thái: admin, manager, HOẶC chính agent đang được gán ticket đó.
- Xoá ticket: chỉ admin.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ticket import TicketPriority, TicketStatus
from app.models.user import User, UserRole
from app.schemas.faq import FaqMatchOut
from app.schemas.ticket import (
    TicketAssign,
    TicketCreate,
    TicketOut,
    TicketStatusUpdate,
    TicketUpdate,
)
from app.services import faq_service, ticket_service
from app.services.auth_service import get_current_user, require_roles

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.get("", response_model=list[TicketOut])
def list_tickets(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: TicketStatus | None = Query(None, alias="status"),
    priority_filter: TicketPriority | None = Query(None, alias="priority"),
    assigned_to_agent_id: int | None = Query(None),
    customer_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list:
    """
    Danh sách ticket, hỗ trợ lọc theo status, priority, agent được gán, customer.

    Agent chỉ được xem ticket của chính mình: nếu người gọi là agent, tham số
    `assigned_to_agent_id` bị bỏ qua và luôn ép về ID của chính họ (kể cả khi
    client cố truyền ID khác) — admin/manager không bị giới hạn này.
    """
    if current_user.role == UserRole.AGENT:
        assigned_to_agent_id = current_user.id

    return ticket_service.get_tickets(
        db,
        skip=skip,
        limit=limit,
        status_filter=status_filter,
        priority_filter=priority_filter.value if priority_filter else None,
        assigned_to_agent_id=assigned_to_agent_id,
        customer_id=customer_id,
    )


@router.get("/priority-queue", response_model=list[TicketOut])
def get_priority_queue(
    limit: int = Query(8, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list:
    """
    Danh sách ticket CẦN XỬ LÝ TRƯỚC (chưa đóng, sắp theo mức ưu tiên cao ->
    thấp, cùng mức thì ticket chờ lâu hơn lên trước) — để hiển thị banner
    "Cần xử lý ưu tiên" ở đầu trang danh sách, giúp admin/nhân viên biết ngay
    ticket mới nào (do AI hoặc nhân viên đánh giá) đang khẩn cấp nhất.

    Agent chỉ thấy ticket của chính mình trong banner này (đồng bộ với
    list_tickets) — admin/manager thấy toàn bộ.
    """
    agent_scope = current_user.id if current_user.role == UserRole.AGENT else None
    return ticket_service.get_priority_queue(db, limit=limit, assigned_to_agent_id=agent_scope)


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    if not ticket_service.user_can_access_ticket(current_user, ticket):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công xử lý ticket này",
        )
    return ticket


@router.post(
    "",
    response_model=TicketOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def create_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
):
    """
    Tạo ticket thủ công cho một khách hàng đã tồn tại. Trạng thái ban đầu luôn
    là 'new'. Chỉ admin/manager được tạo tay — ticket của khách hàng thường
    được tạo tự động qua chat widget; agent không được tự tạo ticket.
    """
    return ticket_service.create_ticket(db, payload)


@router.get("/{ticket_id}/faq-suggestions", response_model=list[FaqMatchOut])
def get_faq_suggestions(
    ticket_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """
    Gợi ý các FAQ (câu trả lời mẫu) liên quan tới ticket này, dựa trên so khớp
    từ khóa với tiêu đề/mô tả/lịch sử tương tác. Agent xem trực tiếp ở đây để
    tự trả lời nhanh, không nhất thiết phải gọi AI sinh draft.
    """
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    matches = faq_service.find_matching_faqs_for_ticket(db, ticket)
    return [
        FaqMatchOut(
            id=m["faq"].id,
            question=m["faq"].question,
            answer=m["faq"].answer,
            matched_keywords=m["matched_keywords"],
        )
        for m in matches
    ]


@router.post("/{ticket_id}/ai-priority", response_model=TicketOut)
def suggest_ticket_priority(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Nhờ AI đánh giá lại mức ưu tiên + phân loại cho ticket này dựa trên nội
    dung/lịch sử hiện tại, rồi áp dụng luôn vào ticket (agent vẫn có thể tự
    sửa lại thủ công sau đó). Cùng quyền truy cập như cập nhật trạng thái:
    admin/manager luôn được, agent chỉ được nếu đang phụ trách ticket này.
    """
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)

    if not ticket_service.user_can_access_ticket(current_user, ticket):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền yêu cầu AI đánh giá ticket này",
        )

    return ticket_service.suggest_ticket_priority_ai(db, ticket_id)


@router.put(
    "/{ticket_id}",
    response_model=TicketOut,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def update_ticket(ticket_id: int, payload: TicketUpdate, db: Session = Depends(get_db)):
    """Cập nhật title/description/priority của ticket."""
    return ticket_service.update_ticket(db, ticket_id, payload)


@router.patch(
    "/{ticket_id}/assign",
    response_model=TicketOut,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def assign_ticket(ticket_id: int, payload: TicketAssign, db: Session = Depends(get_db)):
    """Phân công ticket cho một agent cụ thể. Ticket 'new' sẽ tự chuyển sang 'processing'."""
    return ticket_service.assign_ticket(db, ticket_id, payload)


@router.patch(
    "/{ticket_id}/unassign",
    response_model=TicketOut,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def unassign_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """Bỏ phân công ticket hiện tại (gỡ agent ra khỏi ticket)."""
    return ticket_service.unassign_ticket(db, ticket_id)


@router.patch("/{ticket_id}/status", response_model=TicketOut)
def update_ticket_status(
    ticket_id: int,
    payload: TicketStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cập nhật trạng thái ticket (new/processing/waiting/closed).
    Cho phép: admin, manager, hoặc chính agent đang được gán xử lý ticket này.
    """
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)

    if not ticket_service.user_can_access_ticket(current_user, ticket):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền cập nhật trạng thái ticket này",
        )

    return ticket_service.update_ticket_status(db, ticket_id, payload)


@router.delete(
    "/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("admin"))],
)
def delete_ticket(ticket_id: int, db: Session = Depends(get_db)) -> None:
    ticket_service.delete_ticket(db, ticket_id)
