"""
AI Service — tích hợp OpenAI/Gemini để hỗ trợ xử lý ticket.

Ba hàm public:
    - anonymize_data(text)                 : ẩn PII (email, số điện thoại) trong văn bản.
    - classify_and_summarize(ticket_context): phân loại nhóm vấn đề, gợi ý priority, tóm tắt.
    - generate_draft_response(ticket_context): sinh câu trả lời NHÁP cho agent duyệt.

QUY TẮC BẮT BUỘC CỦA HỆ THỐNG (không được vi phạm ở tầng gọi hàm này):
    1. generate_draft_response() CHỈ sinh bản NHÁP. Router/service gọi hàm này phải lưu
       kết quả vào bảng AiDraft với is_approved=False. Chỉ khi agent bấm "Duyệt" trên
       giao diện thì nội dung mới được copy sang InteractionHistory để gửi cho khách.
       File này không được phép tự ý ghi vào InteractionHistory hay gửi email/tin nhắn.
    2. Mọi văn bản tự do (title, description, nội dung interaction) PHẢI đi qua
       anonymize_data() trước khi được đưa vào prompt gửi ra ngoài (OpenAI/Gemini).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# 1. ANONYMIZE DATA — ẩn PII trước khi gửi bất kỳ nội dung nào ra ngoài
# =============================================================================

# Email: pattern chuẩn, đủ dùng cho phần lớn trường hợp thực tế.
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Số điện thoại VN: chấp nhận các dạng phổ biến
#   0901234567 | 090 123 4567 | 090-123-4567 | +84901234567 | +84 90 123 4567
#   (090) 123 4567 | (84) 90 123 4567
# Yêu cầu tổng cộng 9-10 chữ số sau đầu số để tránh nhận nhầm các dãy số ngắn
# (ví dụ mã ticket, mã đơn hàng) thành số điện thoại.
# Lưu ý: đây là regex best-effort cho các định dạng phổ biến nhất, không bao
# phủ tuyệt đối mọi cách viết số điện thoại trong thực tế.
_PHONE_PATTERN = re.compile(
    r"(?:\(?\+?84\)?|\(?0\)?)[\s.-]?\(?\d{2,4}\)?(?:[\s.-]?\d){6,9}"
)


def anonymize_data(text: str | None) -> str:
    """
    Ẩn thông tin cá nhân (PII) trong văn bản trước khi gửi cho AI.

    Hiện xử lý:
        - Email  -> thay bằng "[EMAIL]"
        - Số điện thoại (định dạng VN/quốc tế cơ bản) -> thay bằng "[PHONE]"

    Hàm an toàn với None/chuỗi rỗng (trả lại nguyên trạng).

    >>> anonymize_data("Liên hệ tôi qua a@b.com hoặc 0901234567 nhé")
    'Liên hệ tôi qua [EMAIL] hoặc [PHONE] nhé'
    """
    if not text:
        return text or ""

    anonymized = _EMAIL_PATTERN.sub("[EMAIL]", text)
    anonymized = _PHONE_PATTERN.sub("[PHONE]", anonymized)
    return anonymized


# =============================================================================
# Kiểu dữ liệu đầu vào dùng chung cho classify_and_summarize & generate_draft_response
# =============================================================================


class InteractionItem(TypedDict, total=False):
    sender_type: str  # "customer" | "agent" | "system"
    content: str


class TicketContext(TypedDict, total=False):
    """
    Ngữ cảnh ticket truyền vào AI. CHỈ chứa nội dung văn bản tự do —
    KHÔNG được đưa các field định danh trực tiếp (customer_email, customer_phone, ...)
    vào đây; nếu những thông tin đó lỡ xuất hiện lồng trong title/description/nội dung
    tương tác thì anonymize_data() sẽ tự động ẩn đi.
    """

    title: str
    description: str
    priority: str
    status: str
    interactions: list[InteractionItem]
    # FAQ nội bộ (câu trả lời mẫu do admin/manager soạn sẵn) đã được so khớp
    # với ticket này theo từ khóa (xem app/services/faq_service.py). Đưa vào
    # đây để AI ưu tiên bám theo đúng chính sách thật của cửa hàng thay vì tự
    # suy diễn/bịa — KHÔNG phải dữ liệu cá nhân nên không cần anonymize.
    faq_context: list[dict]


def _build_context_text(ticket_context: TicketContext) -> str:
    """Gộp thông tin ticket thành 1 đoạn văn bản, đã ẩn PII, để đưa vào prompt."""
    lines: list[str] = []

    title = ticket_context.get("title", "") or ""
    description = ticket_context.get("description", "") or ""
    priority = ticket_context.get("priority")
    status = ticket_context.get("status")

    lines.append(f"Tiêu đề: {anonymize_data(title)}")
    if priority:
        lines.append(f"Mức ưu tiên hiện tại: {priority}")
    if status:
        lines.append(f"Trạng thái hiện tại: {status}")
    lines.append(f"Mô tả: {anonymize_data(description)}")

    interactions = ticket_context.get("interactions") or []
    if interactions:
        lines.append("\nLịch sử tương tác (theo thứ tự thời gian):")
        for item in interactions:
            sender = item.get("sender_type", "unknown")
            content = anonymize_data(item.get("content", ""))
            lines.append(f"- [{sender}] {content}")

    faq_context = ticket_context.get("faq_context") or []
    if faq_context:
        lines.append(
            "\nCâu trả lời mẫu (chính sách chính thức của cửa hàng, do quản lý soạn sẵn — "
            "liên quan tới ticket này):"
        )
        for item in faq_context:
            question = item.get("question", "")
            answer = item.get("answer", "")
            lines.append(f"- Hỏi: {question}\n  Đáp: {answer}")

    return "\n".join(lines)


# =============================================================================
# Lớp gọi AI cấp thấp — hỗ trợ cả OpenAI và Gemini, chọn qua settings.AI_PROVIDER
# =============================================================================

_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "Thiếu OPENAI_API_KEY. Hãy điền vào file .env (xem .env.example)."
            )
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def _call_openai(system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> str:
    client = _get_openai_client()
    kwargs: dict[str, Any] = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001 - cố ý bắt rộng để bọc thành lỗi rõ ràng cho caller
        logger.exception("Lỗi khi gọi OpenAI API")
        raise RuntimeError(f"Không thể gọi AI (OpenAI): {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI trả về nội dung rỗng")
    return content.strip()


def _call_gemini(system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> str:
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError(
            "Chưa cài thư viện google-generativeai. Bỏ comment dòng tương ứng trong "
            "requirements.txt rồi chạy: pip install google-generativeai --break-system-packages"
        ) from exc

    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "Thiếu GEMINI_API_KEY. Hãy điền vào file .env (xem .env.example)."
        )

    genai.configure(api_key=settings.GEMINI_API_KEY)
    generation_config = {"response_mime_type": "application/json"} if json_mode else {}
    model = genai.GenerativeModel(
        model_name=settings.AI_MODEL,
        system_instruction=system_prompt,
        generation_config=generation_config,
    )

    try:
        response = model.generate_content(user_prompt)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Lỗi khi gọi Gemini API")
        raise RuntimeError(f"Không thể gọi AI (Gemini): {exc}") from exc

    if not response.text:
        raise RuntimeError("Gemini trả về nội dung rỗng")
    return response.text.strip()


def _chat_completion(system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> str:
    """Dispatch tới provider AI đang cấu hình (openai | gemini)."""
    provider = (settings.AI_PROVIDER or "openai").lower()
    if provider == "openai":
        return _call_openai(system_prompt, user_prompt, json_mode=json_mode)
    if provider == "gemini":
        return _call_gemini(system_prompt, user_prompt, json_mode=json_mode)
    raise ValueError(f"AI_PROVIDER không hợp lệ: {settings.AI_PROVIDER!r} (chỉ hỗ trợ openai|gemini)")


def _safe_parse_json(raw: str) -> dict[str, Any]:
    """
    Parse JSON trả về từ AI, có fallback: nếu model lỡ thêm text thừa quanh JSON
    (dù đã yêu cầu json_mode), cố gắng trích phần {...} ra để parse lại.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        logger.warning("Không parse được JSON từ phản hồi AI. Raw response: %s", raw)
        return {}


# =============================================================================
# 2. CLASSIFY & SUMMARIZE
# =============================================================================

_CLASSIFY_SYSTEM_PROMPT = """\
Bạn là trợ lý AI hỗ trợ phân loại ticket cho một hệ thống chăm sóc khách hàng.
Nhiệm vụ của bạn CHỈ là phân tích nội bộ — bạn KHÔNG trả lời trực tiếp cho khách hàng.

Dựa trên tiêu đề, mô tả và lịch sử tương tác của ticket được cung cấp, hãy xác định:

1. "category": nhóm vấn đề của ticket. Ưu tiên chọn một trong các nhóm sau nếu phù hợp:
   "Lỗi kỹ thuật", "Thanh toán/Hoá đơn", "Tài khoản/Đăng nhập", "Yêu cầu tính năng",
   "Khiếu nại/Phàn nàn", "Câu hỏi chung". Nếu không nhóm nào phù hợp, hãy tự đặt một
   tên nhóm ngắn gọn khác.
2. "priority": mức độ ưu tiên đề xuất — CHỈ được chọn một trong ba giá trị:
   "low", "medium", "high".
3. "summary": tóm tắt ngắn gọn (2-4 câu, bằng tiếng Việt) nội dung vấn đề và diễn biến
   xử lý tính đến thời điểm hiện tại, dựa hoàn toàn trên thông tin được cung cấp.

Chỉ trả lời bằng một object JSON hợp lệ, đúng định dạng sau, KHÔNG thêm bất kỳ
văn bản, markdown hay giải thích nào khác:
{"category": "...", "priority": "low|medium|high", "summary": "..."}
"""

_VALID_PRIORITIES = {"low", "medium", "high"}


def classify_and_summarize(ticket_context: TicketContext) -> dict[str, str]:
    """
    Dùng AI để phân loại nhóm vấn đề, gợi ý mức ưu tiên, và tóm tắt lịch sử ticket.

    Trả về dict:
        {
            "suggested_category": str,
            "suggested_priority": "low" | "medium" | "high",
            "summary": str,
        }

    Kết quả này dùng để hiển thị gợi ý cho agent hoặc lưu vào AiDraft.suggested_category /
    AiDraft.suggested_priority — KHÔNG tự động ghi đè Ticket.priority thật.
    """
    context_text = _build_context_text(ticket_context)

    raw_response = _chat_completion(_CLASSIFY_SYSTEM_PROMPT, context_text, json_mode=True)
    parsed = _safe_parse_json(raw_response)

    category = str(parsed.get("category") or "Chưa phân loại").strip()

    priority = str(parsed.get("priority") or "").strip().lower()
    if priority not in _VALID_PRIORITIES:
        logger.warning("AI trả về priority không hợp lệ (%r), fallback về 'medium'", priority)
        priority = "medium"

    summary = str(parsed.get("summary") or "").strip()

    return {
        "suggested_category": category,
        "suggested_priority": priority,
        "summary": summary,
    }


# =============================================================================
# 3. GENERATE DRAFT RESPONSE
# =============================================================================

# System Prompt chuẩn: bắt buộc mọi output là bản NHÁP, không bịa thông tin,
# không lộ placeholder ẩn danh, và không tự ký tên nhân viên cụ thể.
_DRAFT_RESPONSE_SYSTEM_PROMPT = """\
Bạn là trợ lý AI hỗ trợ SOẠN THẢO câu trả lời cho nhân viên chăm sóc khách hàng.

QUY TẮC BẮT BUỘC:
1. Đây LUÔN LUÔN là một bản NHÁP (draft). Một nhân viên con người sẽ đọc, có thể
   chỉnh sửa, và phải DUYỆT trước khi bất kỳ nội dung nào được gửi cho khách hàng.
   Bạn không được giả định nội dung này sẽ gửi thẳng cho khách.
2. Chỉ được sử dụng thông tin có trong tiêu đề, mô tả và lịch sử tương tác được cung cấp.
   TUYỆT ĐỐI KHÔNG bịa đặt chính sách, số liệu, thời gian xử lý, hay đưa ra cam kết
   không có căn cứ trong ngữ cảnh.
3. Nếu thông tin hiện có chưa đủ để giải quyết dứt điểm vấn đề, hãy soạn câu trả lời
   lịch sự để xin thêm thông tin cần thiết từ khách hàng, thay vì đoán hoặc bịa.
3b. Nếu ngữ cảnh có kèm mục "Câu trả lời mẫu (chính sách chính thức của cửa hàng...)",
    đây là nguồn thông tin ĐÁNG TIN CẬY NHẤT — hãy ưu tiên bám sát nội dung đó khi
    soạn câu trả lời (có thể diễn đạt lại tự nhiên, không cần chép nguyên văn).
    Nếu câu trả lời mẫu mâu thuẫn với suy luận khác của bạn, luôn ưu tiên câu trả lời mẫu.
4. Giọng văn: chuyên nghiệp, lịch sự, thể hiện sự đồng cảm, ngắn gọn, súc tích.
   Xưng "chúng tôi", gọi khách hàng là "anh/chị".
5. Ngữ cảnh được cung cấp có thể chứa các placeholder ẩn danh như [EMAIL] hoặc [PHONE]
   (do hệ thống tự động ẩn thông tin cá nhân). TUYỆT ĐỐI KHÔNG chép các placeholder này
   vào câu trả lời — nếu cần nhắc tới, hãy diễn đạt tự nhiên (ví dụ: "thông tin liên hệ
   anh/chị đã cung cấp").
6. KHÔNG ký tên cá nhân cụ thể ở cuối thư (nhân viên sẽ tự ký tên khi duyệt gửi).
   Có thể kết thư bằng một lời chào chung, ví dụ "Trân trọng,".
7. Chỉ trả về NỘI DUNG CÂU TRẢ LỜI dạng văn bản thuần (plain text). Không thêm lời
   giải thích, không thêm markdown, không thêm dấu backtick.
"""


def generate_draft_response(ticket_context: TicketContext) -> str:
    """
    Sinh câu trả lời NHÁP cho agent, dựa trên ngữ cảnh ticket (đã được ẩn PII).

    QUAN TRỌNG: Hàm này CHỈ trả về chuỗi văn bản draft — không tự ghi vào DB.
    Caller (ví dụ app/api/v1/ai_drafts.py) chịu trách nhiệm lưu kết quả vào bảng
    AiDraft với is_approved=False, và chỉ copy sang InteractionHistory sau khi
    agent bấm "Duyệt".
    """
    context_text = _build_context_text(ticket_context)
    draft_text = _chat_completion(_DRAFT_RESPONSE_SYSTEM_PROMPT, context_text, json_mode=False)
    return draft_text.strip()
