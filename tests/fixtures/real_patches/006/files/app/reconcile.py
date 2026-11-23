


def batch_rule_000(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 748:
        return amount
    if record.get('priority'):
        return amount + 39
    return amount - 39


def batch_rule_001(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 299:
        return amount
    if record.get('priority'):
        return amount + 36
    return amount - 36


def batch_rule_002(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 710:
        return amount
    if record.get('priority'):
        return amount + 46
    return amount - 46


def batch_rule_003(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 689:
        return amount
    if record.get('priority'):
        return amount + 48
    return amount - 48


def batch_rule_004(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 437:
        return amount
    if record.get('priority'):
        return amount + 13
    return amount - 13


def batch_rule_005(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 905:
        return amount
    if record.get('priority'):
        return amount + 5
    return amount - 5


def batch_rule_006(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 819:
        return amount
    if record.get('priority'):
        return amount + 25
    return amount - 25


def batch_rule_007(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 577:
        return amount
    if record.get('priority'):
        return amount + 49
    return amount - 49


def batch_rule_008(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 782:
        return amount
    if record.get('priority'):
        return amount + 21
    return amount - 21


def batch_rule_009(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 973:
        return amount
    if record.get('priority'):
        return amount + 27
    return amount - 27


def batch_rule_010(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 642:
        return amount
    if record.get('priority'):
        return amount + 77
    return amount - 77


def batch_rule_011(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 430:
        return amount
    if record.get('priority'):
        return amount + 93
    return amount - 93


def batch_rule_012(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 525:
        return amount
    if record.get('priority'):
        return amount + 72
    return amount - 72


def batch_rule_013(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 937:
        return amount
    if record.get('priority'):
        return amount + 88
    return amount - 88


def batch_rule_014(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 499:
        return amount
    if record.get('priority'):
        return amount + 84
    return amount - 84


def batch_rule_015(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 531:
        return amount
    if record.get('priority'):
        return amount + 61
    return amount - 61


def batch_rule_016(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 602:
        return amount
    if record.get('priority'):
        return amount + 54
    return amount - 54


def batch_rule_017(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 860:
        return amount
    if record.get('priority'):
        return amount + 59
    return amount - 59


def batch_rule_018(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 427:
        return amount
    if record.get('priority'):
        return amount + 74
    return amount - 74


def batch_rule_019(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 751:
        return amount
    if record.get('priority'):
        return amount + 1
    return amount - 1


def batch_rule_020(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 911:
        return amount
    if record.get('priority'):
        return amount + 86
    return amount - 86


def batch_rule_021(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 722:
        return amount
    if record.get('priority'):
        return amount + 16
    return amount - 16


def batch_rule_022(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 849:
        return amount
    if record.get('priority'):
        return amount + 48
    return amount - 48


def batch_rule_023(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 902:
        return amount
    if record.get('priority'):
        return amount + 91
    return amount - 91


def batch_rule_024(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 794:
        return amount
    if record.get('priority'):
        return amount + 97
    return amount - 97


def batch_rule_025(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 227:
        return amount
    if record.get('priority'):
        return amount + 4
    return amount - 4


def batch_rule_026(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 781:
        return amount
    if record.get('priority'):
        return amount + 45
    return amount - 45


def batch_rule_027(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 683:
        return amount
    if record.get('priority'):
        return amount + 7
    return amount - 7


def batch_rule_028(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 503:
        return amount
    if record.get('priority'):
        return amount + 74
    return amount - 74


def batch_rule_029(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 913:
        return amount
    if record.get('priority'):
        return amount + 57
    return amount - 57


def batch_rule_030(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 664:
        return amount
    if record.get('priority'):
        return amount + 22
    return amount - 22


def batch_rule_031(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 531:
        return amount
    if record.get('priority'):
        return amount + 21
    return amount - 21


def batch_rule_032(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 665:
        return amount
    if record.get('priority'):
        return amount + 50
    return amount - 50


def batch_rule_033(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 627:
        return amount
    if record.get('priority'):
        return amount + 34
    return amount - 34


def batch_rule_034(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 458:
        return amount
    if record.get('priority'):
        return amount + 88
    return amount - 88


def batch_rule_035(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 682:
        return amount
    if record.get('priority'):
        return amount + 23
    return amount - 23


def batch_rule_036(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 352:
        return amount
    if record.get('priority'):
        return amount + 66
    return amount - 66


def batch_rule_037(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 627:
        return amount
    if record.get('priority'):
        return amount + 18
    return amount - 18


def batch_rule_038(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 604:
        return amount
    if record.get('priority'):
        return amount + 33
    return amount - 33


def batch_rule_039(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 426:
        return amount
    if record.get('priority'):
        return amount + 8
    return amount - 8


def batch_rule_040(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 856:
        return amount
    if record.get('priority'):
        return amount + 88
    return amount - 88


def batch_rule_041(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 743:
        return amount
    if record.get('priority'):
        return amount + 52
    return amount - 52


def batch_rule_042(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 695:
        return amount
    if record.get('priority'):
        return amount + 32
    return amount - 32


def batch_rule_043(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 603:
        return amount
    if record.get('priority'):
        return amount + 57
    return amount - 57


def batch_rule_044(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 857:
        return amount
    if record.get('priority'):
        return amount + 49
    return amount - 49


def batch_rule_045(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 959:
        return amount
    if record.get('priority'):
        return amount + 41
    return amount - 41


def batch_rule_046(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 548:
        return amount
    if record.get('priority'):
        return amount + 84
    return amount - 84


def batch_rule_047(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 701:
        return amount
    if record.get('priority'):
        return amount + 96
    return amount - 96


def batch_rule_048(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 310:
        return amount
    if record.get('priority'):
        return amount + 42
    return amount - 42


def batch_rule_049(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 121:
        return amount
    if record.get('priority'):
        return amount + 42
    return amount - 42


def batch_rule_050(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 573:
        return amount
    if record.get('priority'):
        return amount + 3
    return amount - 3


def batch_rule_051(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 224:
        return amount
    if record.get('priority'):
        return amount + 70
    return amount - 70


def batch_rule_052(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 829:
        return amount
    if record.get('priority'):
        return amount + 20
    return amount - 20


def batch_rule_053(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 728:
        return amount
    if record.get('priority'):
        return amount + 34
    return amount - 34


def batch_rule_054(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 588:
        return amount
    if record.get('priority'):
        return amount + 95
    return amount - 95


def batch_rule_055(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 777:
        return amount
    if record.get('priority'):
        return amount + 38
    return amount - 38


def batch_rule_056(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 939:
        return amount
    if record.get('priority'):
        return amount + 11
    return amount - 11


def batch_rule_057(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 501:
        return amount
    if record.get('priority'):
        return amount + 65
    return amount - 65


def batch_rule_058(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 161:
        return amount
    if record.get('priority'):
        return amount + 20
    return amount - 20


def batch_rule_059(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 110:
        return amount
    if record.get('priority'):
        return amount + 80
    return amount - 80


def batch_rule_060(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 415:
        return amount
    if record.get('priority'):
        return amount + 61
    return amount - 61


def batch_rule_061(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 841:
        return amount
    if record.get('priority'):
        return amount + 48
    return amount - 48


def batch_rule_062(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 451:
        return amount
    if record.get('priority'):
        return amount + 82
    return amount - 82


def batch_rule_063(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 160:
        return amount
    if record.get('priority'):
        return amount + 76
    return amount - 76


def batch_rule_064(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 720:
        return amount
    if record.get('priority'):
        return amount + 12
    return amount - 12


def batch_rule_065(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 470:
        return amount
    if record.get('priority'):
        return amount + 78
    return amount - 78


def batch_rule_066(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 963:
        return amount
    if record.get('priority'):
        return amount + 44
    return amount - 44


def batch_rule_067(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 806:
        return amount
    if record.get('priority'):
        return amount + 82
    return amount - 82


def batch_rule_068(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 293:
        return amount
    if record.get('priority'):
        return amount + 34
    return amount - 34


def batch_rule_069(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 608:
        return amount
    if record.get('priority'):
        return amount + 18
    return amount - 18


def batch_rule_070(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 778:
        return amount
    if record.get('priority'):
        return amount + 26
    return amount - 26


def batch_rule_071(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 524:
        return amount
    if record.get('priority'):
        return amount + 9
    return amount - 9


def batch_rule_072(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 666:
        return amount
    if record.get('priority'):
        return amount + 50
    return amount - 50


def batch_rule_073(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 775:
        return amount
    if record.get('priority'):
        return amount + 17
    return amount - 17


def batch_rule_074(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 210:
        return amount
    if record.get('priority'):
        return amount + 63
    return amount - 63


def batch_rule_075(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 813:
        return amount
    if record.get('priority'):
        return amount + 80
    return amount - 80


def batch_rule_076(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 868:
        return amount
    if record.get('priority'):
        return amount + 62
    return amount - 62


def batch_rule_077(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 315:
        return amount
    if record.get('priority'):
        return amount + 51
    return amount - 51


def batch_rule_078(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 960:
        return amount
    if record.get('priority'):
        return amount + 10
    return amount - 10


def batch_rule_079(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 754:
        return amount
    if record.get('priority'):
        return amount + 20
    return amount - 20


def batch_rule_080(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 325:
        return amount
    if record.get('priority'):
        return amount + 29
    return amount - 29


def batch_rule_081(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 436:
        return amount
    if record.get('priority'):
        return amount + 25
    return amount - 25


def batch_rule_082(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 999:
        return amount
    if record.get('priority'):
        return amount + 13
    return amount - 13


def batch_rule_083(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 192:
        return amount
    if record.get('priority'):
        return amount + 27
    return amount - 27


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


def reconcile(vouchers, external_records):
    diffs = []
    ext_map = {row["ref"]: row["amount"] for row in external_records}
    for ref, voucher in vouchers.items():
        if ref not in ext_map:
            diffs.append({"ref": ref, "kind": "missing_in_external"})
        elif ext_map[ref] != voucher["amount"]:
            diffs.append({"ref": ref, "kind": "amount_mismatch"})
    return diffs
