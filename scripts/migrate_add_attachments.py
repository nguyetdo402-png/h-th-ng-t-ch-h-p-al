"""
Migration thủ công (một lần): thêm 3 cột đính kèm ảnh/video vào bảng
`interaction_histories`: attachment_url, attachment_type, attachment_filename.

Cùng cách làm với scripts/migrate_add_priority_source.py — ALTER TABLE trực
tiếp trên SQLite, không xoá dữ liệu cũ, gọi lại nhiều lần không lỗi (tự kiểm
tra cột đã tồn tại chưa trước khi chạy).

Cách chạy (từ thư mục gốc project, sau khi đã activate venv):
    python scripts/migrate_add_attachments.py
"""

from sqlalchemy import inspect, text

from app.database import engine

_NEW_COLUMNS = {
    "attachment_url": "VARCHAR(500)",
    "attachment_type": "VARCHAR(10)",
    "attachment_filename": "VARCHAR(255)",
}


def main() -> None:
    inspector = inspect(engine)

    if "interaction_histories" not in inspector.get_table_names():
        print(
            "[migrate] Chưa có bảng 'interaction_histories' — DB sẽ tự tạo đủ cột "
            "khi chạy app lần đầu (init_db). Không cần chạy migration này."
        )
        return

    existing_columns = {col["name"] for col in inspector.get_columns("interaction_histories")}
    to_add = {name: coltype for name, coltype in _NEW_COLUMNS.items() if name not in existing_columns}

    if not to_add:
        print("[migrate] Các cột đính kèm đã tồn tại đủ — không cần làm gì thêm.")
        return

    with engine.begin() as conn:
        for name, coltype in to_add.items():
            conn.execute(text(f"ALTER TABLE interaction_histories ADD COLUMN {name} {coltype}"))

    print(f"[migrate] Đã thêm các cột: {', '.join(to_add)} vào bảng 'interaction_histories'.")


if __name__ == "__main__":
    main()
