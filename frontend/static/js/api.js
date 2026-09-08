// Wrapper gọi Fetch API tới backend + các hằng số/hàm tiện ích dùng chung
// cho toàn bộ frontend (login.html, index.html, ticket_detail.html).

const API_BASE = "/api/v1";
const TOKEN_KEY = "cs_ai_token";
const USER_KEY = "cs_ai_user";

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function getCurrentUser() {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

function saveSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function logout() {
  clearSession();
  window.location.href = "/login";
}

/** Gọi ở đầu mỗi trang cần đăng nhập. Trả về user hiện tại, hoặc chuyển hướng về /login. */
function requireAuth() {
  const user = getCurrentUser();
  if (!getToken() || !user) {
    window.location.href = "/login";
    return null;
  }
  return user;
}

/**
 * Gọi API kèm sẵn Authorization header + xử lý lỗi chung.
 * Tự động đăng xuất nếu token hết hạn/không hợp lệ (401).
 */
async function apiFetch(path, options = {}) {
  const headers = options.headers ? { ...options.headers } : {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body && !(options.body instanceof URLSearchParams)) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (response.status === 401) {
    clearSession();
    window.location.href = "/login";
    throw new Error("Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.");
  }

  if (!response.ok) {
    let detail = `Lỗi ${response.status}`;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch (_) {
      /* phản hồi không phải JSON, giữ nguyên detail mặc định */
    }
    throw new Error(detail);
  }

  if (response.status === 204) return null;
  return response.json();
}

// --- Bảng tra cứu label/màu cho status & priority (khớp với tailwind.config ở mỗi trang) ---
const STATUS_META = {
  new: { label: "Mới", dot: "bg-status-new", text: "text-status-new" },
  processing: { label: "Đang xử lý", dot: "bg-status-processing", text: "text-status-processing" },
  waiting: { label: "Chờ phản hồi", dot: "bg-status-waiting", text: "text-status-waiting" },
  closed: { label: "Đã đóng", dot: "bg-status-closed", text: "text-status-closed" },
};

const PRIORITY_META = {
  low: { label: "Thấp", bar: "bg-priority-low", text: "text-priority-low" },
  medium: { label: "Trung bình", bar: "bg-priority-medium", text: "text-priority-medium" },
  high: { label: "Cao", bar: "bg-priority-high", text: "text-priority-high" },
};

const SENDER_LABEL = {
  customer: "Khách hàng",
  agent: "Nhân viên",
  system: "Hệ thống",
  bot: "Trợ lý ảo (tự động)",
};

const ROLE_LABEL = {
  admin: "Admin",
  manager: "Manager",
  agent: "Agent",
};

const ORDER_STATUS_LABEL = {
  pending: "Chờ xác nhận",
  confirmed: "Đã xác nhận",
  shipping: "Đang giao",
  completed: "Hoàn tất",
  cancelled: "Đã huỷ",
};

function formatCurrency(amount) {
  const n = Number(amount) || 0;
  return n.toLocaleString("vi-VN") + " đ";
}

function formatDateTime(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}
