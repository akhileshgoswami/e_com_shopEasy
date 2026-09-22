from decimal import Decimal

from app.extensions import db
from app.models import Category, Product, Subcategory
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
                {"name": "Classic Fit Cotton Shirt", "price": 1299, "sale_price": 899, "stock": 100, "desc": "Breathable 100% cotton shirt, available in multiple colors."},
                {"name": "Slim Fit Denim Jeans", "price": 1999, "sale_price": None, "stock": 80, "desc": "Comfort-stretch denim jeans with a modern slim fit."},
            ],
            "Women": [
                {"name": "Floral Summer Dress", "price": 1799, "sale_price": 1399, "stock": 50, "desc": "Lightweight floral print dress, perfect for summer."},
                {"name": "Everyday Kurti Set", "price": 1499, "sale_price": None, "stock": 70, "desc": "Comfortable cotton kurti with matching bottoms."},
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


def run_seed_data():
    for cat_index, (cat_name, cat_data) in enumerate(SEED_CATALOG.items()):
        category = Category.query.filter_by(name=cat_name).first()
        if category is None:
            category = Category(
                name=cat_name,
                slug=CategoryService.unique_slug(cat_name),
                description=cat_data["description"],
                is_active=True,
                sort_order=cat_index,
            )
            db.session.add(category)
            db.session.flush()

        for sub_index, (sub_name, products) in enumerate(cat_data["subcategories"].items()):
            subcategory = Subcategory.query.filter_by(category_id=category.id, name=sub_name).first()
            if subcategory is None:
                subcategory = Subcategory(
                    category_id=category.id,
                    name=sub_name,
                    slug=CategoryService.unique_slug(sub_name, subcategory_of=category.id),
                    description=f"{sub_name} in {cat_name}",
                    is_active=True,
                    sort_order=sub_index,
                )
                db.session.add(subcategory)
                db.session.flush()

            for prod_index, item in enumerate(products):
                sku = f"{category.slug[:3].upper()}-{subcategory.slug[:3].upper()}-{prod_index + 1:03d}"
                existing = Product.query.filter_by(sku=sku).first()
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
                db.session.add(product)

    db.session.commit()
