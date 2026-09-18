"""
Chống dò mật khẩu (brute-force) khi đăng nhập — dùng chung cho CẢ tài khoản
nhân viên (User) và khách hàng (Customer), vì cả 2 model đều có sẵn 2 cột:
    failed_login_attempts: int
    locked_until: datetime | None

Quy tắc: nhập sai mật khẩu quá LOGIN_LOCKOUT_THRESHOLD (5) lần liên tiếp thì
khoá đăng nhập trong LOGIN_LOCKOUT_MINUTES (2) phút. Đăng nhập đúng thì reset
bộ đếm về 0 ngay. Đây CHỈ khoá tạm thời việc ĐĂNG NHẬP (do sai mật khẩu) — không
liên quan đến is_active (khoá vĩnh viễn do admin chủ động vô hiệu hoá tài khoản).
"""

from datetime import datetime, timedelta, timezone
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

LOGIN_LOCKOUT_THRESHOLD = 5
LOGIN_LOCKOUT_MINUTES = 2


class _LockableAccount(Protocol):
    failed_login_attempts: int
    locked_until: datetime | None


def _as_naive_utc(dt: datetime) -> datetime:
    """
    SQLite không giữ lại tzinfo khi đọc lại DateTime(timezone=True) (trả về
    datetime "naive"), trong khi datetime.now(timezone.utc) luôn "aware" ->
    so sánh trực tiếp sẽ TypeError. Chuẩn hoá cả 2 vế về naive-UTC trước khi
    so sánh để chạy đúng trên cả SQLite lẫn Postgres (vốn giữ tzinfo).
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def ensure_not_locked(account: _LockableAccount) -> None:
    """Chặn ngay từ đầu nếu tài khoản đang trong thời gian bị khoá."""
    if not account.locked_until:
        return

    now_naive = _as_naive_utc(datetime.now(timezone.utc))
    locked_until_naive = _as_naive_utc(account.locked_until)

    if locked_until_naive > now_naive:
        remaining_seconds = int((locked_until_naive - now_naive).total_seconds())
        remaining_display = max(1, remaining_seconds)
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                f"Tài khoản đang tạm khoá do nhập sai mật khẩu quá "
                f"{LOGIN_LOCKOUT_THRESHOLD} lần. Vui lòng thử lại sau "
                f"{remaining_display} giây."
            ),
        )


def register_failed_attempt(account: _LockableAccount, db: Session) -> None:
    """
    Gọi khi nhập SAI mật khẩu. Tăng bộ đếm; nếu vừa chạm ngưỡng thì khoá
    LOGIN_LOCKOUT_MINUTES phút và raise luôn (để endpoint login báo lỗi 423
    thay vì 401 thông thường ở lần thứ 5 này).
    """
    account.failed_login_attempts += 1

    if account.failed_login_attempts >= LOGIN_LOCKOUT_THRESHOLD:
        account.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        account.failed_login_attempts = 0
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                f"Bạn đã nhập sai mật khẩu {LOGIN_LOCKOUT_THRESHOLD} lần liên tiếp. "
                f"Tài khoản bị khoá tạm thời trong {LOGIN_LOCKOUT_MINUTES} phút, "
                "vui lòng thử lại sau."
            ),
        )

    db.commit()


def reset_login_attempts(account: _LockableAccount, db: Session) -> None:
    """Gọi khi đăng nhập ĐÚNG — xoá sạch mọi dấu vết khoá/đếm sai trước đó."""
    if account.failed_login_attempts or account.locked_until:
        account.failed_login_attempts = 0
        account.locked_until = None
        db.commit()
