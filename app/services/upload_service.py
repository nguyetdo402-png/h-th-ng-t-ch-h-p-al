"""
Service dùng chung: nhận 1 UploadFile (ảnh/video) từ client, kiểm tra hợp lệ
(loại file, dung lượng) rồi lưu xuống settings.UPLOAD_DIR với tên file ngẫu
nhiên (tránh trùng/ghi đè và tránh lộ tên file gốc ra URL công khai).

Tách riêng khỏi public_chat_service để sau này agent/admin cũng có thể tái sử
dụng (vd: agent gửi kèm ảnh hướng dẫn cho khách) mà không phải lặp lại logic.
"""

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.models.interaction_history import AttachmentType

# Đuôi file được whitelist theo loại — CHỈ dựa vào content-type của trình
# duyệt gửi lên là không đủ an toàn (có thể giả mạo), nên đối chiếu thêm với
# đuôi file thực tế trước khi chấp nhận.
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v"}


def _detect_attachment_type(filename: str, content_type: str | None) -> AttachmentType:
    ext = Path(filename or "").suffix.lower()
    is_image_ct = bool(content_type) and content_type.startswith("image/")
    is_video_ct = bool(content_type) and content_type.startswith("video/")

    if ext in _IMAGE_EXTENSIONS and (is_image_ct or not content_type):
        return AttachmentType.IMAGE
    if ext in _VIDEO_EXTENSIONS and (is_video_ct or not content_type):
        return AttachmentType.VIDEO

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Chỉ chấp nhận file ảnh (jpg, png, gif, webp) hoặc video (mp4, webm, mov). "
            f"File '{filename}' không đúng định dạng cho phép."
        ),
    )


def save_chat_attachment(file: UploadFile) -> tuple[str, AttachmentType, str]:
    """
    Kiểm tra + lưu 1 file đính kèm gửi trong chat.

    Trả về (attachment_url, attachment_type, original_filename) để caller ghi
    vào InteractionHistory. Raise HTTPException (400/413) nếu file không hợp lệ.
    """
    original_name = file.filename or "tep-dinh-kem"
    attachment_type = _detect_attachment_type(original_name, file.content_type)

    limit_mb = (
        settings.MAX_IMAGE_SIZE_MB
        if attachment_type == AttachmentType.IMAGE
        else settings.MAX_VIDEO_SIZE_MB
    )
    limit_bytes = limit_mb * 1024 * 1024

    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(original_name).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = settings.UPLOAD_DIR / stored_name

    size = 0
    try:
        with dest_path.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > limit_bytes:
                    out.close()
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File vượt quá giới hạn {limit_mb}MB cho "
                        f"{'ảnh' if attachment_type == AttachmentType.IMAGE else 'video'}.",
                    )
                out.write(chunk)
    finally:
        file.file.close()

    if size == 0:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File rỗng.")

    return f"/uploads/{stored_name}", attachment_type, original_name
