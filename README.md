# Hệ thống Quản lý Hỗ trợ Khách hàng tích hợp AI

## Tech Stack
- **Backend:** FastAPI (Python 3.10+)
- **Database:** SQLite (SQLAlchemy ORM — dễ nâng cấp PostgreSQL)
- **Frontend:** HTML5 + TailwindCSS (CDN) + JavaScript (Fetch API)
- **AI:** OpenAI API / Gemini API — phân loại ticket, gợi ý trả lời, tóm tắt

## Cấu trúc thư mục

```
customer-support-ai/
├── app/
│   ├── main.py                # Entry point FastAPI
│   ├── core/                  # Config, security, logging
│   │   ├── config.py
│   │   ├── security.py
│   │   └── logging_config.py
│   ├── db/                    # Kết nối & khởi tạo database
│   │   ├── base.py
│   │   ├── session.py
│   │   └── init_db.py
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── user.py
│   │   ├── customer.py
│   │   ├── ticket.py
│   │   ├── interaction_history.py
│   │   └── ai_draft.py
│   ├── schemas/                 # Pydantic schemas (request/response)
│   │   ├── user.py
│   │   ├── customer.py
│   │   ├── ticket.py
│   │   ├── interaction_history.py
│   │   └── ai_draft.py
│   ├── services/                # Business logic layer
│   │   ├── user_service.py
│   │   ├── customer_service.py
│   │   ├── ticket_service.py
│   │   ├── ai_service.py        # Gọi OpenAI/Gemini
│   │   ├── pii_service.py       # Ẩn PII trước khi gửi AI
│   │   └── auth_service.py
│   ├── api/v1/                  # API routers (FastAPI APIRouter)
│   │   ├── users.py
│   │   ├── customers.py
│   │   ├── tickets.py
│   │   ├── interactions.py
│   │   ├── ai_drafts.py
│   │   ├── auth.py
│   │   └── router.py            # Gộp tất cả router con
│   └── utils/                   # Hàm tiện ích dùng chung
├── frontend/
│   ├── templates/                # index.html, login.html, ticket_detail.html
│   └── static/{css,js}
├── tests/                        # pytest
├── alembic/                       # Migration (khi cần)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Nguyên tắc kiến trúc (Clean Architecture layers)

```
API (routers)  →  Services (business logic)  →  Models (ORM) / Schemas (validation)
                         ↓
                    AI Service ← PII Service (anonymize trước khi gọi AI)
```

- **models/**: chỉ định nghĩa bảng dữ liệu (SQLAlchemy), không chứa logic nghiệp vụ.
- **schemas/**: định nghĩa hình dạng dữ liệu vào/ra API (Pydantic), tách biệt với model DB.
- **services/**: toàn bộ logic nghiệp vụ, bao gồm gọi AI và xử lý PII, nằm ở đây — không viết trực tiếp trong router.
- **api/v1/**: chỉ nhận request, gọi service tương ứng, trả response. Không chứa business logic.

## Nguyên tắc AI & bảo mật dữ liệu

1. **AI chỉ sinh Draft**: Mọi phản hồi AI được lưu vào bảng `AiDraft` với `is_approved=False`. Chỉ khi nhân viên (agent) bấm **Duyệt**, hệ thống mới cập nhật `is_approved=True` và ghi nội dung đó vào `InteractionHistory` để gửi cho khách.
2. **Ẩn PII trước khi gọi AI**: `pii_service.anonymize_pii()` sẽ thay thế email, số điện thoại (và có thể cả tên) bằng placeholder (vd: `[EMAIL]`, `[PHONE]`) trước khi nội dung được đưa vào prompt gửi tới OpenAI/Gemini.

## Cài đặt (sẽ dùng ở Giai đoạn sau)

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # rồi điền OPENAI_API_KEY, SECRET_KEY...
uvicorn app.main:app --reload
```

## Trạng thái hiện tại

✅ Giai đoạn 1: Khung cấu trúc thư mục + requirements.txt
⬜ Giai đoạn 2: Models + Database setup
⬜ Giai đoạn 3: Schemas + Services
⬜ Giai đoạn 4: API Routers
⬜ Giai đoạn 5: AI Integration + PII Anonymization
⬜ Giai đoạn 6: Frontend (Tailwind + JS)
