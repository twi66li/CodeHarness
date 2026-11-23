def discount_cents(subtotal, coupon):
    if coupon is None:
        return 0
    if subtotal > coupon.threshold:
        return coupon.amount
    return 0
