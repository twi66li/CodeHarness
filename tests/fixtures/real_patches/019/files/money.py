from decimal import Decimal, ROUND_DOWN

def cents(value):
    return value.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
