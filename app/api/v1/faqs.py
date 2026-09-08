"""
API routes: /api/v1/faqs — Quản lý câu trả lời mẫu (FAQ) theo từ khóa.

Phân quyền:
- Xem (list/detail): mọi user đã đăng nhập — agent cần đọc để tự tra cứu khi
  xử lý ticket, không chỉ dùng ngầm qua AI.
- Tạo/sửa/xóa: chỉ admin, manager — đây là chính sách chính thức của cửa
  hàng, không để agent tự ý thêm/sửa.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.faq import FaqCreate, FaqOut, FaqUpdate
from app.services import faq_service
from app.services.auth_service import get_current_user, require_roles

router = APIRouter(prefix="/faqs", tags=["FAQ"])


@router.get("", response_model=list[FaqOut])
def list_faqs(
    active_only: bool = Query(False, description="Chỉ lấy FAQ đang bật (is_active=true)"),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return faq_service.get_faqs(db, active_only=active_only)


@router.get("/{faq_id}", response_model=FaqOut)
def get_faq(faq_id: int, db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    return faq_service.get_faq_or_404(db, faq_id)


@router.post(
    "",
    response_model=FaqOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def create_faq(payload: FaqCreate, db: Session = Depends(get_db)):
    return faq_service.create_faq(db, payload)


@router.put(
    "/{faq_id}",
    response_model=FaqOut,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def update_faq(faq_id: int, payload: FaqUpdate, db: Session = Depends(get_db)):
    return faq_service.update_faq(db, faq_id, payload)


@router.delete(
    "/{faq_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("admin", "manager"))],
)
def delete_faq(faq_id: int, db: Session = Depends(get_db)):
    faq_service.delete_faq(db, faq_id)
