"""
Thiết lập kết nối database bằng SQLAlchemy.

- engine: kết nối tới DB (SQLite hiện tại, đổi DATABASE_URL trong .env để
  chuyển sang PostgreSQL sau này mà không cần sửa code).
- SessionLocal: factory tạo session cho mỗi request.
- Base: lớp declarative base để các model trong app/models/ kế thừa.
- get_db(): FastAPI dependency, đảm bảo session luôn được đóng sau khi dùng.
- init_db(): tạo toàn bộ bảng trong DB dựa trên các model đã import vào Base.metadata.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# connect_args chỉ cần thiết với SQLite (cho phép dùng chung connection
# giữa nhiều thread, vì FastAPI có thể xử lý request trên các thread khác nhau).
connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,  # bật True khi cần debug SQL query
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base dùng chung cho tất cả model trong app/models/."""

    pass


def get_db() -> Generator:
    """
    FastAPI dependency: mở một session DB cho request hiện tại,
    tự động đóng lại sau khi request xử lý xong (kể cả khi có lỗi).

    Cách dùng trong router:
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Tạo tất cả bảng trong DB dựa trên metadata của Base.
    Phải import toàn bộ model trước khi gọi hàm này để SQLAlchemy
    biết được các bảng cần tạo (xem import bên dưới).

    Lưu ý: dùng cho môi trường dev/demo. Khi lên production nên dùng
    Alembic migration thay vì create_all().
    """
    # Import tại đây (thay vì đầu file) để tránh circular import,
    # vì các model sẽ import `Base` ngược lại từ file này.
    from app.models import (  # noqa: F401
        ai_draft,
        customer,
        faq,
        interaction_history,
        order,
        product,
        ticket,
        user,
    )

    Base.metadata.create_all(bind=engine)
