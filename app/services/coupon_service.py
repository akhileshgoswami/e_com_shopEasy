from decimal import Decimal

from app.models import Coupon, DiscountType


class CouponError(Exception):
    pass


class CouponService:
    @staticmethod
    def get_valid_coupon(code):
        if not code:
            return None
        coupon = Coupon.query.filter(Coupon.code == code.strip().upper()).first()
        if coupon is None:
            raise CouponError("Invalid coupon code.")
        if not coupon.is_valid_now():
            raise CouponError("This coupon is no longer valid.")
        return coupon

    @staticmethod
    def calculate_discount(coupon, subtotal):
        subtotal = Decimal(subtotal)
        if coupon is None:
            return Decimal("0.00")
        if subtotal < coupon.minimum_order_value:
            raise CouponError(
                f"Minimum order value of {coupon.minimum_order_value} required for this coupon."
            )
        if coupon.discount_type == DiscountType.PERCENT:
            discount = subtotal * (coupon.discount_value / Decimal("100"))
        else:
            discount = coupon.discount_value

        if coupon.maximum_discount is not None:
            discount = min(discount, coupon.maximum_discount)

        return min(discount, subtotal)

    @staticmethod
    def redeem(coupon):
        coupon.used_count += 1
