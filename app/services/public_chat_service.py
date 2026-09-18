"""
Business logic cho luồng chat công khai (khách hàng nhắn tin, không cần đăng nhập).

Khi khách gửi tin nhắn ĐẦU TIÊN (tạo ticket mới), hệ thống sẽ tự động, theo thứ tự:
    1. Tìm hoặc tạo Customer theo email.
    2. Tạo Ticket mới (trạng thái "new", CHƯA gán agent nào).
    3. Ghi tin nhắn của khách vào InteractionHistory (sender_type=customer).
    4. Tự động chào khách: ghi 1 tin nhắn chào (sender_type=bot) — khách thấy phản hồi
       ngay lập tức dù chưa có nhân viên nào xử lý.
    5. Gọi AI để phân loại nhóm vấn đề + mức độ ưu tiên, rồi TỰ ĐỘNG set thẳng vào
       Ticket.category / Ticket.priority (khác với luồng "AI Draft" ở ai_draft_service,
       vốn chỉ gợi ý câu trả lời và luôn cần agent duyệt trước khi gửi khách — ở đây AI
       chỉ quyết định việc PHÂN LOẠI/ĐỘ ƯU TIÊN nội bộ, không tự soạn nội dung gửi khách).
    6. Ticket được để ở trạng thái "new", chưa gán agent -> hiển thị trong hàng đợi
       chung để admin/manager xem và phân công (assign) cho nhân viên phù hợp.

Nếu khách gửi tin nhắn TIẾP THEO kèm ticket_id của 1 ticket đang mở, hệ thống chỉ
ghi thêm tin nhắn vào lịch sử hội thoại đó (không lặp lại bước chào/phân loại).
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.models.interaction_history import InteractionHistory, SenderType
from app.models.order import Order
from app.models.ticket import Ticket, TicketPriority, TicketPrioritySource, TicketStatus
from app.schemas.public_chat import PublicChatMessageIn, PublicMessageOut, PublicTicketStateOut
from app.services import ai_service, customer_service, upload_service

logger = logging.getLogger(__name__)

_MAX_TITLE_LEN = 80


def _build_greeting() -> str:
    # Câu chào cố định, hiển thị ngay khi khách vào khung chat (tin nhắn đầu
    # tiên do "AI/bot" gửi tự động). Thông tin mã ticket + trạng thái đã được
    # hiển thị riêng trên header của khung chat nên không cần lặp lại ở đây.
    return "Anna Store Xin Chào! Shop có thể hỗ trợ gì cho bạn không ạ?"


def _build_ticket_context(ticket: Ticket) -> ai_service.TicketContext:
    interactions = sorted(ticket.interactions, key=lambda i: i.created_at)
    return {
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority.value,
        "status": ticket.status.value,
        "interactions": [
            {"sender_type": i.sender_type.value, "content": i.content} for i in interactions
        ],
    }


def _auto_classify_new_ticket(db: Session, ticket: Ticket) -> None:
    """
    Gọi AI để phân loại nhóm vấn đề + mức ưu tiên, rồi set thẳng vào ticket.
    Nếu AI lỗi (thiếu API key, lỗi mạng...), KHÔNG chặn luồng: ticket vẫn được
    tạo và đẩy vào hàng đợi với mức ưu tiên mặc định 'medium', chỉ ghi log hệ
    thống để admin biết là chưa phân loại được tự động.
    """
    try:
        classification = ai_service.classify_and_summarize(_build_ticket_context(ticket))
        ticket.priority = TicketPriority(classification["suggested_priority"])
        ticket.priority_source = TicketPrioritySource.AI
        ticket.category = classification["suggested_category"]
        db.add(
            InteractionHistory(
                ticket_id=ticket.id,
                sender_type=SenderType.SYSTEM,
                content=(
                    f"AI đã tự động phân loại: nhóm '{classification['suggested_category']}', "
                    f"mức ưu tiên '{classification['suggested_priority']}'. "
                    "Ticket đã được đẩy vào hàng chờ để admin phân công nhân viên xử lý."
                ),
            )
        )
    except (RuntimeError, ValueError) as exc:
        logger.warning("Không thể tự động phân loại ticket #%s bằng AI: %s", ticket.id, exc)
        db.add(
            InteractionHistory(
                ticket_id=ticket.id,
                sender_type=SenderType.SYSTEM,
                content=(
                    "Không thể tự động phân loại bằng AI (lỗi cấu hình hoặc kết nối AI). "
                    "Ticket vẫn được đẩy vào hàng chờ với mức ưu tiên mặc định 'medium' "
                    "để admin phân công nhân viên xử lý."
                ),
            )
        )


def _get_ticket_by_token(db: Session, ticket_id: int, access_token: str) -> Ticket | None:
    """
    Tra cứu ticket bằng (ticket_id + access_token) thay vì (ticket_id +
    customer_id/email). access_token là chuỗi ngẫu nhiên không đoán được,
    nên việc khớp đúng cặp này gần như chỉ người đang giữ mã (khách sở hữu
    ticket) mới làm được — khác với email/ticket_id vốn có thể bị đoán.
    """
    return (
        db.query(Ticket)
        .filter(Ticket.id == ticket_id, Ticket.access_token == access_token)
        .first()
    )


def submit_message(db: Session, payload: PublicChatMessageIn) -> Ticket:
    """Điểm vào chính của luồng chat công khai: xử lý 1 tin nhắn khách gửi lên."""
    customer = customer_service.get_or_create_customer_by_email(
        db, payload.name, payload.email, payload.phone
    )

    ticket: Ticket | None = None
    if payload.ticket_id is not None and payload.access_token:
        ticket = _get_ticket_by_token(db, payload.ticket_id, payload.access_token)
        if ticket is not None and ticket.customer_id != customer.id:
            # access_token đúng nhưng email đổi khác khách sở hữu ban đầu ->
            # không tin tưởng, coi như yêu cầu mới (tránh nhầm/giả mạo).
            ticket = None
        if ticket is not None and ticket.status == TicketStatus.CLOSED:
            # Ticket cũ đã đóng -> không nối vào nữa, coi như yêu cầu mới.
            ticket = None

    is_new_ticket = ticket is None

    if is_new_ticket:
        message_text = payload.message.strip()
        title = message_text[:_MAX_TITLE_LEN] or "Yêu cầu hỗ trợ mới"

        # Nếu khách chọn 1 đơn hàng, xác thực đơn đó đúng là của khách này
        # (tránh khách A nhắc nhầm/cố tình gắn đơn của khách B).
        order_id = None
        if payload.order_id is not None:
            order = (
                db.query(Order)
                .filter(Order.id == payload.order_id, Order.customer_id == customer.id)
                .first()
            )
            if order:
                order_id = order.id

        ticket = Ticket(
            customer_id=customer.id,
            title=title,
            description=message_text,
            priority=TicketPriority.MEDIUM,
            status=TicketStatus.NEW,
            order_id=order_id,
        )
        db.add(ticket)
        db.flush()  # có ticket.id để ghi các interaction bên dưới

    db.add(
        InteractionHistory(
            ticket_id=ticket.id,
            sender_type=SenderType.CUSTOMER,
            content=payload.message.strip(),
        )
    )

    if is_new_ticket:
        db.add(
            InteractionHistory(
                ticket_id=ticket.id,
                sender_type=SenderType.BOT,
                content=_build_greeting(),
            )
        )
        db.flush()
        _auto_classify_new_ticket(db, ticket)
    else:
        db.add(
            InteractionHistory(
                ticket_id=ticket.id,
                sender_type=SenderType.SYSTEM,
                content="Khách hàng vừa gửi thêm tin nhắn mới trong hội thoại này.",
            )
        )

    db.commit()
    db.refresh(ticket)
    return ticket


def get_conversation(db: Session, ticket_id: int, access_token: str) -> Ticket:
    """
    Lấy lại trạng thái hội thoại của 1 ticket, dùng để widget khách poll tin nhắn mới.
    Yêu cầu đúng access_token của ticket đó — mã ngẫu nhiên không đoán được,
    an toàn hơn nhiều so với việc chỉ yêu cầu email (email không phải bí mật
    và có thể trùng/đoán được, còn ticket_id là số tự tăng dễ dò).
    """
    ticket = _get_ticket_by_token(db, ticket_id, access_token)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy hội thoại (sai ticket_id hoặc mã tra cứu).",
        )
    return ticket


def submit_attachment(
    db: Session, ticket_id: int, access_token: str, file: UploadFile
) -> Ticket:
    """
    Khách gửi kèm 1 file ảnh/video vào hội thoại đang mở. Yêu cầu ticket đã
    tồn tại (khách phải nhắn tin lần đầu trước để có ticket_id + access_token)
    — không cho tạo ticket mới chỉ bằng file, tránh spam file rác từ người
    không có ý định liên hệ hỗ trợ thật sự.
    """
    ticket = _get_ticket_by_token(db, ticket_id, access_token)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy hội thoại (sai ticket_id hoặc mã tra cứu).",
        )
    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Yêu cầu này đã được đóng, không thể gửi thêm file. Vui lòng tạo yêu cầu mới.",
        )

    attachment_url, attachment_type, original_name = upload_service.save_chat_attachment(file)

    label = "hình ảnh" if attachment_type.value == "image" else "video"
    db.add(
        InteractionHistory(
            ticket_id=ticket.id,
            sender_type=SenderType.CUSTOMER,
            content=f"[Đã gửi 1 {label}]",
            attachment_url=attachment_url,
            attachment_type=attachment_type,
            attachment_filename=original_name,
        )
    )
    db.add(
        InteractionHistory(
            ticket_id=ticket.id,
            sender_type=SenderType.SYSTEM,
            content=f"Khách hàng vừa gửi thêm {label} trong hội thoại này.",
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


def to_state_out(ticket: Ticket) -> PublicTicketStateOut:
    # Tin nhắn "system" (audit log nội bộ: lỗi phân loại AI, phân công agent,
    # thông báo có tin nhắn mới...) CHỈ dành cho nội bộ (hiện ở dashboard nhân
    # viên, nếu bật) — không bao giờ trả về cho khách hàng qua API công khai
    # này, để tránh lộ thông tin vận hành nội bộ (vd: tên agent được phân công).
    interactions = sorted(
        (i for i in ticket.interactions if i.sender_type != SenderType.SYSTEM),
        key=lambda i: i.created_at,
    )
    return PublicTicketStateOut(
        ticket_id=ticket.id,
        access_token=ticket.access_token,
        status=ticket.status,
        priority=ticket.priority,
        category=ticket.category,
        order_id=ticket.order_id,
        messages=[PublicMessageOut.model_validate(i) for i in interactions],
    )
