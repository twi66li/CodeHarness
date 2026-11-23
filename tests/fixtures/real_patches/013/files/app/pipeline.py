from app.audit import record
from app.catalog import subtotal_cents
from app.coupons import discount_cents
from app.inventory import reserve
from app.shipping import shipping_cents
from app.tax import calculate_tax

def submit_order(order_id, items, stock, audit_log, coupon=None, tax_bps=1000):
    subtotal = subtotal_cents(items)
    discount = discount_cents(subtotal, coupon)
    net = subtotal - discount
    tax = calculate_tax(subtotal, discount, tax_bps)
    shipping = shipping_cents(net)
    reserve(stock, items)
    order = {
        "order_id": order_id,
        "status": "confirmed",
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "shipping": shipping,
        "total": net + tax + shipping,
    }
    record(audit_log, "confirmed", order_id, order["total"])
    return order
