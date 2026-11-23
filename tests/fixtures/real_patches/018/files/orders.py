from inventory import reserve

def place(stock, item, qty):
    reserve(stock, item, qty)
    return 'accepted'
