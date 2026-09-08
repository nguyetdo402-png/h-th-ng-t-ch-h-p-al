"""Pydantic schemas cho AiDraft (gợi ý AI: phân loại + priority + câu trả lời nháp)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AiDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    suggested_category: str | None
    suggested_priority: str | None
    draft_response: str
    is_approved: bool
    created_at: datetime
    approved_at: datetime | None


class AiDraftApprove(BaseModel):
    """
    Payload khi agent bấm "Duyệt" draft.
    edited_response: nếu agent có chỉnh sửa nội dung trước khi duyệt, gửi bản đã sửa
    vào đây; nếu để trống, hệ thống dùng nguyên văn draft_response do AI sinh ra.
    """

    edited_response: str | None = Field(default=None, min_length=1)
