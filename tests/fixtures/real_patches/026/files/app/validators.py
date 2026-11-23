def validate_voucher(entries):
    if not entries:
        raise ValueError("empty voucher")
    debit = sum(e.amount for e in entries if e.side == "debit")
    credit = sum(e.amount for e in entries if e.side == "credit")
    if debit != credit:
        raise ValueError("unbalanced voucher")
