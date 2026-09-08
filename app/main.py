"""
Entry point FastAPI app.
- Khởi tạo DB (create_all) khi start.
- Seed 1 tài khoản admin mặc định nếu DB chưa có user nào (chỉ để bootstrap lần đầu).
- Include API router /api/v1.
- Cấu hình CORS để frontend (chạy HTML tĩnh) có thể gọi API.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import hash_password
from app.database import SessionLocal, init_db
from app.models.faq import FaqEntry
from app.models.product import Product, ProductVariant
from app.models.user import User, UserRole

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _seed_default_admin() -> None:
    """
    Tạo sẵn 1 tài khoản admin (admin@example.com / admin123) nếu bảng users
    đang trống, để có thể đăng nhập lần đầu tiên và tạo thêm tài khoản khác
    qua /api/v1/auth/register.

    LƯU Ý: chỉ dùng cho môi trường dev/demo. Ở production nên tạo admin
    qua một quy trình bootstrap riêng và đổi mật khẩu ngay sau đó.
    """
    db = SessionLocal()
    try:
        has_any_user = db.query(User).first() is not None
        if not has_any_user:
            admin = User(
                name="System Admin",
                email="admin@example.com",
                hashed_password=hash_password("admin123"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print(
                "[seed] Đã tạo tài khoản admin mặc định: "
                "admin@example.com / admin123 — hãy đổi mật khẩu ngay."
            )
    finally:
        db.close()


def _seed_sample_products() -> None:
    """
    Tạo sẵn vài sản phẩm quần áo mẫu (kèm variant size/màu + tồn kho) nếu bảng
    products đang trống — để demo/test đơn hàng ngay mà không cần nhập tay.
    """
    db = SessionLocal()
    try:
        has_any_product = db.query(Product).first() is not None
        if has_any_product:
            return

        sample_products = [
            {
                "name": "Áo thun basic",
                "description": "Áo thun cotton form rộng, form unisex.",
                "price": 150000,
                "variants": [
                    ("S", "Trắng", 20),
                    ("M", "Trắng", 15),
                    ("M", "Đen", 10),
                    ("L", "Đen", 8),
                ],
            },
            {
                "name": "Quần jean ống suông",
                "description": "Jean co giãn nhẹ, form suông basic.",
                "price": 320000,
                "variants": [
                    ("29", "Xanh đậm", 12),
                    ("30", "Xanh đậm", 10),
                    ("31", "Đen", 6),
                ],
            },
        ]

        for item in sample_products:
            product = Product(
                name=item["name"], description=item["description"], price=item["price"]
            )
            db.add(product)
            db.flush()
            for size, color, stock in item["variants"]:
                db.add(
                    ProductVariant(
                        product_id=product.id, size=size, color=color, stock_quantity=stock
                    )
                )
        db.commit()
        print("[seed] Đã tạo sẵn 2 sản phẩm mẫu kèm tồn kho để demo.")
    finally:
        db.close()


def _seed_sample_faqs() -> None:
    """
    Tạo sẵn vài FAQ mẫu (câu trả lời chuẩn theo từ khóa) nếu bảng faq_entries
    đang trống — để demo tính năng gợi ý FAQ cho agent + làm ngữ cảnh cho AI
    ngay mà không cần admin phải tự soạn từ đầu.
    """
    db = SessionLocal()
    try:
        has_any_faq = db.query(FaqEntry).first() is not None
        if has_any_faq:
            return

        sample_faqs = [
            {
                "question": "Bảng size áo/quần của shop như thế nào?",
                "keywords": "size, bảng size, đổi size, kích cỡ, size chart",
                "answer": (
                    "Shop có bảng size chi tiết theo từng loại sản phẩm (áo/quần), "
                    "khách vui lòng xem ảnh bảng size ở phần mô tả sản phẩm. Nếu đã nhận "
                    "hàng mà không vừa size, có thể đổi sang size khác trong vòng 7 ngày "
                    "kể từ ngày nhận hàng, với điều kiện sản phẩm còn nguyên tem mác, "
                    "chưa qua sử dụng/giặt."
                ),
            },
            {
                "question": "Chính sách đổi trả hàng của shop?",
                "keywords": "đổi trả, đổi hàng, trả hàng, hoàn hàng, không vừa",
                "answer": (
                    "Shop hỗ trợ đổi trả trong vòng 7 ngày kể từ ngày nhận hàng, áp dụng "
                    "cho trường hợp không vừa size hoặc đổi ý (sản phẩm còn nguyên tem "
                    "mác, chưa qua sử dụng/giặt/ủi). Khách vui lòng gửi kèm ảnh sản phẩm "
                    "và mã đơn hàng để được hỗ trợ nhanh nhất. Phí vận chuyển đổi trả do "
                    "khách chịu, trừ trường hợp lỗi từ phía shop."
                ),
            },
            {
                "question": "Nhận được hàng bị lỗi (rách, lem màu, thiếu phụ kiện...) thì làm sao?",
                "keywords": "hàng lỗi, lỗi, rách, hư, lem màu, thiếu, sai hàng",
                "answer": (
                    "Shop rất xin lỗi vì trải nghiệm không tốt này. Với hàng lỗi do sản "
                    "xuất/vận chuyển, shop hỗ trợ đổi mới 100% hoặc hoàn tiền, khách hàng "
                    "KHÔNG mất phí vận chuyển đổi trả. Anh/chị vui lòng chụp ảnh rõ lỗi sản "
                    "phẩm và cung cấp mã đơn hàng để shop xử lý đổi/hoàn trong 24h."
                ),
            },
        ]

        for item in sample_faqs:
            db.add(FaqEntry(**item, is_active=True))
        db.commit()
        print("[seed] Đã tạo sẵn 3 FAQ mẫu (size / đổi trả / hàng lỗi) để demo.")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _seed_default_admin()
    _seed_sample_products()
    _seed_sample_faqs()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting cho các endpoint public (xem app/core/rate_limit.py) — chặn
# brute-force dò access_token/ticket_id và spam tạo ticket qua chat widget.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Cho phép frontend (file HTML tĩnh, mở qua trình duyệt hoặc live-server khác cổng)
# gọi được API. Ở production nên giới hạn allow_origins cụ thể thay vì "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# --- Phục vụ frontend (HTML5 + Tailwind CDN + JS thuần) ---
# /static/... : file CSS/JS dùng chung
# /, /login, /ticket : trả về file HTML tương ứng. Điều hướng theo trạng thái
#   đăng nhập (kiểm tra token trong localStorage) được xử lý ở phía client (JS),
#   vì đây là single-page-per-file app không dùng session phía server.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")

# /uploads/... : ảnh/video khách gửi kèm trong chat (xem app/services/upload_service.py).
# Tạo thư mục trước nếu chưa có, tránh StaticFiles báo lỗi lúc khởi động trên máy mới.
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.get("/", include_in_schema=False)
def serve_welcome() -> FileResponse:
    """
    Trang chào công khai — nơi BẤT KỲ ai (khách hàng hoặc nhân viên) vào domain
    gốc cũng thấy ngay 2 lối đi rõ ràng, thay vì bị mặc định hất vào trang đăng
    nhập nhân viên (trước đây "/" trả thẳng dashboard, khiến khách hàng vô tình
    vào sẽ không thấy đường nào để đăng ký/đăng nhập cho mình).
    """
    return FileResponse(FRONTEND_DIR / "templates" / "welcome.html")


@app.get("/dashboard", include_in_schema=False)
def serve_dashboard() -> FileResponse:
    """Dashboard quản lý ticket — dành cho nhân viên (trước đây ở '/')."""
    return FileResponse(FRONTEND_DIR / "templates" / "index.html")


@app.get("/login", include_in_schema=False)
def serve_login() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "templates" / "login.html")


@app.get("/account", include_in_schema=False)
def serve_customer_account() -> FileResponse:
    """Trang đăng nhập/đăng ký cho KHÁCH HÀNG (khác /login — dành cho nhân viên nội bộ)."""
    return FileResponse(FRONTEND_DIR / "templates" / "account.html")


@app.get("/chat", include_in_schema=False)
def serve_customer_chat_widget() -> FileResponse:
    """
    Trang chat công khai cho khách hàng (không cần đăng nhập) — gọi các endpoint
    /api/v1/public/chat/*. Có thể nhúng (iframe) vào website bán hàng thật.
    """
    return FileResponse(FRONTEND_DIR / "templates" / "chat_widget.html")


@app.get("/my-account", include_in_schema=False)
def serve_my_account() -> FileResponse:
    """Trang 'Tài khoản của tôi': đơn hàng + lịch sử ticket/chat của khách đã đăng nhập."""
    return FileResponse(FRONTEND_DIR / "templates" / "my_account.html")


@app.get("/ticket", include_in_schema=False)
def serve_ticket_detail_legacy() -> FileResponse:
    """
    Tương thích ngược cho link cũ dạng /ticket?id=123 (trước khi gộp thành SPA).
    Trả về cùng index.html — app.js sẽ đọc query string phía client và tự
    chuyển sang route nội bộ #/tickets/{id}.
    """
    return FileResponse(FRONTEND_DIR / "templates" / "index.html")


@app.get("/health", tags=["Health"])
def health_check() -> dict:
    return {"status": "ok", "app": settings.APP_NAME}
