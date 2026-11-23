def reconcile(vouchers, external_records):
    diffs = []
    ext_map = {row["ref"]: row["amount"] for row in external_records}
    for ref, voucher in vouchers.items():
        if ref not in ext_map:
            diffs.append({"ref": ref, "kind": "missing_in_external"})
        elif ext_map[ref] != voucher["amount"]:
            diffs.append({"ref": ref, "kind": "amount_mismatch"})
    return diffs
