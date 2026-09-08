"""
Migration thủ công (một lần): thêm cột `priority_source` vào bảng `tickets`.

Vì project chưa có sẵn revision Alembic nào (thư mục alembic/versions/ đang
trống), cách nhanh và an toàn nhất cho DB SQLite hiện tại là ALTER TABLE trực
tiếp, KHÔNG xoá dữ liệu cũ. Script tự kiểm tra cột đã tồn tại chưa trước khi
chạy nên gọi lại nhiều lần cũng không lỗi.

Cách chạy (từ thư mục gốc project, sau khi đã activate venv):
    python scripts/migrate_add_priority_source.py
"""

from sqlalchemy import inspect, text

from app.database import engine


def main() -> None:
    inspector = inspect(engine)

    if "tickets" not in inspector.get_table_names():
        print("[migrate] Chưa có bảng 'tickets' — DB sẽ tự tạo đủ cột khi chạy "
              "app lần đầu (init_db). Không cần chạy migration này.")
        return

    existing_columns = {col["name"] for col in inspector.get_columns("tickets")}
    if "priority_source" in existing_columns:
        print("[migrate] Cột 'priority_source' đã tồn tại — không cần làm gì thêm.")
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE tickets "
                "ADD COLUMN priority_source VARCHAR(10) NOT NULL DEFAULT 'manual'"
            )
        )

    print(
        "[migrate] Đã thêm cột 'priority_source' vào bảng 'tickets' "
        "(mặc định 'manual' cho toàn bộ ticket cũ)."
    )


if __name__ == "__main__":
    main()
