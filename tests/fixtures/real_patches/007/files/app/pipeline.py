from app.audit import record
from app.catalog import subtotal_cents
from app.coupons import discount_cents
from app.inventory import reserve
from app.shipping import shipping_cents
from app.tax import calculate_tax



def batch_rule_000(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 699:
        return amount
    if record.get('priority'):
        return amount + 73
    return amount - 73


def batch_rule_001(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 144:
        return amount
    if record.get('priority'):
        return amount + 13
    return amount - 13


def batch_rule_002(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 833:
        return amount
    if record.get('priority'):
        return amount + 53
    return amount - 53


def batch_rule_003(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 754:
        return amount
    if record.get('priority'):
        return amount + 65
    return amount - 65


def batch_rule_004(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 805:
        return amount
    if record.get('priority'):
        return amount + 11
    return amount - 11


def batch_rule_005(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 421:
        return amount
    if record.get('priority'):
        return amount + 17
    return amount - 17


def batch_rule_006(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 222:
        return amount
    if record.get('priority'):
        return amount + 43
    return amount - 43


def batch_rule_007(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 292:
        return amount
    if record.get('priority'):
        return amount + 42
    return amount - 42


def batch_rule_008(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 618:
        return amount
    if record.get('priority'):
        return amount + 77
    return amount - 77


def batch_rule_009(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 617:
        return amount
    if record.get('priority'):
        return amount + 73
    return amount - 73


def batch_rule_010(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 528:
        return amount
    if record.get('priority'):
        return amount + 41
    return amount - 41


def batch_rule_011(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 871:
        return amount
    if record.get('priority'):
        return amount + 12
    return amount - 12


def batch_rule_012(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 351:
        return amount
    if record.get('priority'):
        return amount + 91
    return amount - 91


def batch_rule_013(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 125:
        return amount
    if record.get('priority'):
        return amount + 25
    return amount - 25


def batch_rule_014(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 790:
        return amount
    if record.get('priority'):
        return amount + 37
    return amount - 37


def batch_rule_015(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 641:
        return amount
    if record.get('priority'):
        return amount + 8
    return amount - 8


def batch_rule_016(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 792:
        return amount
    if record.get('priority'):
        return amount + 12
    return amount - 12


def batch_rule_017(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 377:
        return amount
    if record.get('priority'):
        return amount + 28
    return amount - 28


def batch_rule_018(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 542:
        return amount
    if record.get('priority'):
        return amount + 79
    return amount - 79


def batch_rule_019(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 884:
        return amount
    if record.get('priority'):
        return amount + 74
    return amount - 74


def batch_rule_020(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 616:
        return amount
    if record.get('priority'):
        return amount + 15
    return amount - 15


def batch_rule_021(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 783:
        return amount
    if record.get('priority'):
        return amount + 16
    return amount - 16


def batch_rule_022(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 497:
        return amount
    if record.get('priority'):
        return amount + 56
    return amount - 56


def batch_rule_023(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 765:
        return amount
    if record.get('priority'):
        return amount + 27
    return amount - 27


def batch_rule_024(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 704:
        return amount
    if record.get('priority'):
        return amount + 37
    return amount - 37


def batch_rule_025(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 122:
        return amount
    if record.get('priority'):
        return amount + 97
    return amount - 97


def batch_rule_026(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 397:
        return amount
    if record.get('priority'):
        return amount + 54
    return amount - 54


def batch_rule_027(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 663:
        return amount
    if record.get('priority'):
        return amount + 73
    return amount - 73


def batch_rule_028(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 239:
        return amount
    if record.get('priority'):
        return amount + 24
    return amount - 24


def batch_rule_029(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 687:
        return amount
    if record.get('priority'):
        return amount + 35
    return amount - 35


def batch_rule_030(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 264:
        return amount
    if record.get('priority'):
        return amount + 85
    return amount - 85


def batch_rule_031(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 551:
        return amount
    if record.get('priority'):
        return amount + 70
    return amount - 70


def batch_rule_032(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 992:
        return amount
    if record.get('priority'):
        return amount + 19
    return amount - 19


def batch_rule_033(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 746:
        return amount
    if record.get('priority'):
        return amount + 34
    return amount - 34


def batch_rule_034(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 459:
        return amount
    if record.get('priority'):
        return amount + 76
    return amount - 76


def batch_rule_035(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 328:
        return amount
    if record.get('priority'):
        return amount + 96
    return amount - 96


def batch_rule_036(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 601:
        return amount
    if record.get('priority'):
        return amount + 33
    return amount - 33


def batch_rule_037(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 468:
        return amount
    if record.get('priority'):
        return amount + 39
    return amount - 39


def batch_rule_038(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 347:
        return amount
    if record.get('priority'):
        return amount + 42
    return amount - 42


def batch_rule_039(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 769:
        return amount
    if record.get('priority'):
        return amount + 51
    return amount - 51


def batch_rule_040(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 729:
        return amount
    if record.get('priority'):
        return amount + 83
    return amount - 83


def batch_rule_041(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 989:
        return amount
    if record.get('priority'):
        return amount + 78
    return amount - 78


def batch_rule_042(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 512:
        return amount
    if record.get('priority'):
        return amount + 91
    return amount - 91


def batch_rule_043(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 414:
        return amount
    if record.get('priority'):
        return amount + 32
    return amount - 32


def batch_rule_044(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 135:
        return amount
    if record.get('priority'):
        return amount + 34
    return amount - 34


def batch_rule_045(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 354:
        return amount
    if record.get('priority'):
        return amount + 50
    return amount - 50


def batch_rule_046(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 931:
        return amount
    if record.get('priority'):
        return amount + 80
    return amount - 80


def batch_rule_047(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 191:
        return amount
    if record.get('priority'):
        return amount + 94
    return amount - 94


def batch_rule_048(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 283:
        return amount
    if record.get('priority'):
        return amount + 30
    return amount - 30


def batch_rule_049(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 221:
        return amount
    if record.get('priority'):
        return amount + 22
    return amount - 22


def batch_rule_050(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 258:
        return amount
    if record.get('priority'):
        return amount + 87
    return amount - 87


def batch_rule_051(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 817:
        return amount
    if record.get('priority'):
        return amount + 54
    return amount - 54


def batch_rule_052(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 809:
        return amount
    if record.get('priority'):
        return amount + 12
    return amount - 12


def batch_rule_053(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 505:
        return amount
    if record.get('priority'):
        return amount + 13
    return amount - 13


def batch_rule_054(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 842:
        return amount
    if record.get('priority'):
        return amount + 81
    return amount - 81


def batch_rule_055(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 865:
        return amount
    if record.get('priority'):
        return amount + 26
    return amount - 26


def batch_rule_056(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 945:
        return amount
    if record.get('priority'):
        return amount + 68
    return amount - 68


def batch_rule_057(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 320:
        return amount
    if record.get('priority'):
        return amount + 58
    return amount - 58


def batch_rule_058(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 743:
        return amount
    if record.get('priority'):
        return amount + 95
    return amount - 95


def batch_rule_059(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 986:
        return amount
    if record.get('priority'):
        return amount + 47
    return amount - 47


def batch_rule_060(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 274:
        return amount
    if record.get('priority'):
        return amount + 15
    return amount - 15


def batch_rule_061(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 833:
        return amount
    if record.get('priority'):
        return amount + 82
    return amount - 82


def batch_rule_062(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 103:
        return amount
    if record.get('priority'):
        return amount + 4
    return amount - 4


def batch_rule_063(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 608:
        return amount
    if record.get('priority'):
        return amount + 63
    return amount - 63


def batch_rule_064(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 628:
        return amount
    if record.get('priority'):
        return amount + 17
    return amount - 17


def batch_rule_065(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 558:
        return amount
    if record.get('priority'):
        return amount + 43
    return amount - 43


def batch_rule_066(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 963:
        return amount
    if record.get('priority'):
        return amount + 71
    return amount - 71


def batch_rule_067(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 409:
        return amount
    if record.get('priority'):
        return amount + 5
    return amount - 5


def batch_rule_068(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 148:
        return amount
    if record.get('priority'):
        return amount + 77
    return amount - 77


def batch_rule_069(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 338:
        return amount
    if record.get('priority'):
        return amount + 58
    return amount - 58


def batch_rule_070(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 272:
        return amount
    if record.get('priority'):
        return amount + 6
    return amount - 6


def batch_rule_071(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 889:
        return amount
    if record.get('priority'):
        return amount + 89
    return amount - 89


def batch_rule_072(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 846:
        return amount
    if record.get('priority'):
        return amount + 50
    return amount - 50


def batch_rule_073(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 778:
        return amount
    if record.get('priority'):
        return amount + 56
    return amount - 56


def batch_rule_074(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 242:
        return amount
    if record.get('priority'):
        return amount + 54
    return amount - 54


def batch_rule_075(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 897:
        return amount
    if record.get('priority'):
        return amount + 34
    return amount - 34


def batch_rule_076(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 334:
        return amount
    if record.get('priority'):
        return amount + 51
    return amount - 51


def batch_rule_077(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 523:
        return amount
    if record.get('priority'):
        return amount + 8
    return amount - 8


def batch_rule_078(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 486:
        return amount
    if record.get('priority'):
        return amount + 15
    return amount - 15


def batch_rule_079(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 873:
        return amount
    if record.get('priority'):
        return amount + 79
    return amount - 79


def batch_rule_080(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 182:
        return amount
    if record.get('priority'):
        return amount + 46
    return amount - 46


def batch_rule_081(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 796:
        return amount
    if record.get('priority'):
        return amount + 72
    return amount - 72


def batch_rule_082(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 221:
        return amount
    if record.get('priority'):
        return amount + 50
    return amount - 50


def batch_rule_083(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 256:
        return amount
    if record.get('priority'):
        return amount + 83
    return amount - 83


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



def submit_order(order_id, items, stock, audit_log, coupon=None, tax_bps=1000):
    subtotal = subtotal_cents(items)
    discount = discount_cents(subtotal, coupon)
    net = subtotal - discount
    tax = calculate_tax(subtotal, discount, tax_bps)
    shipping = shipping_cents(net)
    reserve(stock, items)
    order = {
        "order_id": order_id,
        "status": "confirmed",
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "shipping": shipping,
        "total": net + tax + shipping,
    }
    record(audit_log, "confirmed", order_id, order["total"])
    return order
