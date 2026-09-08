"""
API routes: /api/v1/stats — Truy vấn thống kê.

  GET /api/v1/stats/overview        : tổng quan ticket theo trạng thái/ưu tiên (mọi nhân viên xem được)
  GET /api/v1/stats/agents          : hiệu suất từng agent (chỉ admin/manager — dữ liệu đánh giá nhân sự)
  GET /api/v1/stats/processing-time : thời gian xử lý trung bình theo ưu tiên/agent (mọi nhân viên xem được)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.stats import AgentPerformanceOut, OverviewStatsOut, ProcessingTimeStatsOut
from app.services import stats_service
from app.services.auth_service import get_current_user, require_roles

router = APIRouter(prefix="/stats", tags=["Statistics"])


@router.get("/overview", response_model=OverviewStatsOut)
def get_overview_stats(
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Tổng số ticket/khách hàng + phân bổ theo trạng thái và mức ưu tiên."""
    return stats_service.get_overview_stats(db)


@router.get(
    "/agents",
    response_model=list[AgentPerformanceOut],
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def get_agent_performance(db: Session = Depends(get_db)):
    """
    Hiệu suất xử lý ticket của từng agent (tổng số đã gán / đã đóng / đang mở).
    Giới hạn admin/manager vì đây là dữ liệu mang tính đánh giá nhân sự.
    """
    return stats_service.get_agent_performance(db)


@router.get("/processing-time", response_model=ProcessingTimeStatsOut)
def get_processing_time_stats(
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Thời gian xử lý trung bình (created_at -> closed_at) của các ticket đã
    đóng: tổng quan, theo mức ưu tiên, và theo từng agent.
    """
    return stats_service.get_processing_time_stats(db)
