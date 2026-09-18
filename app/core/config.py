"""
Cấu hình ứng dụng, đọc từ file .env bằng pydantic-settings.
Dùng chung cho toàn bộ app (database, AI service, security, ...).
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Thư mục gốc của project (chứa requirements.txt, .env, app.db) — tính từ vị
# trí file này (app/core/config.py) đi lên 2 cấp. Dùng đường dẫn TUYỆT ĐỐI
# thay vì "./app.db" (tương đối) để file database luôn nằm cố định 1 chỗ,
# KHÔNG PHỤ THUỘC vào việc bạn đứng ở thư mục nào khi gõ lệnh `uvicorn` —
# tránh tình trạng tưởng nhầm là "mất dữ liệu" khi thực ra chỉ là đang tạo
# một file app.db MỚI ở một vị trí khác.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "AI Customer Support System"
    SECRET_KEY: str = "change-this-to-a-random-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Database ---
    DATABASE_URL: str = f"sqlite:///{PROJECT_ROOT / 'app.db'}"

    # --- AI Provider ---
    AI_PROVIDER: str = "openai"  # "openai" | "gemini"
    OPENAI_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    AI_MODEL: str = "gpt-4o-mini"

    # --- Upload (ảnh/video khách gửi kèm trong chat) ---
    # Thư mục vật lý lưu file, phục vụ qua StaticFiles ở /uploads (xem main.py).
    # Cùng nguyên tắc đường dẫn TUYỆT ĐỐI như DATABASE_URL ở trên.
    UPLOAD_DIR: Path = PROJECT_ROOT / "uploads"
    MAX_IMAGE_SIZE_MB: int = 10
    MAX_VIDEO_SIZE_MB: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Trả về Settings singleton (cache lại, chỉ đọc .env 1 lần)."""
    return Settings()


settings = get_settings()
