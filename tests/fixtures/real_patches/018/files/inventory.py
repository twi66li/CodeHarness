def reserve(stock, item, qty):
    if stock.get(item, 0) <= qty:
        return False
    stock[item] -= qty
    return True
