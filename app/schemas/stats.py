"""Pydantic schemas cho các truy vấn thống kê (dashboard tổng quan + hiệu suất agent)."""

from pydantic import BaseModel


class OverviewStatsOut(BaseModel):
    """Thống kê tổng quan toàn hệ thống: số lượng ticket theo trạng thái/ưu tiên."""

    total_tickets: int
    total_customers: int
    total_open_tickets: int  # tổng ticket chưa "closed"
    by_status: dict[str, int]
    by_priority: dict[str, int]


class AgentPerformanceOut(BaseModel):
    """Hiệu suất xử lý ticket của từng agent."""

    agent_id: int
    agent_name: str
    total_assigned: int  # tổng số ticket từng/đang được gán cho agent này
    total_closed: int    # trong số đó, đã đóng (closed)
    total_open: int      # trong số đó, đang mở (chưa closed) — càng cao càng đang tải nhiều việc


class AgentProcessingTimeOut(BaseModel):
    """Thời gian xử lý trung bình của 1 agent (chỉ tính ticket đã closed)."""

    agent_id: int
    agent_name: str
    closed_count: int
    average_processing_hours: float


class ProcessingTimeStatsOut(BaseModel):
    """
    Thống kê thời gian xử lý ticket (created_at -> closed_at), chỉ tính trên
    các ticket đã closed. average_processing_hours = None nếu chưa có ticket
    nào được đóng.
    """

    total_closed_tickets: int
    average_processing_hours: float | None
    by_priority_avg_hours: dict[str, float]
    by_agent: list[AgentProcessingTimeOut]
