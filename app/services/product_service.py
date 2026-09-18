"""Business logic CRUD cho Product / ProductVariant (sản phẩm & tồn kho)."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.models.product import Product, ProductVariant
from app.schemas.product import ProductCreate, ProductUpdate, ProductVariantCreate


def get_product_or_404(db: Session, product_id: int) -> Product:
    product = (
        db.query(Product)
        .options(selectinload(Product.variants))
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sản phẩm id={product_id}",
        )
    return product


def get_products(
    db: Session, skip: int = 0, limit: int = 100, search: str | None = None
) -> list[Product]:
    query = db.query(Product).options(selectinload(Product.variants))
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    return query.order_by(Product.id.desc()).offset(skip).limit(limit).all()


def get_variant_or_404(db: Session, variant_id: int) -> ProductVariant:
    variant = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy biến thể sản phẩm (variant) id={variant_id}",
        )
    return variant


def create_product(db: Session, payload: ProductCreate) -> Product:
    product = Product(
        name=payload.name,
        description=payload.description,
        price=payload.price,
        image_url=payload.image_url,
    )
    db.add(product)
    db.flush()  # cần product.id trước khi tạo variant

    for variant_payload in payload.variants:
        db.add(
            ProductVariant(
                product_id=product.id,
                size=variant_payload.size,
                color=variant_payload.color,
                stock_quantity=variant_payload.stock_quantity,
            )
        )

    db.commit()
    db.refresh(product)
    return product


def update_product(db: Session, product_id: int, payload: ProductUpdate) -> Product:
    product = get_product_or_404(db, product_id)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


def add_variant(db: Session, product_id: int, payload: ProductVariantCreate) -> ProductVariant:
    """Thêm 1 tổ hợp size/màu mới cho sản phẩm đã có (vd: nhập thêm màu mới)."""
    product = get_product_or_404(db, product_id)

    existing = next(
        (v for v in product.variants if v.size == payload.size and v.color == payload.color),
        None,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sản phẩm đã có variant size={payload.size} màu={payload.color}",
        )

    variant = ProductVariant(
        product_id=product_id,
        size=payload.size,
        color=payload.color,
        stock_quantity=payload.stock_quantity,
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)
    return variant


def update_variant_stock(db: Session, variant_id: int, stock_quantity: int) -> ProductVariant:
    """Sửa trực tiếp số lượng tồn kho — dùng khi nhập thêm hàng hoặc kiểm kho."""
    variant = get_variant_or_404(db, variant_id)
    variant.stock_quantity = stock_quantity
    db.commit()
    db.refresh(variant)
    return variant
