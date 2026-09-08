"""
Migration thủ công (một lần): thêm 2 cột chống dò mật khẩu vào bảng `users`
VÀ `customers`:
    failed_login_attempts INTEGER NOT NULL DEFAULT 0
    locked_until          DATETIME NULL

Tự kiểm tra cột đã tồn tại chưa trước khi chạy nên gọi lại nhiều lần không lỗi.

Cách chạy (từ thư mục gốc project, sau khi đã activate venv):
    python scripts/migrate_add_login_lockout.py
"""

from sqlalchemy import inspect, text

from app.database import engine


def _add_columns_if_missing(table: str) -> None:
    inspector = inspect(engine)

    if table not in inspector.get_table_names():
        print(f"[migrate] Chưa có bảng '{table}' — bỏ qua (sẽ tự tạo đủ cột khi init_db chạy lần đầu).")
        return

    existing_columns = {col["name"] for col in inspector.get_columns(table)}
    statements = []

    if "failed_login_attempts" not in existing_columns:
        statements.append(
            f"ALTER TABLE {table} ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0"
        )
    if "locked_until" not in existing_columns:
        statements.append(f"ALTER TABLE {table} ADD COLUMN locked_until DATETIME")

    if not statements:
        print(f"[migrate] Bảng '{table}' đã có đủ cột — không cần làm gì thêm.")
        return

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))

    print(f"[migrate] Đã thêm {len(statements)} cột mới vào bảng '{table}'.")


def main() -> None:
    _add_columns_if_missing("users")
    _add_columns_if_missing("customers")


if __name__ == "__main__":
    main()
