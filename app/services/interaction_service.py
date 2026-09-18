"""Business logic cho InteractionHistory: ghi và đọc lịch sử hội thoại của ticket."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.interaction_history import InteractionHistory, SenderType
from app.models.ticket import TicketStatus
from app.schemas.interaction_history import InteractionCreate, InteractionUpdate
from app.services.ticket_service import get_ticket_or_404


def get_interactions(db: Session, ticket_id: int) -> list[InteractionHistory]:
    """Trả về toàn bộ lịch sử hội thoại của 1 ticket, sắp theo thời gian tăng dần."""
    get_ticket_or_404(db, ticket_id)  # đảm bảo ticket tồn tại, raise 404 nếu không
    return (
        db.query(InteractionHistory)
        .filter(InteractionHistory.ticket_id == ticket_id)
        .order_by(InteractionHistory.created_at.asc())
        .all()
    )


def get_interaction_or_404(db: Session, ticket_id: int, interaction_id: int) -> InteractionHistory:
    interaction = (
        db.query(InteractionHistory)
        .filter(
            InteractionHistory.id == interaction_id,
            InteractionHistory.ticket_id == ticket_id,
        )
        .first()
    )
    if not interaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy bình luận id={interaction_id} trong ticket #{ticket_id}",
        )
    return interaction


def create_interaction(
    db: Session, ticket_id: int, payload: InteractionCreate
) -> InteractionHistory:
    """
    Ghi thêm 1 mục vào lịch sử hội thoại do NHÂN VIÊN gửi (trả lời khách, ghi
    chú nội bộ...). Luôn ghi cứng sender_type=AGENT — nhân viên không được
    phép giả danh khách hàng hay hệ thống. Tin nhắn thật của khách hàng chỉ
    được ghi qua luồng chat công khai riêng (public_chat_service), và log hệ
    thống (assign/đổi trạng thái/AI...) chỉ do chính server tự ghi ở nơi khác.
    """
    get_ticket_or_404(db, ticket_id)

    interaction = InteractionHistory(
        ticket_id=ticket_id,
        sender_type=SenderType.AGENT,
        content=payload.content,
    )
    db.add(interaction)
    db.commit()
    db.refresh(interaction)
    return interaction


def update_interaction_by_customer(
    db: Session, ticket_id: int, interaction_id: int, customer_id: int, payload: InteractionUpdate
) -> InteractionHistory:
    """
    Khách hàng tự sửa lại NỘI DUNG TIN NHẮN CỦA CHÍNH MÌNH. Chặt hơn
    update_interaction() dành cho nhân viên ở 2 điểm:
      1. Chỉ được sửa tin nhắn có sender_type=customer (không đụng được vào
         tin nhắn của agent hay nhật ký hệ thống — kể cả khi chúng nằm trong
         ticket của chính họ).
      2. Ghi thêm 1 dòng hệ thống để nhân viên biết khách đã sửa lại nội dung,
         tránh nhầm lẫn khi đọc lại lịch sử hội thoại về sau.
    Ticket không thuộc về customer_id -> 404 (không tiết lộ ticket có tồn tại).
    """
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.customer_id != customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy ticket id={ticket_id}",
        )

    interaction = get_interaction_or_404(db, ticket_id, interaction_id)
    if interaction.sender_type != SenderType.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn chỉ được sửa tin nhắn do chính mình gửi",
        )

    interaction.content = payload.content
    db.add(
        InteractionHistory(
            ticket_id=ticket_id,
            sender_type=SenderType.SYSTEM,
            content="Khách hàng đã chỉnh sửa lại một tin nhắn.",
        )
    )
    db.commit()
    db.refresh(interaction)
    return interaction


def delete_interaction_by_customer(
    db: Session, ticket_id: int, interaction_id: int, customer_id: int
) -> None:
    """Giống update_interaction_by_customer() ở trên, nhưng cho hành động xoá."""
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.customer_id != customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy ticket id={ticket_id}",
        )

    interaction = get_interaction_or_404(db, ticket_id, interaction_id)
    if interaction.sender_type != SenderType.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn chỉ được xoá tin nhắn do chính mình gửi",
        )

    db.delete(interaction)
    db.add(
        InteractionHistory(
            ticket_id=ticket_id,
            sender_type=SenderType.SYSTEM,
            content="Khách hàng đã xoá một tin nhắn.",
        )
    )
    db.commit()


def create_message_by_customer(
    db: Session, ticket_id: int, customer_id: int, payload: InteractionCreate
) -> InteractionHistory:
    """
    Khách hàng ĐÃ ĐĂNG NHẬP (customer-auth) gửi thêm 1 tin nhắn vào ticket của
    chính mình — dùng cho trang "Tài khoản của tôi", KHÔNG phụ thuộc vào phiên
    chat ẩn danh lưu ở localStorage của widget (vốn dễ mất khi khách đóng
    tab/trình duyệt, đặc biệt khi widget được nhúng iframe ở website khác).
    Đây là lối đi thay thế để khách vẫn nhắn lại được ngay cả khi đã mất phiên
    chat cũ, miễn là còn nhớ email/mật khẩu tài khoản.

    Nếu ticket đang ở trạng thái "closed", TỰ ĐỘNG mở lại (chuyển về "new")
    thay vì tạo ticket mới — khác với luồng chat công khai ẩn danh (tạo ticket
    mới khi ticket cũ đã đóng) vì ở đây khách đã CHỦ ĐỘNG chọn đúng ticket này
    để nhắn tiếp, nên ưu tiên giữ liền mạch lịch sử hội thoại thay vì tách ra
    ticket mới.
    """
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.customer_id != customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy ticket id={ticket_id}",
        )

    if ticket.status == TicketStatus.CLOSED:
        ticket.status = TicketStatus.NEW
        db.add(
            InteractionHistory(
                ticket_id=ticket_id,
                sender_type=SenderType.SYSTEM,
                content=(
                    "Khách hàng đã nhắn tin trở lại sau khi ticket được đóng — "
                    "ticket được tự động mở lại (trạng thái 'Mới') để admin phân công xử lý."
                ),
            )
        )
    else:
        db.add(
            InteractionHistory(
                ticket_id=ticket_id,
                sender_type=SenderType.SYSTEM,
                content="Khách hàng vừa gửi thêm tin nhắn mới trong hội thoại này.",
            )
        )

    interaction = InteractionHistory(
        ticket_id=ticket_id,
        sender_type=SenderType.CUSTOMER,
        content=payload.content,
    )
    db.add(interaction)
    db.commit()
    db.refresh(interaction)
    return interaction


def update_interaction(
    db: Session, ticket_id: int, interaction_id: int, payload: InteractionUpdate
) -> InteractionHistory:
    """
    Sửa nội dung một mục lịch sử (vd: sửa lỗi chính tả trong ghi chú).
    Không cho phép sửa nhật ký hệ thống (sender_type=system) để bảo toàn tính
    trung thực của audit trail (log đổi trạng thái, log phân công, ...).
    """
    interaction = get_interaction_or_404(db, ticket_id, interaction_id)
    if interaction.sender_type == SenderType.SYSTEM:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể sửa nhật ký hệ thống",
        )
    interaction.content = payload.content
    db.commit()
    db.refresh(interaction)
    return interaction


def delete_interaction(db: Session, ticket_id: int, interaction_id: int) -> None:
    """
    Xoá một mục lịch sử. Cũng không cho xoá nhật ký hệ thống, vì lý do tương tự
    update_interaction() ở trên — đây là dấu vết audit, không phải nội dung
    người dùng tự do chỉnh sửa.
    """
    interaction = get_interaction_or_404(db, ticket_id, interaction_id)
    if interaction.sender_type == SenderType.SYSTEM:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể xoá nhật ký hệ thống (cần bảo toàn lịch sử audit)",
        )
    db.delete(interaction)
    db.commit()
