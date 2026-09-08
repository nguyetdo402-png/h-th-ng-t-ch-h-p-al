/**
 * app.js — Logic UI chính của Dashboard (Single Page).
 *
 * Trang index.html có 2 "view" cùng tồn tại trong DOM, JS chỉ ẩn/hiện chứ
 * không reload trang:
 *   - #view-list   : danh sách ticket + bộ lọc trạng thái/ưu tiên
 *   - #view-detail : chi tiết 1 ticket, gồm lịch sử hội thoại + gợi ý AI
 *
 * Điều hướng giữa 2 view dùng location.hash (không cần route phía server):
 *   #/tickets        -> view-list
 *   #/tickets/{id}    -> view-detail cho ticket id đó
 *
 * File này phụ thuộc vào api.js (đã include trước nó trong index.html) để
 * lấy: apiFetch(), requireAuth(), logout(), STATUS_META, PRIORITY_META,
 * SENDER_LABEL, ROLE_LABEL, formatDateTime(), escapeHtml().
 */

const currentUser = requireAuth();
const isPrivileged = currentUser && (currentUser.role === "admin" || currentUser.role === "manager");

if (currentUser && currentUser.role === "agent") {
  // Agent chỉ xem được ticket của chính mình (API cũng đã ép filter tương
  // ứng) — đổi tiêu đề để rõ ràng, tránh hiểu nhầm đây là toàn bộ ticket.
  document.getElementById("ticket-list-heading").textContent = "Ticket của tôi";
}

document.getElementById("current-user-label").textContent = currentUser
  ? `${currentUser.name} (${ROLE_LABEL[currentUser.role] || currentUser.role})`
  : "";
document.getElementById("logout-btn").addEventListener("click", logout);

const viewList = document.getElementById("view-list");
const viewDetail = document.getElementById("view-detail");
const viewUsers = document.getElementById("view-users");
const viewFaqs = document.getElementById("view-faqs");
const viewProducts = document.getElementById("view-products");
const viewOrders = document.getElementById("view-orders");

const navUsersBtn = document.getElementById("nav-users-btn");
const navFaqsBtn = document.getElementById("nav-faqs-btn");
const navTicketsBtn = document.getElementById("nav-tickets-btn");
const navProductsBtn = document.getElementById("nav-products-btn");
const navOrdersBtn = document.getElementById("nav-orders-btn");
if (isPrivileged) {
  navUsersBtn.classList.remove("hidden");
  navUsersBtn.addEventListener("click", () => { window.location.hash = "#/users"; });
  navFaqsBtn.classList.remove("hidden");
  navFaqsBtn.addEventListener("click", () => { window.location.hash = "#/faqs"; });
  document.getElementById("open-create-faq").classList.remove("hidden");
}
navTicketsBtn.addEventListener("click", goToList);
navProductsBtn.addEventListener("click", () => { window.location.hash = "#/products"; });
navOrdersBtn.addEventListener("click", () => { window.location.hash = "#/orders"; });
if (currentUser && currentUser.role === "admin") {
  document.getElementById("open-create-user").classList.remove("hidden");
}
if (isPrivileged) {
  document.getElementById("open-create-product").classList.remove("hidden");
}
if (!isPrivileged) {
  // Agent không được tự tạo ticket thủ công (khớp phân quyền backend:
  // POST /tickets giờ chỉ admin/manager) — ẩn hẳn nút để tránh nhầm lẫn.
  document.getElementById("open-create-ticket").classList.add("hidden");
}

// =====================================================================
// ROUTER — chuyển view dựa trên location.hash, không reload trang
// =====================================================================

function parseRoute() {
  const hash = window.location.hash; // vd: "#/tickets/12", "#/tickets", "#/users", "#/products", "#/orders", ""
  const match = hash.match(/^#\/tickets\/(\d+)$/);
  if (match) return { view: "detail", ticketId: Number(match[1]) };
  if (hash === "#/users" && isPrivileged) return { view: "users" };
  if (hash === "#/faqs" && isPrivileged) return { view: "faqs" };
  if (hash === "#/products") return { view: "products" };
  if (hash === "#/orders") return { view: "orders" };
  return { view: "list" };
}

function goToList() {
  window.location.hash = "#/tickets";
}

function goToDetail(ticketId) {
  window.location.hash = `#/tickets/${ticketId}`;
}

async function renderRoute() {
  const route = parseRoute();

  viewList.classList.add("hidden");
  viewDetail.classList.add("hidden");
  viewUsers.classList.add("hidden");
  viewFaqs.classList.add("hidden");
  viewProducts.classList.add("hidden");
  viewOrders.classList.add("hidden");

  if (route.view === "detail") {
    viewDetail.classList.remove("hidden");
    await loadTicketDetail(route.ticketId);
  } else if (route.view === "users") {
    viewUsers.classList.remove("hidden");
    await loadUserList();
  } else if (route.view === "faqs") {
    viewFaqs.classList.remove("hidden");
    await loadFaqList();
  } else if (route.view === "products") {
    viewProducts.classList.remove("hidden");
    await loadProductList();
  } else if (route.view === "orders") {
    viewOrders.classList.remove("hidden");
    await loadOrderList();
  } else {
    viewList.classList.remove("hidden");
    await loadTicketList();
  }
}

window.addEventListener("hashchange", renderRoute);
document.getElementById("back-to-list-btn").addEventListener("click", goToList);

// =====================================================================
// VIEW: DANH SÁCH TICKET + BỘ LỌC
// =====================================================================

let activeStatus = null;   // null = "Tất cả"
let activePriority = null; // null = "Tất cả"
let activeAgentId = null;  // null = "Tất cả nhân viên" — set khi bấm số liệu ở trang Nhân viên
let activeAgentName = null;
let listLoaded = false;    // để chỉ render filter chips 1 lần

/** Điều hướng sang danh sách ticket, lọc sẵn theo 1 agent cụ thể (dùng từ trang Nhân viên). */
function goToTicketsForAgent(agentId, agentName) {
  activeAgentId = agentId;
  activeAgentName = agentName;
  activeStatus = null;
  window.location.hash = "#/tickets";
}

function renderFilterChips(containerId, meta, activeValue, onSelect) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";

  const makeChip = (value, label) => {
    const btn = document.createElement("button");
    const isActive = activeValue === value;
    btn.type = "button";
    btn.textContent = label;
    btn.className = [
      "text-xs px-3 py-1.5 rounded-full border transition-colors",
      isActive ? "bg-ink text-white border-ink" : "border-line text-subtle hover:border-ink hover:text-ink",
    ].join(" ");
    btn.addEventListener("click", () => onSelect(value));
    return btn;
  };

  container.appendChild(makeChip(null, "Tất cả"));
  for (const [value, m] of Object.entries(meta)) {
    container.appendChild(makeChip(value, m.label));
  }
}

function renderFilters() {
  renderFilterChips("status-filters", STATUS_META, activeStatus, (v) => {
    activeStatus = v;
    renderFilters();
    loadTicketList();
  });
  renderFilterChips("priority-filters", PRIORITY_META, activePriority, (v) => {
    activePriority = v;
    renderFilters();
    loadTicketList();
  });

  const agentBanner = document.getElementById("agent-filter-banner");
  if (activeAgentId) {
    agentBanner.classList.remove("hidden");
    agentBanner.querySelector("span").textContent = `Đang lọc theo nhân viên: ${activeAgentName || "#" + activeAgentId}`;
  } else {
    agentBanner.classList.add("hidden");
  }

  listLoaded = true;
}

document.getElementById("agent-filter-clear-btn").addEventListener("click", () => {
  activeAgentId = null;
  activeAgentName = null;
  renderFilters();
  loadTicketList();
});

// ---- Banner "Cần xử lý ưu tiên" (đầu trang danh sách) ----

async function loadPriorityQueue() {
  const banner = document.getElementById("priority-queue-banner");
  const list = document.getElementById("priority-queue-list");

  let tickets;
  try {
    tickets = await apiFetch("/tickets/priority-queue?limit=4");
  } catch (_) {
    banner.classList.add("hidden");
    return;
  }

  if (!tickets || tickets.length === 0) {
    banner.classList.add("hidden");
    return;
  }

  list.innerHTML = "";
  for (const ticket of tickets) {
    const statusMeta = STATUS_META[ticket.status];
    const priorityMeta = PRIORITY_META[ticket.priority];

    const card = document.createElement("button");
    card.type = "button";
    card.className =
      "text-left bg-white border border-line rounded-2xl p-3.5 shadow-[0_16px_36px_-28px_rgba(47,127,189,0.35)] hover:-translate-y-0.5 transition-transform";
    card.addEventListener("click", () => goToDetail(ticket.id));

    card.innerHTML = `
      <div class="flex items-center justify-between mb-1.5">
        <span class="inline-flex items-center gap-1.5 text-xs font-semibold ${priorityMeta.text}">
          <span class="inline-block w-1.5 h-1.5 rounded-full ${priorityMeta.bar}"></span>
          ${priorityMeta.label}
        </span>
        ${
          ticket.priority_source === "ai"
            ? '<span class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-brand-light text-brand-dark">🤖 AI</span>'
            : ""
        }
      </div>
      <p class="text-sm font-medium text-ink line-clamp-2 mb-1.5">${escapeHtml(ticket.title)}</p>
      <span class="inline-flex items-center gap-1 text-xs text-subtle">
        <span class="inline-block w-1.5 h-1.5 rounded-full ${statusMeta.dot}"></span>
        ${statusMeta.label} · #${ticket.id}
      </span>
    `;
    list.appendChild(card);
  }
  banner.classList.remove("hidden");
}

async function loadTicketList() {
  renderFilters();
  loadPriorityQueue();

  const tbody = document.getElementById("ticket-table-body");
  const emptyState = document.getElementById("empty-state");
  const loadingState = document.getElementById("list-loading-state");

  emptyState.classList.add("hidden");
  loadingState.classList.remove("hidden");
  tbody.innerHTML = "";

  const params = new URLSearchParams();
  if (activeStatus) params.set("status", activeStatus);
  if (activePriority) params.set("priority", activePriority);
  if (activeAgentId) params.set("assigned_to_agent_id", activeAgentId);

  let tickets;
  try {
    tickets = await apiFetch(`/tickets?${params.toString()}`);
  } finally {
    loadingState.classList.add("hidden");
  }

  if (tickets.length === 0) {
    emptyState.classList.remove("hidden");
    return;
  }

  for (const ticket of tickets) {
    const statusMeta = STATUS_META[ticket.status];
    const priorityMeta = PRIORITY_META[ticket.priority];

    const tr = document.createElement("tr");
    tr.className = "border-b border-line last:border-0 hover:bg-canvas cursor-pointer transition-colors";
    tr.addEventListener("click", () => goToDetail(ticket.id));

    tr.innerHTML = `
      <td class="px-4 py-3 text-subtle">#${ticket.id}</td>
      <td class="px-4 py-3 font-medium">${escapeHtml(ticket.title)}</td>
      <td class="px-4 py-3">
        <span class="inline-flex items-center gap-1.5">
          <span class="inline-block w-1 h-3.5 rounded-sm ${priorityMeta.bar}"></span>
          <span class="${priorityMeta.text}">${priorityMeta.label}</span>
          ${
            ticket.priority_source === "ai"
              ? '<span class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-brand-light text-brand-dark">🤖 AI</span>'
              : ""
          }
        </span>
      </td>
      <td class="px-4 py-3">
        <span class="inline-flex items-center gap-1.5">
          <span class="inline-block w-1.5 h-1.5 rounded-full ${statusMeta.dot}"></span>
          <span>${statusMeta.label}</span>
        </span>
      </td>
      <td class="px-4 py-3 text-subtle text-xs">${formatDateTime(ticket.updated_at)}</td>
    `;
    tbody.appendChild(tr);
  }
}

// ---- Modal: Tạo ticket mới (thuộc view danh sách) ----

const createTicketModal = document.getElementById("create-ticket-modal");
const customerSelect = document.getElementById("ticket-customer-select");

async function loadCustomersIntoSelect(selectId = null) {
  const customers = await apiFetch("/customers?limit=200");
  customerSelect.innerHTML = '<option value="">— Chọn khách hàng —</option>';
  for (const c of customers) {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = `${c.name} (${c.email})`;
    customerSelect.appendChild(opt);
  }
  if (selectId) customerSelect.value = selectId;
}

function openCreateTicketModal() {
  document.getElementById("create-ticket-form").reset();
  document.getElementById("create-ticket-error").classList.add("hidden");
  document.getElementById("new-customer-fields").classList.add("hidden");
  document.getElementById("new-customer-error").classList.add("hidden");

  // Chỉ admin/manager mới được tạo khách hàng mới (khớp phân quyền backend).
  document.getElementById("toggle-new-customer").classList.toggle("hidden", !isPrivileged);

  loadCustomersIntoSelect();
  createTicketModal.classList.remove("hidden");
}

function closeCreateTicketModal() {
  createTicketModal.classList.add("hidden");
}

document.getElementById("open-create-ticket").addEventListener("click", openCreateTicketModal);
document.getElementById("close-create-ticket").addEventListener("click", closeCreateTicketModal);
document.getElementById("cancel-create-ticket").addEventListener("click", closeCreateTicketModal);

document.getElementById("toggle-new-customer").addEventListener("click", () => {
  document.getElementById("new-customer-fields").classList.toggle("hidden");
});

document.getElementById("save-new-customer").addEventListener("click", async () => {
  const errorEl = document.getElementById("new-customer-error");
  errorEl.classList.add("hidden");
  try {
    const payload = {
      name: document.getElementById("new-customer-name").value.trim(),
      email: document.getElementById("new-customer-email").value.trim(),
      phone: document.getElementById("new-customer-phone").value.trim() || null,
    };
    if (!payload.name || !payload.email) {
      throw new Error("Vui lòng nhập đủ họ tên và email khách hàng.");
    }
    const newCustomer = await apiFetch("/customers", { method: "POST", body: JSON.stringify(payload) });
    await loadCustomersIntoSelect(newCustomer.id);
    document.getElementById("new-customer-fields").classList.add("hidden");
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

document.getElementById("create-ticket-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorEl = document.getElementById("create-ticket-error");
  errorEl.classList.add("hidden");

  try {
    const customerId = customerSelect.value;
    if (!customerId) throw new Error("Vui lòng chọn khách hàng.");

    const payload = {
      customer_id: Number(customerId),
      title: document.getElementById("ticket-title-input").value.trim(),
      description: document.getElementById("ticket-description-input").value.trim(),
      priority: document.getElementById("ticket-priority-input").value,
    };

    const ticket = await apiFetch("/tickets", { method: "POST", body: JSON.stringify(payload) });

    closeCreateTicketModal();
    goToDetail(ticket.id);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

// =====================================================================
// VIEW: CHI TIẾT TICKET
// =====================================================================

let currentTicket = null;
let currentDraft = null; // draft AI đang chờ duyệt (nếu có)

async function loadTicketDetail(ticketId) {
  // Reset trạng thái AI draft khi chuyển sang ticket khác.
  currentDraft = null;
  document.getElementById("draft-panel").classList.add("hidden");
  document.getElementById("draft-error-msg").classList.add("hidden");
  document.getElementById("no-draft-msg").classList.remove("hidden");

  currentTicket = await apiFetch(`/tickets/${ticketId}`);

  document.getElementById("ticket-id-label").textContent = `Ticket #${currentTicket.id}`;
  document.getElementById("ticket-title").textContent = currentTicket.title;
  document.getElementById("ticket-description").textContent = currentTicket.description;

  const categoryBadge = document.getElementById("ticket-category-badge");
  if (currentTicket.category) {
    categoryBadge.textContent = `AI: ${currentTicket.category}`;
    categoryBadge.classList.remove("hidden");
  } else {
    categoryBadge.classList.add("hidden");
  }

  const orderBox = document.getElementById("ticket-order-box");
  if (currentTicket.order) {
    document.getElementById("ticket-order-id").textContent = `#${currentTicket.order.id}`;
    document.getElementById("ticket-order-status").textContent =
      `Trạng thái: ${ORDER_STATUS_LABEL[currentTicket.order.status] || currentTicket.order.status}`;
    document.getElementById("ticket-order-total").textContent =
      `Tổng tiền: ${formatCurrency(currentTicket.order.total_amount)}`;
    orderBox.classList.remove("hidden");
  } else {
    orderBox.classList.add("hidden");
  }

  renderStatusSelect();
  renderPrioritySelect();

  const customer = await apiFetch(`/customers/${currentTicket.customer_id}`);
  document.getElementById("customer-name").textContent = customer.name;
  document.getElementById("customer-email").textContent = customer.email;
  document.getElementById("customer-phone").textContent = customer.phone || "—";

  await loadAgentsIntoSelect();
  await loadInteractions();
  await loadLatestPendingDraft();
  await loadFaqSuggestions(ticketId);
}

async function loadFaqSuggestions(ticketId) {
  const panel = document.getElementById("faq-suggestions-panel");
  const list = document.getElementById("faq-suggestions-list");
  list.innerHTML = "";

  try {
    const matches = await apiFetch(`/tickets/${ticketId}/faq-suggestions`);
    if (matches.length === 0) {
      panel.classList.add("hidden");
      return;
    }
    panel.classList.remove("hidden");

    for (const faq of matches) {
      const card = document.createElement("div");
      card.className = "border border-line rounded-md p-4";
      card.innerHTML = `
        <div class="flex items-start justify-between gap-3 mb-1">
          <p class="text-sm font-medium">${escapeHtml(faq.question)}</p>
          <button data-faq-id="${faq.id}" class="use-faq-btn shrink-0 text-xs border border-line rounded-md px-2.5 py-1 hover:bg-canvas transition-colors">
            Dùng câu này
          </button>
        </div>
        <p class="text-sm text-subtle whitespace-pre-wrap mb-2">${escapeHtml(faq.answer)}</p>
        <p class="text-xs text-subtle">Khớp từ khóa: ${faq.matched_keywords.map(escapeHtml).join(", ")}</p>
      `;
      list.appendChild(card);
    }

    // Tra cứu answer qua id (thay vì nhúng thẳng vào data-attribute) để tránh
    // vấn đề escaping khi answer chứa dấu ngoặc kép (escapeHtml không escape
    // quote vì nó chỉ cần an toàn cho text content, không phải attribute).
    const answerById = Object.fromEntries(matches.map((m) => [String(m.id), m.answer]));
    list.querySelectorAll(".use-faq-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const contentInput = document.getElementById("interaction-content");
        contentInput.value = answerById[btn.dataset.faqId] || "";
        contentInput.focus();
      });
    });
  } catch (err) {
    // Không tìm thấy FAQ liên quan hoặc lỗi tải -> ẩn panel, không làm phiền agent.
    panel.classList.add("hidden");
  }
}

function renderStatusSelect() {
  const select = document.getElementById("status-select");
  select.innerHTML = "";
  for (const [value, meta] of Object.entries(STATUS_META)) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = meta.label;
    if (value === currentTicket.status) opt.selected = true;
    select.appendChild(opt);
  }
}

function renderPrioritySelect() {
  const select = document.getElementById("priority-select");
  select.innerHTML = "";
  for (const [value, meta] of Object.entries(PRIORITY_META)) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = meta.label;
    if (value === currentTicket.priority) opt.selected = true;
    select.appendChild(opt);
  }
  select.disabled = !isPrivileged;
  document.getElementById("priority-permission-note").classList.toggle("hidden", isPrivileged);
  document
    .getElementById("priority-source-badge")
    .classList.toggle("hidden", currentTicket.priority_source !== "ai");
}

async function loadAgentsIntoSelect() {
  const agentSelect = document.getElementById("agent-select");
  const agents = await apiFetch("/users?role=agent");
  agentSelect.innerHTML = '<option value="">— Chưa phân công —</option>';
  for (const a of agents) {
    const opt = document.createElement("option");
    opt.value = a.id;
    opt.textContent = a.name;
    if (currentTicket.assigned_to_agent_id === a.id) opt.selected = true;
    agentSelect.appendChild(opt);
  }
  agentSelect.disabled = !isPrivileged;
  document.getElementById("assign-permission-note").classList.toggle("hidden", isPrivileged);
}

function showSidebarError(message) {
  const el = document.getElementById("sidebar-error-msg");
  el.textContent = message;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 4000);
}

document.getElementById("status-select").addEventListener("change", async (e) => {
  try {
    await apiFetch(`/tickets/${currentTicket.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: e.target.value }),
    });
    await loadTicketDetail(currentTicket.id);
  } catch (err) {
    showSidebarError(err.message);
    renderStatusSelect();
  }
});

document.getElementById("priority-select").addEventListener("change", async (e) => {
  try {
    await apiFetch(`/tickets/${currentTicket.id}`, {
      method: "PUT",
      body: JSON.stringify({ priority: e.target.value }),
    });
    await loadTicketDetail(currentTicket.id);
  } catch (err) {
    showSidebarError(err.message);
    renderPrioritySelect();
  }
});

document.getElementById("ai-priority-btn").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  const errorEl = document.getElementById("ai-priority-error");
  errorEl.classList.add("hidden");
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = "Đang hỏi AI...";
  try {
    await apiFetch(`/tickets/${currentTicket.id}/ai-priority`, { method: "POST" });
    await loadTicketDetail(currentTicket.id);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
});

document.getElementById("agent-select").addEventListener("change", async (e) => {
  const value = e.target.value;
  if (!value) return; // API hiện chưa hỗ trợ bỏ gán, chỉ hỗ trợ gán mới
  try {
    await apiFetch(`/tickets/${currentTicket.id}/assign`, {
      method: "PATCH",
      body: JSON.stringify({ agent_id: Number(value) }),
    });
    await loadTicketDetail(currentTicket.id);
  } catch (err) {
    showSidebarError(err.message);
    await loadAgentsIntoSelect();
  }
});

// ---- Lịch sử hội thoại ----

function interactionBubbleClass(senderType) {
  if (senderType === "customer") return "bg-canvas border border-line mr-auto";
  if (senderType === "agent") return "bg-brand-light ml-auto";
  if (senderType === "bot") return "bg-white border border-dashed border-brand/50 mr-auto";
  return "bg-transparent text-subtle text-xs italic mx-auto text-center";
}

async function loadInteractions() {
  const interactions = await apiFetch(`/tickets/${currentTicket.id}/interactions`);
  const list = document.getElementById("interaction-list");
  list.innerHTML = "";

  for (const item of interactions) {
    // Tin nhắn "system" (audit log nội bộ: phân công, lỗi phân loại AI, đổi
    // trạng thái tự động...) không hiển thị trong khung hội thoại — chỉ mang
    // tính ghi vết ở tầng dữ liệu, hiện lên đây gây rối và không cần thiết
    // với agent/khách hàng.
    if (item.sender_type === "system") continue;

    const wrapper = document.createElement("div");
    wrapper.className = "max-w-[75%] " + (item.sender_type === "agent" ? "ml-auto" : "mr-auto");

    const bubble = document.createElement("div");
    bubble.className = "rounded-md px-3 py-2 text-sm " + interactionBubbleClass(item.sender_type);
    if (item.attachment_url) {
      // Ảnh/video khách (hoặc agent, nếu sau này agent cũng gửi được) đính
      // kèm — hiện media trực tiếp thay vì chỉ hiện chữ placeholder.
      bubble.classList.add("p-1.5");
      if (item.attachment_type === "video") {
        const video = document.createElement("video");
        video.src = item.attachment_url;
        video.controls = true;
        video.className = "max-w-[240px] max-h-[240px] rounded";
        bubble.appendChild(video);
      } else {
        const img = document.createElement("img");
        img.src = item.attachment_url;
        img.alt = item.attachment_filename || "Hình ảnh đính kèm";
        img.className = "max-w-[220px] max-h-[220px] rounded cursor-pointer";
        img.addEventListener("click", () => window.open(item.attachment_url, "_blank"));
        bubble.appendChild(img);
      }
    } else {
      bubble.textContent = item.content;
    }

    const meta = document.createElement("p");
    meta.className = "text-[11px] text-subtle mt-1 " + (item.sender_type === "agent" ? "text-right" : "text-left");
    meta.textContent = `${SENDER_LABEL[item.sender_type]} · ${formatDateTime(item.created_at)}`;

    wrapper.appendChild(bubble);
    wrapper.appendChild(meta);
    list.appendChild(wrapper);
  }

  list.scrollTop = list.scrollHeight;
}

document.getElementById("add-interaction-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  // Nhân viên gửi tin nhắn thì luôn là "agent" — không cho chọn giả danh
  // khách hàng/hệ thống nữa (bỏ dropdown chọn vai trò trước đây).
  const senderType = "agent";
  const contentInput = document.getElementById("interaction-content");
  const content = contentInput.value.trim();
  if (!content) return;

  try {
    await apiFetch(`/tickets/${currentTicket.id}/interactions`, {
      method: "POST",
      body: JSON.stringify({ sender_type: senderType, content }),
    });
    contentInput.value = "";
    await loadInteractions();
  } catch (err) {
    showSidebarError(err.message);
  }
});

// =====================================================================
// GỢI Ý AI + NÚT DUYỆT CÂU TRẢ LỜI NHÁP
// =====================================================================

function showDraft(draft) {
  currentDraft = draft;
  document.getElementById("no-draft-msg").classList.add("hidden");
  document.getElementById("draft-panel").classList.remove("hidden");
  document.getElementById("draft-category").textContent = draft.suggested_category || "—";
  document.getElementById("draft-priority").textContent =
    PRIORITY_META[draft.suggested_priority]?.label || "—";
  document.getElementById("draft-textarea").value = draft.draft_response;
}

function hideDraftPanel() {
  currentDraft = null;
  document.getElementById("draft-panel").classList.add("hidden");
  document.getElementById("no-draft-msg").classList.remove("hidden");
}

async function loadLatestPendingDraft() {
  const drafts = await apiFetch(`/tickets/${currentTicket.id}/ai-drafts`);
  const pending = drafts.find((d) => !d.is_approved);
  if (pending) {
    showDraft(pending);
  } else {
    hideDraftPanel();
  }
}

async function generateDraft() {
  const errorEl = document.getElementById("draft-error-msg");
  const loadingEl = document.getElementById("draft-loading-msg");
  errorEl.classList.add("hidden");
  document.getElementById("no-draft-msg").classList.add("hidden");
  document.getElementById("draft-panel").classList.add("hidden");
  loadingEl.classList.remove("hidden");

  try {
    const draft = await apiFetch(`/tickets/${currentTicket.id}/ai-draft`, { method: "POST" });
    showDraft(draft);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
    document.getElementById("no-draft-msg").classList.remove("hidden");
  } finally {
    loadingEl.classList.add("hidden");
  }
}

document.getElementById("generate-draft-btn").addEventListener("click", generateDraft);
document.getElementById("regenerate-draft-btn").addEventListener("click", generateDraft);

/**
 * NÚT "Duyệt & Gửi": đây là bước DUY NHẤT trong toàn bộ frontend khiến câu
 * trả lời của AI được coi là đã gửi cho khách hàng — gọi PATCH
 * /ai-drafts/{id}/approve, backend sẽ copy nội dung (đã/chưa chỉnh sửa)
 * sang InteractionHistory. Trước khi bấm nút này, mọi nội dung AI sinh ra
 * chỉ nằm trong bảng AiDraft với is_approved=false, chưa đến tay khách hàng.
 */
document.getElementById("approve-draft-btn").addEventListener("click", async () => {
  if (!currentDraft) return;
  const errorEl = document.getElementById("draft-error-msg");
  errorEl.classList.add("hidden");

  try {
    const edited = document.getElementById("draft-textarea").value.trim();
    const payload = edited && edited !== currentDraft.draft_response ? { edited_response: edited } : {};

    await apiFetch(`/ai-drafts/${currentDraft.id}/approve`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });

    hideDraftPanel();
    await loadInteractions();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

// =====================================================================
// VIEW 3: QUẢN LÝ NHÂN VIÊN (chỉ admin/manager truy cập được, xem router)
// =====================================================================

async function loadUserList() {
  const tbody = document.getElementById("user-table-body");
  const loadingEl = document.getElementById("user-loading-state");
  const emptyEl = document.getElementById("user-empty-state");

  tbody.innerHTML = "";
  emptyEl.classList.add("hidden");
  loadingEl.classList.remove("hidden");

  try {
    // /stats/agents chỉ trả về agent nào có username hoạt động;
    // nếu lỗi (vd role không đủ quyền) vẫn hiển thị được bảng nhân viên, chỉ thiếu 2 cột số liệu.
    const [users, agentStats] = await Promise.all([
      apiFetch("/users?limit=200"),
      apiFetch("/stats/agents").catch(() => []),
    ]);
    loadingEl.classList.add("hidden");

    if (users.length === 0) {
      emptyEl.classList.remove("hidden");
      return;
    }

    const statsByAgentId = {};
    for (const s of agentStats) statsByAgentId[s.agent_id] = s;

    for (const user of users) {
      const tr = document.createElement("tr");
      tr.className = "border-b border-line last:border-0";

      const isAdmin = currentUser && currentUser.role === "admin";
      const deactivateBtn = isAdmin && user.is_active && user.id !== currentUser.id
        ? `<button data-user-id="${user.id}" class="deactivate-user-btn text-xs text-priority-high hover:underline">Vô hiệu hoá</button>`
        : "";

      const stat = statsByAgentId[user.id];
      const openCell = stat
        ? `<button data-agent-id="${user.id}" data-agent-name="${escapeHtml(user.name)}" class="agent-open-count-btn font-semibold text-brand-dark hover:underline">${stat.total_open}</button>`
        : `<span class="text-subtle">—</span>`;
      const closedCell = stat ? stat.total_closed : "—";

      tr.innerHTML = `
        <td class="px-4 py-3">${escapeHtml(user.name)}</td>
        <td class="px-4 py-3 text-subtle">${escapeHtml(user.email)}</td>
        <td class="px-4 py-3">${ROLE_LABEL[user.role] || user.role}</td>
        <td class="px-4 py-3">${user.is_active ? "Đang hoạt động" : "Đã vô hiệu hoá"}</td>
        <td class="px-4 py-3 text-right">${openCell}</td>
        <td class="px-4 py-3 text-right text-subtle">${closedCell}</td>
        <td class="px-4 py-3 text-right">${deactivateBtn}</td>
      `;
      tbody.appendChild(tr);
    }

    tbody.querySelectorAll(".deactivate-user-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Vô hiệu hoá tài khoản này? Nhân viên sẽ không đăng nhập được nữa.")) return;
        try {
          await apiFetch(`/users/${btn.dataset.userId}/deactivate`, { method: "PATCH" });
          await loadUserList();
        } catch (err) {
          alert(err.message);
        }
      });
    });

    tbody.querySelectorAll(".agent-open-count-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        goToTicketsForAgent(Number(btn.dataset.agentId), btn.dataset.agentName);
      });
    });
  } catch (err) {
    loadingEl.textContent = `Lỗi tải danh sách: ${err.message}`;
  }
}

const createUserModal = document.getElementById("create-user-modal");
document.getElementById("open-create-user").addEventListener("click", () => {
  document.getElementById("create-user-error").classList.add("hidden");
  document.getElementById("create-user-form").reset();
  createUserModal.classList.remove("hidden");
});
document.getElementById("close-create-user").addEventListener("click", () => createUserModal.classList.add("hidden"));
document.getElementById("cancel-create-user").addEventListener("click", () => createUserModal.classList.add("hidden"));

document.getElementById("create-user-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("create-user-error");
  errorEl.classList.add("hidden");

  const payload = {
    name: document.getElementById("new-user-name").value.trim(),
    email: document.getElementById("new-user-email").value.trim(),
    password: document.getElementById("new-user-password").value,
    role: document.getElementById("new-user-role").value,
  };

  try {
    await apiFetch("/auth/register", { method: "POST", body: JSON.stringify(payload) });
    createUserModal.classList.add("hidden");
    await loadUserList();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

// =====================================================================
// VIEW: QUẢN LÝ FAQ (chỉ admin/manager truy cập được, xem router)
// =====================================================================

async function loadFaqList() {
  const tbody = document.getElementById("faq-table-body");
  const loadingEl = document.getElementById("faq-loading-state");
  const emptyEl = document.getElementById("faq-empty-state");

  tbody.innerHTML = "";
  emptyEl.classList.add("hidden");
  loadingEl.classList.remove("hidden");

  try {
    const faqs = await apiFetch("/faqs");
    loadingEl.classList.add("hidden");

    if (faqs.length === 0) {
      emptyEl.classList.remove("hidden");
      return;
    }

    for (const faq of faqs) {
      const tr = document.createElement("tr");
      tr.className = "border-b border-line last:border-0 align-top";
      tr.innerHTML = `
        <td class="px-4 py-3 font-medium">${escapeHtml(faq.question)}</td>
        <td class="px-4 py-3 text-subtle">${escapeHtml(faq.keywords)}</td>
        <td class="px-4 py-3 text-subtle">${escapeHtml(faq.answer.slice(0, 120))}${faq.answer.length > 120 ? "…" : ""}</td>
        <td class="px-4 py-3">${faq.is_active ? "Đang bật" : "Đã tắt"}</td>
        <td class="px-4 py-3 text-right whitespace-nowrap">
          <button data-faq-id="${faq.id}" class="edit-faq-btn text-xs text-brand hover:underline mr-3">Sửa</button>
          <button data-faq-id="${faq.id}" class="delete-faq-btn text-xs text-priority-high hover:underline">Xoá</button>
        </td>
      `;
      tbody.appendChild(tr);
    }

    const faqById = Object.fromEntries(faqs.map((f) => [String(f.id), f]));

    tbody.querySelectorAll(".edit-faq-btn").forEach((btn) => {
      btn.addEventListener("click", () => openFaqModal(faqById[btn.dataset.faqId]));
    });
    tbody.querySelectorAll(".delete-faq-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Xoá FAQ này? Không thể hoàn tác.")) return;
        try {
          await apiFetch(`/faqs/${btn.dataset.faqId}`, { method: "DELETE" });
          await loadFaqList();
        } catch (err) {
          alert(err.message);
        }
      });
    });
  } catch (err) {
    loadingEl.textContent = `Lỗi tải danh sách: ${err.message}`;
  }
}

const faqModal = document.getElementById("faq-modal");

function openFaqModal(faq) {
  document.getElementById("faq-form-error").classList.add("hidden");
  document.getElementById("faq-form").reset();
  document.getElementById("faq-id").value = faq ? faq.id : "";
  document.getElementById("faq-modal-title").textContent = faq ? "Sửa FAQ" : "Thêm FAQ";
  document.getElementById("faq-question").value = faq ? faq.question : "";
  document.getElementById("faq-keywords").value = faq ? faq.keywords : "";
  document.getElementById("faq-answer").value = faq ? faq.answer : "";
  document.getElementById("faq-is-active").checked = faq ? faq.is_active : true;
  faqModal.classList.remove("hidden");
}

document.getElementById("open-create-faq").addEventListener("click", () => openFaqModal(null));
document.getElementById("close-faq-modal").addEventListener("click", () => faqModal.classList.add("hidden"));
document.getElementById("cancel-faq-form").addEventListener("click", () => faqModal.classList.add("hidden"));

document.getElementById("faq-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("faq-form-error");
  errorEl.classList.add("hidden");

  const faqId = document.getElementById("faq-id").value;
  const payload = {
    question: document.getElementById("faq-question").value.trim(),
    keywords: document.getElementById("faq-keywords").value.trim(),
    answer: document.getElementById("faq-answer").value.trim(),
    is_active: document.getElementById("faq-is-active").checked,
  };

  try {
    if (faqId) {
      await apiFetch(`/faqs/${faqId}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await apiFetch("/faqs", { method: "POST", body: JSON.stringify(payload) });
    }
    faqModal.classList.add("hidden");
    await loadFaqList();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

// =====================================================================
// VIEW: SẢN PHẨM & KHO
// =====================================================================

async function loadProductList() {
  const tbody = document.getElementById("product-table-body");
  const loadingEl = document.getElementById("product-loading-state");
  const emptyEl = document.getElementById("product-empty-state");

  tbody.innerHTML = "";
  emptyEl.classList.add("hidden");
  loadingEl.classList.remove("hidden");

  try {
    const products = await apiFetch("/products?limit=200");
    loadingEl.classList.add("hidden");

    if (products.length === 0) {
      emptyEl.classList.remove("hidden");
      return;
    }

    for (const product of products) {
      const tr = document.createElement("tr");
      tr.className = "border-b border-line last:border-0 align-top";

      const variantList = product.variants
        .map((v) => `${escapeHtml(v.size)}/${escapeHtml(v.color)}: <span class="${v.stock_quantity === 0 ? "text-priority-high" : ""}">${v.stock_quantity}</span>`)
        .join(" · ") || "<span class=\"text-subtle\">Chưa có variant</span>";

      const addVariantBtn = isPrivileged
        ? `<button data-product-id="${product.id}" class="add-variant-btn text-xs text-brand hover:underline block">+ Thêm size/màu</button>`
        : "";
      const editStockBtns = isPrivileged
        ? product.variants
            .map((v) => `<button data-variant-id="${v.id}" data-current="${v.stock_quantity}" data-label="${escapeHtml(product.name)} (${escapeHtml(v.size)}/${escapeHtml(v.color)})" class="edit-stock-btn text-xs text-subtle hover:underline block">Sửa tồn kho #${v.id}</button>`)
            .join("")
        : "";

      tr.innerHTML = `
        <td class="px-4 py-3 font-medium">${escapeHtml(product.name)}</td>
        <td class="px-4 py-3">${formatCurrency(product.price)}</td>
        <td class="px-4 py-3">${variantList}</td>
        <td class="px-4 py-3 text-right space-y-1">${addVariantBtn}${editStockBtns}</td>
      `;
      tbody.appendChild(tr);
    }

    tbody.querySelectorAll(".add-variant-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const size = prompt("Size mới (vd: S, M, L, 29, 30...):");
        if (!size) return;
        const color = prompt("Màu mới (vd: Trắng, Đen...):");
        if (!color) return;
        const stock = prompt("Số lượng tồn kho ban đầu:", "0");
        if (stock === null) return;
        try {
          await apiFetch(`/products/${btn.dataset.productId}/variants`, {
            method: "POST",
            body: JSON.stringify({ size, color, stock_quantity: Number(stock) || 0 }),
          });
          await loadProductList();
        } catch (err) {
          alert(err.message);
        }
      });
    });

    tbody.querySelectorAll(".edit-stock-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const newStock = prompt(`Số lượng tồn kho mới cho ${btn.dataset.label}:`, btn.dataset.current);
        if (newStock === null) return;
        try {
          await apiFetch(`/products/variants/${btn.dataset.variantId}/stock?stock_quantity=${Number(newStock) || 0}`, {
            method: "PATCH",
          });
          await loadProductList();
        } catch (err) {
          alert(err.message);
        }
      });
    });
  } catch (err) {
    loadingEl.textContent = `Lỗi tải danh sách: ${err.message}`;
  }
}

// ---- Modal: Thêm sản phẩm ----

const createProductModal = document.getElementById("create-product-modal");
const variantRowsContainer = document.getElementById("variant-rows");

function addVariantRow() {
  const row = document.createElement("div");
  row.className = "flex gap-2 variant-row";
  row.innerHTML = `
    <input type="text" placeholder="Size" class="variant-size w-1/4 border border-line rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand" />
    <input type="text" placeholder="Màu" class="variant-color flex-1 border border-line rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand" />
    <input type="number" min="0" placeholder="Tồn kho" value="0" class="variant-stock w-24 border border-line rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand" />
    <button type="button" class="remove-variant-row text-subtle hover:text-priority-high px-1">&times;</button>
  `;
  row.querySelector(".remove-variant-row").addEventListener("click", () => row.remove());
  variantRowsContainer.appendChild(row);
}

document.getElementById("add-variant-row").addEventListener("click", addVariantRow);

document.getElementById("open-create-product").addEventListener("click", () => {
  document.getElementById("create-product-form").reset();
  document.getElementById("create-product-error").classList.add("hidden");
  variantRowsContainer.innerHTML = "";
  addVariantRow(); // luôn có sẵn 1 dòng để nhập
  createProductModal.classList.remove("hidden");
});
document.getElementById("close-create-product").addEventListener("click", () => createProductModal.classList.add("hidden"));
document.getElementById("cancel-create-product").addEventListener("click", () => createProductModal.classList.add("hidden"));

document.getElementById("create-product-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("create-product-error");
  errorEl.classList.add("hidden");

  const variants = [];
  variantRowsContainer.querySelectorAll(".variant-row").forEach((row) => {
    const size = row.querySelector(".variant-size").value.trim();
    const color = row.querySelector(".variant-color").value.trim();
    const stock = Number(row.querySelector(".variant-stock").value) || 0;
    if (size && color) variants.push({ size, color, stock_quantity: stock });
  });

  const payload = {
    name: document.getElementById("new-product-name").value.trim(),
    description: document.getElementById("new-product-description").value.trim() || null,
    price: Number(document.getElementById("new-product-price").value),
    variants,
  };

  try {
    await apiFetch("/products", { method: "POST", body: JSON.stringify(payload) });
    createProductModal.classList.add("hidden");
    await loadProductList();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

// =====================================================================
// VIEW: ĐƠN HÀNG
// =====================================================================

async function loadOrderList() {
  const tbody = document.getElementById("order-table-body");
  const loadingEl = document.getElementById("order-loading-state");
  const emptyEl = document.getElementById("order-empty-state");

  tbody.innerHTML = "";
  emptyEl.classList.add("hidden");
  loadingEl.classList.remove("hidden");

  try {
    const orders = await apiFetch("/orders?limit=200");
    loadingEl.classList.add("hidden");

    if (orders.length === 0) {
      emptyEl.classList.remove("hidden");
      return;
    }

    for (const order of orders) {
      const tr = document.createElement("tr");
      tr.className = "border-b border-line last:border-0 align-top";

      const itemsSummary = order.items
        .map((it) => `${it.quantity} × ${escapeHtml(it.product_variant.size)}/${escapeHtml(it.product_variant.color)}`)
        .join(", ");

      const statusSelect = `
        <select data-order-id="${order.id}" class="order-status-select border border-line rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand">
          ${Object.entries(ORDER_STATUS_LABEL).map(([val, label]) =>
            `<option value="${val}" ${order.status === val ? "selected" : ""}>${label}</option>`).join("")}
        </select>
      `;

      tr.innerHTML = `
        <td class="px-4 py-3">#${order.id}</td>
        <td class="px-4 py-3">${escapeHtml(order.customer.name)}<br/><span class="text-xs text-subtle">${escapeHtml(order.customer.email)}</span></td>
        <td class="px-4 py-3">${itemsSummary || "<span class=\"text-subtle\">—</span>"}</td>
        <td class="px-4 py-3">${formatCurrency(order.total_amount)}</td>
        <td class="px-4 py-3">${statusSelect}</td>
      `;
      tbody.appendChild(tr);
    }

    tbody.querySelectorAll(".order-status-select").forEach((sel) => {
      sel.addEventListener("change", async () => {
        try {
          await apiFetch(`/orders/${sel.dataset.orderId}/status`, {
            method: "PATCH",
            body: JSON.stringify({ status: sel.value }),
          });
          await loadOrderList();
        } catch (err) {
          alert(err.message);
          await loadOrderList();
        }
      });
    });
  } catch (err) {
    loadingEl.textContent = `Lỗi tải danh sách: ${err.message}`;
  }
}

// ---- Modal: Tạo đơn hàng ----

const createOrderModal = document.getElementById("create-order-modal");
const orderCustomerSelect = document.getElementById("order-customer-select");
const orderItemRowsContainer = document.getElementById("order-item-rows");
let allVariantsCache = []; // [{id, label, product_name, size, color}]

async function loadOrderCustomerSelect() {
  const customers = await apiFetch("/customers?limit=200");
  orderCustomerSelect.innerHTML = '<option value="">— Chọn khách hàng —</option>';
  for (const c of customers) {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = `${c.name} (${c.email})`;
    orderCustomerSelect.appendChild(opt);
  }
}

async function loadVariantsCache() {
  const products = await apiFetch("/products?limit=200");
  allVariantsCache = [];
  for (const p of products) {
    for (const v of p.variants) {
      allVariantsCache.push({
        id: v.id,
        label: `${p.name} — ${v.size}/${v.color} (còn ${v.stock_quantity})`,
        stock: v.stock_quantity,
      });
    }
  }
}

function addOrderItemRow() {
  const row = document.createElement("div");
  row.className = "flex gap-2 order-item-row";

  const options = allVariantsCache
    .map((v) => `<option value="${v.id}">${escapeHtml(v.label)}</option>`)
    .join("");

  row.innerHTML = `
    <select class="order-item-variant flex-1 border border-line rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand">
      <option value="">— Chọn sản phẩm (size/màu) —</option>
      ${options}
    </select>
    <input type="number" min="1" value="1" class="order-item-qty w-20 border border-line rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand/40 focus:border-brand" />
    <button type="button" class="remove-order-item-row text-subtle hover:text-priority-high px-1">&times;</button>
  `;
  row.querySelector(".remove-order-item-row").addEventListener("click", () => row.remove());
  orderItemRowsContainer.appendChild(row);
}

document.getElementById("add-order-item-row").addEventListener("click", addOrderItemRow);

document.getElementById("open-create-order").addEventListener("click", async () => {
  document.getElementById("create-order-form").reset();
  document.getElementById("create-order-error").classList.add("hidden");
  orderItemRowsContainer.innerHTML = "";
  await loadOrderCustomerSelect();
  await loadVariantsCache();
  addOrderItemRow(); // luôn có sẵn 1 dòng để chọn
  createOrderModal.classList.remove("hidden");
});
document.getElementById("close-create-order").addEventListener("click", () => createOrderModal.classList.add("hidden"));
document.getElementById("cancel-create-order").addEventListener("click", () => createOrderModal.classList.add("hidden"));

document.getElementById("create-order-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("create-order-error");
  errorEl.classList.add("hidden");

  const items = [];
  orderItemRowsContainer.querySelectorAll(".order-item-row").forEach((row) => {
    const variantId = row.querySelector(".order-item-variant").value;
    const qty = Number(row.querySelector(".order-item-qty").value) || 0;
    if (variantId && qty > 0) items.push({ product_variant_id: Number(variantId), quantity: qty });
  });

  if (!orderCustomerSelect.value) {
    errorEl.textContent = "Vui lòng chọn khách hàng.";
    errorEl.classList.remove("hidden");
    return;
  }
  if (items.length === 0) {
    errorEl.textContent = "Vui lòng chọn ít nhất 1 sản phẩm.";
    errorEl.classList.remove("hidden");
    return;
  }

  const payload = {
    customer_id: Number(orderCustomerSelect.value),
    shipping_address: document.getElementById("order-shipping-address").value.trim() || null,
    items,
  };

  try {
    await apiFetch("/orders", { method: "POST", body: JSON.stringify(payload) });
    createOrderModal.classList.add("hidden");
    await loadOrderList();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

// =====================================================================
// INIT
// =====================================================================

// Tương thích ngược: link cũ dạng /ticket?id=123 (trước khi gộp thành SPA)
// -> tự chuyển sang route nội bộ #/tickets/123.
function migrateLegacyTicketLink() {
  const params = new URLSearchParams(window.location.search);
  const legacyId = params.get("id");
  if (window.location.pathname === "/ticket" && legacyId) {
    window.location.replace(`/#/tickets/${legacyId}`);
    return true;
  }
  return false;
}

if (!migrateLegacyTicketLink()) {
  renderRoute();
}
