def calculate_tax(subtotal, discount, rate_bps):
    taxable = subtotal
    return (taxable * rate_bps + 5000) // 10000
