"""
Business logic cho các truy vấn thống kê:
  - get_overview_stats(): tổng quan số ticket theo trạng thái/ưu tiên toàn hệ thống.
  - get_agent_performance(): hiệu suất xử lý ticket của từng agent.
  - get_processing_time_stats(): thời gian xử lý (từ lúc tạo tới lúc đóng),
    tổng quan + theo mức ưu tiên + theo agent.

Các hàm ở đây chỉ đọc dữ liệu (không ghi), dùng group-by ở tầng SQL để tránh
vấn đề N+1 query khi số lượng ticket/agent lớn.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.user import User, UserRole


def get_overview_stats(db: Session, assigned_to_agent_id: int | None = None) -> dict:
    """
    Tổng số ticket/khách hàng, và phân bổ ticket theo trạng thái + mức ưu tiên.

    assigned_to_agent_id: nếu truyền vào (agent xem trang của chính mình), chỉ
    tính trên các ticket đang được gán cho agent đó — đồng bộ với cách
    list_tickets/get_priority_queue giới hạn phạm vi cho agent. None (mặc định,
    dùng cho admin/manager) nghĩa là tính trên toàn bộ ticket.
    """
    ticket_query = db.query(Ticket)
    if assigned_to_agent_id is not None:
        ticket_query = ticket_query.filter(Ticket.assigned_to_agent_id == assigned_to_agent_id)

    total_tickets = ticket_query.with_entities(func.count(Ticket.id)).scalar() or 0

    # total_customers luôn tính toàn hệ thống — số ticket bị lọc theo agent
    # không đồng nghĩa với "số khách hàng của agent đó".
    total_customers = db.query(func.count(Customer.id)).scalar() or 0

    # Khởi tạo sẵn tất cả giá trị enum = 0, để FE không phải tự xử lý key bị thiếu
    # (ví dụ chưa có ticket "waiting" nào thì vẫn trả về waiting: 0 thay vì bỏ qua key).
    by_status = {s.value: 0 for s in TicketStatus}
    status_counts_query = ticket_query.with_entities(Ticket.status, func.count(Ticket.id)).group_by(
        Ticket.status
    )
    for status_value, count in status_counts_query.all():
        by_status[status_value.value] = count

    by_priority = {p.value: 0 for p in TicketPriority}
    priority_counts_query = ticket_query.with_entities(
        Ticket.priority, func.count(Ticket.id)
    ).group_by(Ticket.priority)
    for priority_value, count in priority_counts_query.all():
        by_priority[priority_value.value] = count

    total_open_tickets = total_tickets - by_status.get(TicketStatus.CLOSED.value, 0)

    return {
        "total_tickets": total_tickets,
        "total_customers": total_customers,
        "total_open_tickets": total_open_tickets,
        "by_status": by_status,
        "by_priority": by_priority,
    }


def get_agent_performance(db: Session) -> list[dict]:
    """
    Với mỗi agent: tổng số ticket từng được gán, số đã đóng, số đang mở.
    Dùng 2 query group-by (KHÔNG lặp query theo từng agent) để tránh N+1.
    """
    agents = db.query(User).filter(User.role == UserRole.AGENT).order_by(User.name).all()

    total_by_agent = dict(
        db.query(Ticket.assigned_to_agent_id, func.count(Ticket.id))
        .filter(Ticket.assigned_to_agent_id.isnot(None))
        .group_by(Ticket.assigned_to_agent_id)
        .all()
    )
    closed_by_agent = dict(
        db.query(Ticket.assigned_to_agent_id, func.count(Ticket.id))
        .filter(
            Ticket.assigned_to_agent_id.isnot(None),
            Ticket.status == TicketStatus.CLOSED,
        )
        .group_by(Ticket.assigned_to_agent_id)
        .all()
    )

    results = []
    for agent in agents:
        total_assigned = total_by_agent.get(agent.id, 0)
        total_closed = closed_by_agent.get(agent.id, 0)
        results.append(
            {
                "agent_id": agent.id,
                "agent_name": agent.name,
                "total_assigned": total_assigned,
                "total_closed": total_closed,
                "total_open": total_assigned - total_closed,
            }
        )

    # Sắp xếp theo số ticket đang mở giảm dần -> thấy ngay ai đang tải nhiều việc nhất.
    results.sort(key=lambda r: r["total_open"], reverse=True)
    return results


def get_processing_time_stats(db: Session) -> dict:
    """
    Thời gian xử lý ticket = khoảng thời gian từ lúc tạo (created_at) tới lúc
    đóng (closed_at) — chỉ tính được với các ticket ĐÃ closed (closed_at khác
    NULL). Tính trung bình tổng quan + theo mức ưu tiên + theo agent.

    Tính bằng Python (thay vì hàm ngày-giờ đặc thù của từng DB như julianday()
    của SQLite hay EXTRACT(EPOCH...) của PostgreSQL) để code không phụ thuộc
    loại DB đang dùng — khớp định hướng "dễ nâng cấp PostgreSQL" của dự án.
    Số lượng ticket closed thường không quá lớn nên chi phí này chấp nhận được;
    nếu sau này dữ liệu rất lớn, có thể chuyển phần tính trung bình xuống SQL.
    """
    closed_tickets = (
        db.query(Ticket.priority, Ticket.assigned_to_agent_id, Ticket.created_at, Ticket.closed_at)
        .filter(Ticket.closed_at.isnot(None))
        .all()
    )

    by_priority_val = {p.value: 0 for p in TicketPriority}

    if not closed_tickets:
        return {
            "total_closed_tickets": 0,
            "average_processing_hours": None,
            "by_priority_avg_hours": by_priority_val,
            "by_agent": [],
        }

    def _hours(created_at, closed_at) -> float:
        return (closed_at - created_at).total_seconds() / 3600

    all_durations = [_hours(row.created_at, row.closed_at) for row in closed_tickets]
    overall_avg = sum(all_durations) / len(all_durations)

    priority_durations: dict[str, list[float]] = {p.value: [] for p in TicketPriority}
    agent_durations: dict[int, list[float]] = {}

    for row in closed_tickets:
        duration = _hours(row.created_at, row.closed_at)
        priority_durations[row.priority.value].append(duration)
        if row.assigned_to_agent_id is not None:
            agent_durations.setdefault(row.assigned_to_agent_id, []).append(duration)

    by_priority_avg_hours = {
        priority: (round(sum(values) / len(values), 2) if values else 0)
        for priority, values in priority_durations.items()
    }

    agent_names = dict(
        db.query(User.id, User.name).filter(User.id.in_(agent_durations.keys())).all()
    )
    by_agent = [
        {
            "agent_id": agent_id,
            "agent_name": agent_names.get(agent_id, f"id={agent_id}"),
            "closed_count": len(values),
            "average_processing_hours": round(sum(values) / len(values), 2),
        }
        for agent_id, values in agent_durations.items()
    ]
    by_agent.sort(key=lambda r: r["average_processing_hours"])

    return {
        "total_closed_tickets": len(closed_tickets),
        "average_processing_hours": round(overall_avg, 2),
        "by_priority_avg_hours": by_priority_avg_hours,
        "by_agent": by_agent,
    }
