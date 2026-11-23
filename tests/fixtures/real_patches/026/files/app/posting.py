from app.balances import apply_entries
from app.validators import validate_voucher

class Ledger:
    def __init__(self):
        self.balances = {}
        self.vouchers = {}
        self.by_key = {}
        self.external_totals = {}

    def post(self, ref, entries, idempotency_key=None):
        validate_voucher(entries)
        apply_entries(self.balances, entries)
        amount = sum(e.amount for e in entries if e.side == "debit")
        voucher = {"ref": ref, "amount": amount, "entries": list(entries)}
        self.vouchers[ref] = voucher
        if idempotency_key is not None:
            self.by_key[idempotency_key] = voucher
        return voucher
