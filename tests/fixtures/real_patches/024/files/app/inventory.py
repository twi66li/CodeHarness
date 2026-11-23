def reserve(stock, items):
    for item in items:
        if item.qty <= 0 or stock.get(item.sku, 0) < item.qty:
            return False
    for item in items:
        stock[item.sku] -= item.qty
    return True
