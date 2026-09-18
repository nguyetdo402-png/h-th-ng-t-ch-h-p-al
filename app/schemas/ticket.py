"""Pydantic schemas cho Ticket: tạo mới, phân công agent, cập nhật trạng thái."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ticket import TicketPriority, TicketPrioritySource, TicketStatus
from app.schemas.customer import CustomerOut
from app.schemas.order import OrderOut
from app.schemas.user import UserOut


class TicketCreate(BaseModel):
    customer_id: int
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    priority: TicketPriority = TicketPriority.MEDIUM
    # Optional: ticket liên quan tới đơn hàng nào (vd: khiếu nại giao hàng, đổi trả...).
    order_id: int | None = None


class TicketUpdate(BaseModel):
    """Cập nhật thông tin chung của ticket (không bao gồm assign/status — có endpoint riêng)."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    priority: TicketPriority | None = None


class TicketAssign(BaseModel):
    """Payload để phân công ticket cho một agent."""

    agent_id: int


class TicketStatusUpdate(BaseModel):
    """Payload để cập nhật trạng thái xử lý ticket."""

    status: TicketStatus


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    title: str
    description: str
    priority: TicketPriority
    priority_source: TicketPrioritySource
    status: TicketStatus
    category: str | None = None
    assigned_to_agent_id: int | None
    order_id: int | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None


class TicketDetailOut(TicketOut):
    """Bản chi tiết, kèm thông tin khách hàng và agent được gán (dùng cho trang chi tiết)."""

    customer: CustomerOut
    assigned_agent: UserOut | None = None
    order: OrderOut | None = None