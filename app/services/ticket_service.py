"""
Business logic cho Ticket: tạo mới, danh sách/lọc, phân công agent,
cập nhật trạng thái. Mỗi thay đổi quan trọng (phân công, đổi trạng thái)
đều được ghi lại vào InteractionHistory (sender_type=system) để có dấu vết
audit — hữu ích khi xem lại lịch sử xử lý ticket.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.interaction_history import InteractionHistory, SenderType
from app.models.ticket import Ticket, TicketPrioritySource, TicketStatus
from app.models.user import User, UserRole
from app.schemas.ticket import TicketAssign, TicketCreate, TicketStatusUpdate, TicketUpdate
from app.services import ai_service, faq_service


def get_ticket_or_404(db: Session, ticket_id: int) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy ticket id={ticket_id}",
        )
    return ticket


def user_can_access_ticket(user: User, ticket: Ticket) -> bool:
    """
    Quy tắc dùng chung cho các thao tác "thuộc về 1 ticket cụ thể"
    (đổi trạng thái, thêm interaction, sinh/duyệt AI draft):
      - admin, manager: luôn được phép.
      - agent: chỉ được phép nếu đang là người được gán xử lý ticket đó.
    """
    if user.role in (UserRole.ADMIN, UserRole.MANAGER):
        return True
    return user.role == UserRole.AGENT and ticket.assigned_to_agent_id == user.id


def get_tickets(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    status_filter: TicketStatus | None = None,
    priority_filter: str | None = None,
    assigned_to_agent_id: int | None = None,
    customer_id: int | None = None,
) -> list[Ticket]:
    """Lấy danh sách ticket, hỗ trợ lọc theo status/priority/agent/customer."""
    query = db.query(Ticket)

    if status_filter:
        query = query.filter(Ticket.status == status_filter)
    if priority_filter:
        query = query.filter(Ticket.priority == priority_filter)
    if assigned_to_agent_id is not None:
        query = query.filter(Ticket.assigned_to_agent_id == assigned_to_agent_id)
    if customer_id is not None:
        query = query.filter(Ticket.customer_id == customer_id)

    return query.order_by(Ticket.created_at.desc()).offset(skip).limit(limit).all()


# Thứ tự ưu tiên cao -> thấp khi cần SẮP XẾP theo mức độ khẩn cấp (khác với thứ
# tự alphabet mặc định "high" < "low" < "medium" nếu sort chuỗi thông thường).
_PRIORITY_RANK = case(
    (Ticket.priority == "high", 0),
    (Ticket.priority == "medium", 1),
    (Ticket.priority == "low", 2),
    else_=3,
)


def get_priority_queue(
    db: Session,
    limit: int = 8,
    assigned_to_agent_id: int | None = None,
) -> list[Ticket]:
    """
    Danh sách ticket CẦN CHÚ Ý TRƯỚC, dành cho banner "Cần xử lý ưu tiên" ở đầu
    trang danh sách — giúp quản trị/nhân viên thấy ngay ticket nào (đặc biệt là
    ticket mới) đang được AI (hoặc nhân viên) đánh giá gấp, thay vì phải tự lọc
    thủ công qua hàng trăm ticket.

    Tiêu chí: chưa đóng (status != closed), sắp theo mức ưu tiên cao trước,
    ticket cũ hơn ở cùng mức ưu tiên được đẩy lên trước (chờ lâu -> ưu tiên xử lý).

    assigned_to_agent_id: nếu truyền vào (agent xem trang của chính mình), chỉ
    tính các ticket đang được gán cho agent đó — agent không thấy ticket của
    người khác kể cả trong banner ưu tiên.
    """
    query = db.query(Ticket).filter(Ticket.status != TicketStatus.CLOSED)
    if assigned_to_agent_id is not None:
        query = query.filter(Ticket.assigned_to_agent_id == assigned_to_agent_id)
    return query.order_by(_PRIORITY_RANK, Ticket.created_at.asc()).limit(limit).all()


def _build_ai_context(db: Session, ticket: Ticket) -> ai_service.TicketContext:
    """Dựng TicketContext để đưa vào ai_service — dùng chung cho việc AI (đề xuất
    lại) mức ưu tiên. Cùng logic build context như ai_draft_service, nhưng tách
    riêng ở đây vì chỉ cần classify, không cần sinh câu trả lời nháp."""
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


def suggest_ticket_priority_ai(db: Session, ticket_id: int) -> Ticket:
    """
    Nhờ AI đánh giá LẠI mức ưu tiên + phân loại cho một ticket (dựa trên toàn bộ
    nội dung + lịch sử tương tác hiện tại), rồi ÁP DỤNG LUÔN kết quả vào
    Ticket.priority/category (khác với luồng AiDraft chỉ lưu gợi ý riêng để agent
    duyệt câu trả lời — ở đây ticket không có "nội dung gửi khách" nên áp dụng
    thẳng là an toàn, agent vẫn có thể tự sửa lại thủ công bất cứ lúc nào).

    Đánh dấu priority_source=AI và ghi log hệ thống để có dấu vết ai/khi nào
    đổi mức ưu tiên.
    """
    ticket = get_ticket_or_404(db, ticket_id)
    context = _build_ai_context(db, ticket)

    try:
        classification = ai_service.classify_and_summarize(context)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Không thể lấy đề xuất ưu tiên từ AI: {exc}",
        ) from exc

    old_priority = ticket.priority.value
    new_priority = classification["suggested_priority"]

    ticket.priority = new_priority
    ticket.priority_source = TicketPrioritySource.AI
    if classification.get("suggested_category"):
        ticket.category = classification["suggested_category"]

    if old_priority != new_priority:
        _log_system_event(
            db,
            ticket.id,
            f"AI đề xuất đổi mức ưu tiên từ '{old_priority}' sang '{new_priority}'.",
        )
    else:
        _log_system_event(
            db, ticket.id, f"AI xác nhận giữ nguyên mức ưu tiên '{new_priority}'."
        )

    db.commit()
    db.refresh(ticket)
    return ticket


def _log_system_event(db: Session, ticket_id: int, content: str) -> None:
    """Ghi 1 dòng lịch sử hệ thống (không commit — caller chịu trách nhiệm commit)."""
    db.add(
        InteractionHistory(
            ticket_id=ticket_id,
            sender_type=SenderType.SYSTEM,
            content=content,
        )
    )


def create_ticket(db: Session, payload: TicketCreate) -> Ticket:
    customer = db.query(Customer).filter(Customer.id == payload.customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy khách hàng id={payload.customer_id}",
        )

    ticket = Ticket(
        customer_id=payload.customer_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        status=TicketStatus.NEW,
        order_id=payload.order_id,
    )
    db.add(ticket)
    db.flush()  # để có ticket.id trước khi ghi log

    _log_system_event(db, ticket.id, "Ticket được tạo mới.")

    db.commit()
    db.refresh(ticket)
    return ticket


def update_ticket(db: Session, ticket_id: int, payload: TicketUpdate) -> Ticket:
    ticket = get_ticket_or_404(db, ticket_id)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ticket, field, value)
    # Nhân viên tự tay đổi priority ở đây -> không còn là gợi ý AI nữa, để
    # frontend hiển thị đúng nhãn "Nhân viên đặt" thay vì "AI đề xuất".
    if "priority" in update_data:
        ticket.priority_source = TicketPrioritySource.MANUAL
    db.commit()
    db.refresh(ticket)
    return ticket


def assign_ticket(db: Session, ticket_id: int, payload: TicketAssign) -> Ticket:
    """Phân công ticket cho một agent. Chỉ chấp nhận user có role agent hoặc manager."""
    ticket = get_ticket_or_404(db, ticket_id)

    agent = db.query(User).filter(User.id == payload.agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy nhân viên id={payload.agent_id}",
        )
    if agent.role not in (UserRole.AGENT, UserRole.MANAGER):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chỉ có thể phân công ticket cho agent hoặc manager",
        )
    if not agent.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tài khoản nhân viên này đã bị vô hiệu hoá",
        )

    ticket.assigned_to_agent_id = agent.id
    # Ticket vừa được phân công thì tự động chuyển sang trạng thái "processing"
    # nếu đang ở trạng thái "new".
    if ticket.status == TicketStatus.NEW:
        ticket.status = TicketStatus.PROCESSING

    _log_system_event(db, ticket.id, f"Ticket được phân công cho agent '{agent.name}'.")

    db.commit()
    db.refresh(ticket)
    return ticket


def unassign_ticket(db: Session, ticket_id: int) -> Ticket:
    """
    Bỏ phân công ticket (gỡ agent hiện tại ra khỏi ticket).
    Hoàn thiện CRUD cho "Phân công" — assign (Create/Update) đã có ở trên,
    đây là phần "xoá" phân công hiện tại.
    """
    ticket = get_ticket_or_404(db, ticket_id)

    if ticket.assigned_to_agent_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticket này hiện chưa được phân công cho ai",
        )

    old_agent = db.query(User).filter(User.id == ticket.assigned_to_agent_id).first()
    old_agent_name = old_agent.name if old_agent else f"id={ticket.assigned_to_agent_id}"

    ticket.assigned_to_agent_id = None
    _log_system_event(db, ticket.id, f"Ticket được bỏ phân công khỏi agent '{old_agent_name}'.")

    db.commit()
    db.refresh(ticket)
    return ticket


def cancel_ticket_by_customer(db: Session, ticket_id: int, customer_id: int) -> Ticket:
    """
    Khách hàng tự huỷ yêu cầu hỗ trợ của chính họ. Khác update_ticket_status()
    (dành cho nhân viên) ở 2 điểm:
      1. Kiểm tra ticket đúng là của customer_id này (không cho huỷ ticket người khác).
      2. Log rõ "khách tự huỷ" thay vì log đổi trạng thái chung chung, để nhân
         viên phân biệt được đây là do khách chủ động, không phải do agent xử lý xong.
    """
    ticket = get_ticket_or_404(db, ticket_id)

    if ticket.customer_id != customer_id:
        # Trả 404 thay vì 403 — không tiết lộ ticket này có tồn tại hay không
        # cho người không sở hữu, cùng nguyên tắc với read_my_ticket_interactions().
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy ticket id={ticket_id}",
        )

    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Yêu cầu này đã được đóng/huỷ trước đó rồi",
        )

    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = datetime.now(timezone.utc)
    _log_system_event(db, ticket.id, "Khách hàng đã tự huỷ yêu cầu này.")

    db.commit()
    db.refresh(ticket)
    return ticket


def update_ticket_status(db: Session, ticket_id: int, payload: TicketStatusUpdate) -> Ticket:
    ticket = get_ticket_or_404(db, ticket_id)

    old_status = ticket.status
    ticket.status = payload.status

    # Ghi/xoá mốc closed_at để tính được thời gian xử lý (xem stats_service.py):
    #   - Chuyển SANG closed lần đầu (hoặc sau khi mở lại) -> ghi nhận thời điểm đóng.
    #   - Mở lại (chuyển RA KHỎI closed) -> xoá mốc cũ, vì ticket đang xử lý lại,
    #     thời gian xử lý "lần đóng trước" không còn phản ánh đúng hiện trạng.
    if payload.status == TicketStatus.CLOSED and old_status != TicketStatus.CLOSED:
        ticket.closed_at = datetime.now(timezone.utc)
    elif payload.status != TicketStatus.CLOSED and old_status == TicketStatus.CLOSED:
        ticket.closed_at = None

    _log_system_event(
        db, ticket.id, f"Trạng thái đổi từ '{old_status.value}' sang '{payload.status.value}'."
    )

    db.commit()
    db.refresh(ticket)
    return ticket


def delete_ticket(db: Session, ticket_id: int) -> None:
    ticket = get_ticket_or_404(db, ticket_id)
    db.delete(ticket)
    db.commit()
