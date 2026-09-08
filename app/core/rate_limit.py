"""
Rate limiting cho các endpoint public (không cần đăng nhập).

Dùng slowapi (dựa trên thư viện `limits`), giới hạn theo địa chỉ IP của
request. Áp dụng cho các route trong `app/api/v1/public_chat.py` vì đây là
nơi duy nhất trong hệ thống nhận request không cần xác thực JWT — nếu không
giới hạn, kẻ tấn công có thể dò (brute-force) email/ticket_id/access_token
hoặc spam tạo ticket/gọi AI tốn phí.

LƯU Ý: dùng in-memory storage (mặc định của slowapi) chỉ phù hợp khi chạy
1 process. Nếu sau này scale ra nhiều worker/instance, cần cấu hình storage
dùng chung (vd: Redis) để giới hạn đúng trên toàn hệ thống.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
