from decimal import Decimal
from money import cents

def total(items, shipping=Decimal('0')):
    return cents(sum(items, Decimal('0')))
