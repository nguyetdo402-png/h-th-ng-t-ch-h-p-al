"""
Xác thực cho KHÁCH HÀNG (tách biệt hoàn toàn khỏi app/services/auth_service.py
dành cho nhân viên nội bộ).

Điểm khác biệt bảo mật quan trọng: JWT của khách hàng dùng key "customer_id"
trong payload (thay vì "user_id" như token nhân viên). Nhờ vậy:
  - Token khách hàng đưa vào get_current_user() (nhân viên) sẽ không tìm thấy
    "user_id" -> tự động bị từ chối, KHÔNG cần sửa auth_service.py.
  - Token nhân viên đưa vào get_current_customer() (khách hàng) sẽ không tìm
    thấy "customer_id" -> tự động bị từ chối tương tự.
Không cần thêm cờ "type" hay đụng vào code nhân viên hiện có để đạt được sự
tách biệt này.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.login_lockout import ensure_not_locked, register_failed_attempt, reset_login_attempts
from app.core.security import decode_access_token, hash_password, verify_password
from app.database import get_db
from app.models.customer import Customer
from app.schemas.customer_auth import CustomerRegister

oauth2_scheme_customer = OAuth2PasswordBearer(
    tokenUrl="api/v1/customer-auth/login", auto_error=False
)


def register_customer(db: Session, payload: CustomerRegister) -> Customer:
    """
    Đăng ký tài khoản khách hàng mới.

    Xử lý 2 trường hợp với email đã tồn tại trong bảng customers:
      1. Email đã có VÀ đã có mật khẩu (đã tự đăng ký trước đó) -> 409, không
         cho đăng ký chồng.
      2. Email đã có nhưng CHƯA có mật khẩu (hồ sơ do nhân viên tạo khi ghi
         nhận ticket qua điện thoại/email, khách chưa từng tự đăng ký) -> cho
         phép "claim": gán mật khẩu vào chính hồ sơ đó thay vì tạo bản ghi
         trùng email (email là unique). Đây là hành vi mong đợi cho khách
         hàng cũ muốn tạo tài khoản online lần đầu.
    """
    existing = db.query(Customer).filter(Customer.email == payload.email).first()

    if existing and existing.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email này đã có tài khoản. Vui lòng đăng nhập hoặc dùng 'Quên mật khẩu'.",
        )

    if existing:
        # Claim hồ sơ khách hàng có sẵn (do nhân viên tạo trước đó).
        existing.hashed_password = hash_password(payload.password)
        existing.name = payload.name or existing.name
        if payload.phone:
            existing.phone = payload.phone
        db.commit()
        db.refresh(existing)
        return existing

    customer = Customer(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def authenticate_customer(db: Session, email: str, password: str) -> Customer | None:
    """
    Trả về Customer nếu email/password đúng VÀ tài khoản đã có mật khẩu (đã đăng ký).
    Áp dụng khoá tạm sau 5 lần sai liên tiếp giống hệt tài khoản nhân viên —
    xem app/core/login_lockout.py.
    """
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer or not customer.hashed_password:
        return None

    ensure_not_locked(customer)

    if not verify_password(password, customer.hashed_password):
        register_failed_attempt(customer, db)
        return None

    reset_login_attempts(customer, db)
    return customer


def get_current_customer(
    token: str | None = Depends(oauth2_scheme_customer),
    db: Session = Depends(get_db),
) -> Customer:
    """
    Dependency cho các endpoint yêu cầu khách hàng đã đăng nhập.
    auto_error=False ở oauth2_scheme_customer để tự kiểm soát thông báo lỗi
    rõ ràng hơn (thay vì lỗi mặc định của FastAPI khi thiếu header).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Vui lòng đăng nhập để tiếp tục",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    customer_id = payload.get("customer_id")
    if customer_id is None:
        raise credentials_exception

    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer is None:
        raise credentials_exception

    return customer


def get_current_customer_optional(
    token: str | None = Depends(oauth2_scheme_customer),
    db: Session = Depends(get_db),
) -> Customer | None:
    """
    Giống get_current_customer() nhưng trả None thay vì raise lỗi khi chưa
    đăng nhập — dùng cho các endpoint mà khách CÓ THỂ dùng ẩn danh hoặc đã
    đăng nhập (vd: chat công khai tự nhận diện nếu có token, không bắt buộc).
    """
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    customer_id = payload.get("customer_id")
    if customer_id is None:
        return None
    return db.query(Customer).filter(Customer.id == customer_id).first()
