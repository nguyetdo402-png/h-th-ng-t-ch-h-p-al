"""
Test hồi quy cho lỗi: "khách hàng sau khi thoát ra (đóng tab/trình duyệt) sẽ
không nhắn lại được cho shop nữa".

Nguyên nhân gốc: widget chat công khai lưu access_token của ticket ở
localStorage trình duyệt (thiết kế để nhúng iframe vào website bán hàng
thật) — khi khách đóng tab/trình duyệt, phiên này có thể bị mất, và khách
không còn cách nào nhắn tiếp vào ticket cũ.

Fix: cho phép khách hàng ĐÃ ĐĂNG NHẬP tài khoản (không phụ thuộc localStorage
của widget) gửi thêm tin nhắn vào ticket của chính mình qua
POST /api/v1/customer-auth/me/tickets/{id}/interactions — kể cả khi ticket
đã "closed" (tự động mở lại thay vì bắt tạo ticket mới, giữ liền mạch lịch sử).
"""

from app.models.customer import Customer
from app.models.ticket import TicketStatus


def _register_and_login(client, email: str, password: str = "MatKhau123!"):
    resp = client.post(
        "/api/v1/customer-auth/register",
        json={"name": "Khach Hang", "email": email, "password": password},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_customer_can_reply_after_losing_widget_session(client, db_session, make_ticket):
    """Khách vẫn nhắn tiếp được vào ticket ĐANG MỞ dù không còn access_token cũ."""
    ticket = make_ticket(status=TicketStatus.PROCESSING)
    customer = db_session.query(Customer).filter(Customer.id == ticket.customer_id).first()

    headers = _register_and_login(client, customer.email)

    resp = client.post(
        f"/api/v1/customer-auth/me/tickets/{ticket.id}/interactions",
        json={"content": "Tôi muốn hỏi thêm về yêu cầu này"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["sender_type"] == "customer"

    db_session.refresh(ticket)
    assert ticket.status == TicketStatus.PROCESSING  # ticket đang mở -> giữ nguyên trạng thái


def test_customer_reply_reopens_closed_ticket(client, db_session, make_ticket):
    """Nhắn tin vào ticket ĐÃ ĐÓNG -> tự động mở lại (về 'new') thay vì chặn khách."""
    ticket = make_ticket(status=TicketStatus.CLOSED)
    customer = db_session.query(Customer).filter(Customer.id == ticket.customer_id).first()

    headers = _register_and_login(client, customer.email)

    resp = client.post(
        f"/api/v1/customer-auth/me/tickets/{ticket.id}/interactions",
        json={"content": "Ticket đã đóng nhưng tôi vẫn cần hỗ trợ thêm"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    db_session.refresh(ticket)
    assert ticket.status == TicketStatus.NEW


def test_customer_cannot_reply_to_others_ticket(client, db_session, make_ticket):
    """Không cho khách A nhắn vào ticket của khách B (404, không lộ ticket có tồn tại)."""
    ticket = make_ticket()  # thuộc về 1 customer khác

    headers = _register_and_login(client, "nguoi-khac@example.com")

    resp = client.post(
        f"/api/v1/customer-auth/me/tickets/{ticket.id}/interactions",
        json={"content": "Thử nhắn vào ticket không phải của mình"},
        headers=headers,
    )
    assert resp.status_code == 404
