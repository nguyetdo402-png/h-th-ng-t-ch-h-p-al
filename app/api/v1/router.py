"""Router tổng hợp: gộp tất cả router con lại thành /api/v1."""

from fastapi import APIRouter

from app.api.v1 import (
    ai_drafts,
    auth,
    customer_auth,
    customers,
    faqs,
    interactions,
    orders,
    products,
    public_chat,
    stats,
    tickets,
    users,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(customers.router)
api_router.include_router(products.router)
api_router.include_router(orders.router)
api_router.include_router(tickets.router)
api_router.include_router(interactions.router)
api_router.include_router(ai_drafts.router)
api_router.include_router(faqs.router)
api_router.include_router(stats.router)
# Public: không yêu cầu đăng nhập bắt buộc (khách hàng tự đăng ký/đăng nhập,
# kênh chat công khai).
api_router.include_router(customer_auth.router)
api_router.include_router(public_chat.router)
