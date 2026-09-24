from decimal import Decimal

from app.admin.services import AdminProductTypeService
from app.models import Category, Product, ProductSize, ProductType, Subcategory
from app.shop.services import CategoryService, ProductService

SEED_CATALOG = {
    "Electronics": {
        "description": "Phones, laptops, and gadgets.",
        "subcategories": {
            "Mobiles": [
                {"name": "Aurora X12 Smartphone", "price": 24999, "sale_price": 21999, "stock": 40, "desc": "6.5-inch AMOLED display, 128GB storage, 5G ready."},
                {"name": "Nimbus Lite 5G", "price": 15999, "sale_price": None, "stock": 60, "desc": "Affordable 5G phone with all-day battery life."},
            ],
            "Laptops": [
                {"name": "Vector Pro 14 Laptop", "price": 68999, "sale_price": 62999, "stock": 15, "desc": "14-inch laptop with 16GB RAM and 512GB SSD."},
                {"name": "Compact Book Air 13", "price": 54999, "sale_price": None, "stock": 20, "desc": "Ultra-light 13-inch laptop for everyday productivity."},
            ],
        },
    },
    "Fashion": {
        "description": "Clothing and accessories for everyone.",
        "subcategories": {
            "Men": [
                {"name": "Classic Fit Cotton Shirt", "price": 1299, "sale_price": 899, "stock": 100, "type": "Clothing", "desc": "Breathable 100% cotton shirt, available in multiple colors."},
                {"name": "Slim Fit Denim Jeans", "price": 1999, "sale_price": None, "stock": 80, "type": "Bottomwear", "desc": "Comfort-stretch denim jeans with a modern slim fit."},
            ],
            "Women": [
                {"name": "Floral Summer Dress", "price": 1799, "sale_price": 1399, "stock": 50, "type": "Clothing", "desc": "Lightweight floral print dress, perfect for summer."},
                {"name": "Everyday Kurti Set", "price": 1499, "sale_price": None, "stock": 70, "type": "Clothing", "desc": "Comfortable cotton kurti with matching bottoms."},
            ],
        },
    },
    "Home & Kitchen": {
        "description": "Everything for your home.",
        "subcategories": {
            "Kitchen Appliances": [
                {"name": "Turbo Mixer Grinder 750W", "price": 3499, "sale_price": 2999, "stock": 35, "desc": "750W mixer grinder with 3 stainless steel jars."},
                {"name": "Electric Kettle 1.5L", "price": 1299, "sale_price": None, "stock": 90, "desc": "Fast-boil electric kettle with auto shut-off."},
            ],
            "Furniture": [
                {"name": "Ergo Study Chair", "price": 6999, "sale_price": 5999, "stock": 12, "desc": "Ergonomic chair with lumbar support and adjustable height."},
                {"name": "Compact Bookshelf", "price": 3999, "sale_price": None, "stock": 25, "desc": "5-tier bookshelf, easy to assemble."},
            ],
        },
    },
}


def _apply_seed_sizes(product, product_type, total_stock):
    """Spread the seed stock evenly over the type's sizes."""
    product.product_type_id = product_type.id
    if not product_type.sizes:
        return
    per_size, extra = divmod(total_stock, len(product_type.sizes))
    product.size_label = product_type.size_label
    product.sizes = [
        ProductSize(name=name, stock_quantity=per_size + (1 if i < extra else 0))
        for i, name in enumerate(product_type.sizes)
    ]


def run_seed_data():
    AdminProductTypeService.create_defaults()
    types_by_name = {t.name: t for t in ProductType.all()}

    for cat_index, (cat_name, cat_data) in enumerate(SEED_CATALOG.items()):
        category = Category.first(Category.name == cat_name)
        if category is None:
            category = Category(
                name=cat_name,
                slug=CategoryService.unique_slug(cat_name),
                description=cat_data["description"],
                is_active=True,
                sort_order=cat_index,
            )
            category.put()

        for sub_index, (sub_name, products) in enumerate(cat_data["subcategories"].items()):
            subcategory = Subcategory.first(Subcategory.category_id == category.id, Subcategory.name == sub_name)
            if subcategory is None:
                subcategory = Subcategory(
                    category_id=category.id,
                    name=sub_name,
                    slug=CategoryService.unique_slug(sub_name, subcategory_of=category.id),
                    description=f"{sub_name} in {cat_name}",
                    is_active=True,
                    sort_order=sub_index,
                )
                subcategory.put()

            for prod_index, item in enumerate(products):
                sku = f"{category.slug[:3].upper()}-{subcategory.slug[:3].upper()}-{prod_index + 1:03d}"
                existing = Product.first(Product.sku == sku)
                if existing:
                    continue
                product = Product(
                    category_id=category.id,
                    subcategory_id=subcategory.id,
                    name=item["name"],
                    slug=ProductService.unique_slug(item["name"]),
                    sku=sku,
                    short_description=item["desc"],
                    description=item["desc"] + " Ships within 2-4 business days.",
                    price=Decimal(str(item["price"])),
                    sale_price=Decimal(str(item["sale_price"])) if item["sale_price"] else None,
                    stock_quantity=item["stock"],
                    low_stock_threshold=5,
                    is_active=True,
                )
                if item.get("type") in types_by_name:
                    _apply_seed_sizes(product, types_by_name[item["type"]], item["stock"])
                product.put()
