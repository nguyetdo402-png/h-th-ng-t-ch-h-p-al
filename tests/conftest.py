"""
Fixtures dùng chung cho toàn bộ test suite:
  - `client`: TestClient của FastAPI app, dùng SQLite in-memory RIÊNG cho test
    (không đụng vào app.db thật), tạo lại schema sạch cho mỗi test function.
  - `make_user` / `auth_headers`: tạo nhanh user theo role (admin/manager/agent)
    và lấy header Authorization: Bearer <JWT> tương ứng để gọi API như user đó.

Dùng StaticPool để nhiều connection SQLite trong cùng 1 test đều trỏ vào
cùng 1 in-memory DB (mặc định SQLite in-memory tạo DB mới cho mỗi connection).
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.database import Base, get_db
from app.main import app
from app.models.customer import Customer
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.user import User, UserRole

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture()
def db_session() -> Generator:
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session) -> Generator:
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    # CHỦ Ý không dùng `with TestClient(app) as c:` — cách đó sẽ kích hoạt
    # lifespan() thật của app (init_db() + seed admin/sản phẩm mẫu), vốn chạy
    # trên DATABASE_URL thật (app.db) chứ không phải DB test in-memory ở trên,
    # gây side-effect ngoài ý muốn lên dữ liệu dev thật khi chạy test.
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def make_user(db_session):
    """Factory tạo user theo role, trả về đối tượng User đã lưu DB."""

    counter = {"n": 0}

    def _make(role: UserRole, name: str | None = None) -> User:
        counter["n"] += 1
        user = User(
            name=name or f"{role.value.title()} {counter['n']}",
            email=f"{role.value}{counter['n']}@example.com",
            hashed_password=hash_password("testpass123"),
            role=role,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


@pytest.fixture()
def auth_headers(client):
    """Đăng nhập một User đã có trong DB, trả về header Authorization sẵn dùng."""

    def _headers(user: User, password: str = "testpass123") -> dict:
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": user.email, "password": password},
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture()
def make_ticket(db_session):
    """Factory tạo nhanh 1 Customer + Ticket, trả về đối tượng Ticket đã lưu DB."""

    counter = {"n": 0}

    def _make(assigned_to_agent_id: int | None = None, status: TicketStatus = TicketStatus.NEW) -> Ticket:
        counter["n"] += 1
        customer = Customer(
            name=f"Khach {counter['n']}",
            email=f"khach{counter['n']}@example.com",
        )
        db_session.add(customer)
        db_session.flush()

        ticket = Ticket(
            customer_id=customer.id,
            title=f"Yeu cau ho tro {counter['n']}",
            description="Mo ta van de.",
            priority=TicketPriority.MEDIUM,
            status=status,
            assigned_to_agent_id=assigned_to_agent_id,
        )
        db_session.add(ticket)
        db_session.commit()
        db_session.refresh(ticket)
        return ticket

    return _make
