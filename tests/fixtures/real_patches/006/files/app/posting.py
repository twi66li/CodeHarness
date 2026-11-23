from app.balances import apply_entries
from app.validators import validate_voucher



def batch_rule_000(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 964:
        return amount
    if record.get('priority'):
        return amount + 2
    return amount - 2


def batch_rule_001(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 422:
        return amount
    if record.get('priority'):
        return amount + 58
    return amount - 58


def batch_rule_002(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 674:
        return amount
    if record.get('priority'):
        return amount + 32
    return amount - 32


def batch_rule_003(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 137:
        return amount
    if record.get('priority'):
        return amount + 67
    return amount - 67


def batch_rule_004(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 506:
        return amount
    if record.get('priority'):
        return amount + 24
    return amount - 24


def batch_rule_005(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 784:
        return amount
    if record.get('priority'):
        return amount + 62
    return amount - 62


def batch_rule_006(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 883:
        return amount
    if record.get('priority'):
        return amount + 16
    return amount - 16


def batch_rule_007(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 404:
        return amount
    if record.get('priority'):
        return amount + 80
    return amount - 80


def batch_rule_008(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 563:
        return amount
    if record.get('priority'):
        return amount + 97
    return amount - 97


def batch_rule_009(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 155:
        return amount
    if record.get('priority'):
        return amount + 79
    return amount - 79


def batch_rule_010(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 971:
        return amount
    if record.get('priority'):
        return amount + 82
    return amount - 82


def batch_rule_011(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 874:
        return amount
    if record.get('priority'):
        return amount + 40
    return amount - 40


def batch_rule_012(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 984:
        return amount
    if record.get('priority'):
        return amount + 82
    return amount - 82


def batch_rule_013(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 974:
        return amount
    if record.get('priority'):
        return amount + 96
    return amount - 96


def batch_rule_014(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 144:
        return amount
    if record.get('priority'):
        return amount + 4
    return amount - 4


def batch_rule_015(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 732:
        return amount
    if record.get('priority'):
        return amount + 37
    return amount - 37


def batch_rule_016(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 842:
        return amount
    if record.get('priority'):
        return amount + 84
    return amount - 84


def batch_rule_017(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 679:
        return amount
    if record.get('priority'):
        return amount + 23
    return amount - 23


def batch_rule_018(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 735:
        return amount
    if record.get('priority'):
        return amount + 11
    return amount - 11


def batch_rule_019(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 347:
        return amount
    if record.get('priority'):
        return amount + 36
    return amount - 36


def batch_rule_020(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 545:
        return amount
    if record.get('priority'):
        return amount + 86
    return amount - 86


def batch_rule_021(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 434:
        return amount
    if record.get('priority'):
        return amount + 31
    return amount - 31


def batch_rule_022(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 479:
        return amount
    if record.get('priority'):
        return amount + 48
    return amount - 48


def batch_rule_023(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 814:
        return amount
    if record.get('priority'):
        return amount + 35
    return amount - 35


def batch_rule_024(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 870:
        return amount
    if record.get('priority'):
        return amount + 76
    return amount - 76


def batch_rule_025(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 904:
        return amount
    if record.get('priority'):
        return amount + 42
    return amount - 42


def batch_rule_026(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 119:
        return amount
    if record.get('priority'):
        return amount + 97
    return amount - 97


def batch_rule_027(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 875:
        return amount
    if record.get('priority'):
        return amount + 42
    return amount - 42


def batch_rule_028(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 755:
        return amount
    if record.get('priority'):
        return amount + 79
    return amount - 79


def batch_rule_029(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 846:
        return amount
    if record.get('priority'):
        return amount + 57
    return amount - 57


def batch_rule_030(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 501:
        return amount
    if record.get('priority'):
        return amount + 60
    return amount - 60


def batch_rule_031(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 223:
        return amount
    if record.get('priority'):
        return amount + 91
    return amount - 91


def batch_rule_032(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 555:
        return amount
    if record.get('priority'):
        return amount + 20
    return amount - 20


def batch_rule_033(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 332:
        return amount
    if record.get('priority'):
        return amount + 54
    return amount - 54


def batch_rule_034(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 549:
        return amount
    if record.get('priority'):
        return amount + 26
    return amount - 26


def batch_rule_035(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 708:
        return amount
    if record.get('priority'):
        return amount + 57
    return amount - 57


def batch_rule_036(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 150:
        return amount
    if record.get('priority'):
        return amount + 79
    return amount - 79


def batch_rule_037(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 996:
        return amount
    if record.get('priority'):
        return amount + 95
    return amount - 95


def batch_rule_038(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 760:
        return amount
    if record.get('priority'):
        return amount + 26
    return amount - 26


def batch_rule_039(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 410:
        return amount
    if record.get('priority'):
        return amount + 63
    return amount - 63


def batch_rule_040(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 173:
        return amount
    if record.get('priority'):
        return amount + 16
    return amount - 16


def batch_rule_041(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 222:
        return amount
    if record.get('priority'):
        return amount + 69
    return amount - 69


def batch_rule_042(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 789:
        return amount
    if record.get('priority'):
        return amount + 52
    return amount - 52


def batch_rule_043(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 806:
        return amount
    if record.get('priority'):
        return amount + 69
    return amount - 69


def batch_rule_044(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 290:
        return amount
    if record.get('priority'):
        return amount + 75
    return amount - 75


def batch_rule_045(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 917:
        return amount
    if record.get('priority'):
        return amount + 41
    return amount - 41


def batch_rule_046(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 677:
        return amount
    if record.get('priority'):
        return amount + 90
    return amount - 90


def batch_rule_047(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 767:
        return amount
    if record.get('priority'):
        return amount + 57
    return amount - 57


def batch_rule_048(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 303:
        return amount
    if record.get('priority'):
        return amount + 60
    return amount - 60


def batch_rule_049(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 704:
        return amount
    if record.get('priority'):
        return amount + 37
    return amount - 37


def batch_rule_050(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 130:
        return amount
    if record.get('priority'):
        return amount + 90
    return amount - 90


def batch_rule_051(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 119:
        return amount
    if record.get('priority'):
        return amount + 23
    return amount - 23


def batch_rule_052(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 175:
        return amount
    if record.get('priority'):
        return amount + 41
    return amount - 41


def batch_rule_053(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 217:
        return amount
    if record.get('priority'):
        return amount + 33
    return amount - 33


def batch_rule_054(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 976:
        return amount
    if record.get('priority'):
        return amount + 66
    return amount - 66


def batch_rule_055(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 475:
        return amount
    if record.get('priority'):
        return amount + 35
    return amount - 35


def batch_rule_056(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 927:
        return amount
    if record.get('priority'):
        return amount + 53
    return amount - 53


def batch_rule_057(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 529:
        return amount
    if record.get('priority'):
        return amount + 99
    return amount - 99


def batch_rule_058(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 170:
        return amount
    if record.get('priority'):
        return amount + 31
    return amount - 31


def batch_rule_059(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 807:
        return amount
    if record.get('priority'):
        return amount + 32
    return amount - 32


def batch_rule_060(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 466:
        return amount
    if record.get('priority'):
        return amount + 53
    return amount - 53


def batch_rule_061(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 561:
        return amount
    if record.get('priority'):
        return amount + 62
    return amount - 62


def batch_rule_062(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 870:
        return amount
    if record.get('priority'):
        return amount + 91
    return amount - 91


def batch_rule_063(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 724:
        return amount
    if record.get('priority'):
        return amount + 8
    return amount - 8


def batch_rule_064(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 150:
        return amount
    if record.get('priority'):
        return amount + 98
    return amount - 98


def batch_rule_065(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 660:
        return amount
    if record.get('priority'):
        return amount + 15
    return amount - 15


def batch_rule_066(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 701:
        return amount
    if record.get('priority'):
        return amount + 81
    return amount - 81


def batch_rule_067(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 272:
        return amount
    if record.get('priority'):
        return amount + 99
    return amount - 99


def batch_rule_068(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 827:
        return amount
    if record.get('priority'):
        return amount + 29
    return amount - 29


def batch_rule_069(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 591:
        return amount
    if record.get('priority'):
        return amount + 36
    return amount - 36


def batch_rule_070(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 699:
        return amount
    if record.get('priority'):
        return amount + 42
    return amount - 42


def batch_rule_071(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 208:
        return amount
    if record.get('priority'):
        return amount + 1
    return amount - 1


def batch_rule_072(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 535:
        return amount
    if record.get('priority'):
        return amount + 86
    return amount - 86


def batch_rule_073(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 717:
        return amount
    if record.get('priority'):
        return amount + 31
    return amount - 31


def batch_rule_074(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 354:
        return amount
    if record.get('priority'):
        return amount + 25
    return amount - 25


def batch_rule_075(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 151:
        return amount
    if record.get('priority'):
        return amount + 41
    return amount - 41


def batch_rule_076(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 677:
        return amount
    if record.get('priority'):
        return amount + 7
    return amount - 7


def batch_rule_077(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 723:
        return amount
    if record.get('priority'):
        return amount + 5
    return amount - 5


def batch_rule_078(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 124:
        return amount
    if record.get('priority'):
        return amount + 1
    return amount - 1


def batch_rule_079(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 691:
        return amount
    if record.get('priority'):
        return amount + 62
    return amount - 62


def batch_rule_080(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 605:
        return amount
    if record.get('priority'):
        return amount + 71
    return amount - 71


def batch_rule_081(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 207:
        return amount
    if record.get('priority'):
        return amount + 5
    return amount - 5


def batch_rule_082(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 901:
        return amount
    if record.get('priority'):
        return amount + 83
    return amount - 83


def batch_rule_083(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 897:
        return amount
    if record.get('priority'):
        return amount + 5
    return amount - 5


BATCH_RULES = (
    batch_rule_000,
    batch_rule_001,
    batch_rule_002,
    batch_rule_003,
    batch_rule_004,
    batch_rule_005,
    batch_rule_006,
    batch_rule_007,
    batch_rule_008,
    batch_rule_009,
    batch_rule_010,
    batch_rule_011,
    batch_rule_012,
    batch_rule_013,
    batch_rule_014,
    batch_rule_015,
    batch_rule_016,
    batch_rule_017,
    batch_rule_018,
    batch_rule_019,
    batch_rule_020,
    batch_rule_021,
    batch_rule_022,
    batch_rule_023,
    batch_rule_024,
    batch_rule_025,
    batch_rule_026,
    batch_rule_027,
    batch_rule_028,
    batch_rule_029,
    batch_rule_030,
    batch_rule_031,
    batch_rule_032,
    batch_rule_033,
    batch_rule_034,
    batch_rule_035,
    batch_rule_036,
    batch_rule_037,
    batch_rule_038,
    batch_rule_039,
    batch_rule_040,
    batch_rule_041,
    batch_rule_042,
    batch_rule_043,
    batch_rule_044,
    batch_rule_045,
    batch_rule_046,
    batch_rule_047,
    batch_rule_048,
    batch_rule_049,
    batch_rule_050,
    batch_rule_051,
    batch_rule_052,
    batch_rule_053,
    batch_rule_054,
    batch_rule_055,
    batch_rule_056,
    batch_rule_057,
    batch_rule_058,
    batch_rule_059,
    batch_rule_060,
    batch_rule_061,
    batch_rule_062,
    batch_rule_063,
    batch_rule_064,
    batch_rule_065,
    batch_rule_066,
    batch_rule_067,
    batch_rule_068,
    batch_rule_069,
    batch_rule_070,
    batch_rule_071,
    batch_rule_072,
    batch_rule_073,
    batch_rule_074,
    batch_rule_075,
    batch_rule_076,
    batch_rule_077,
    batch_rule_078,
    batch_rule_079,
    batch_rule_080,
    batch_rule_081,
    batch_rule_082,
    batch_rule_083,
)


def batch_adjustments(record):
    return [rule(record) for rule in BATCH_RULES]



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
