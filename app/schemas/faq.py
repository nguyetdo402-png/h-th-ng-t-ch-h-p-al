"""Pydantic schemas cho FaqEntry (câu trả lời mẫu theo từ khóa)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_keywords(raw: str) -> str:
    """
    Chuẩn hoá chuỗi từ khóa: tách theo dấu phẩy, bỏ khoảng trắng thừa, bỏ mục
    rỗng, rồi nối lại bằng ", " — đảm bảo dữ liệu lưu trong DB luôn nhất quán
    bất kể admin gõ cách nhau kiểu gì ("size,đổi trả" hay "size , đổi trả").
    """
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        raise ValueError("Cần ít nhất 1 từ khóa")
    return ", ".join(parts)


class FaqBase(BaseModel):
    question: str = Field(min_length=1, max_length=255)
    answer: str = Field(min_length=1)
    keywords: str = Field(
        min_length=1,
        max_length=500,
        description="Các từ khóa liên quan, cách nhau bởi dấu phẩy. VD: 'size, đổi size, bảng size'",
    )
    is_active: bool = True

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, v: str) -> str:
        return _normalize_keywords(v)


class FaqCreate(FaqBase):
    pass


class FaqUpdate(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=255)
    answer: str | None = Field(default=None, min_length=1)
    keywords: str | None = Field(default=None, min_length=1, max_length=500)
    is_active: bool | None = None

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, v: str | None) -> str | None:
        return _normalize_keywords(v) if v is not None else v


class FaqOut(FaqBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class FaqMatchOut(BaseModel):
    """FAQ khớp với nội dung ticket, kèm từ khóa nào đã khớp — để agent hiểu vì sao được gợi ý."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    answer: str
    matched_keywords: list[str]
