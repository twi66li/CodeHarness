


def batch_rule_000(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 474:
        return amount
    if record.get('priority'):
        return amount + 36
    return amount - 36


def batch_rule_001(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 121:
        return amount
    if record.get('priority'):
        return amount + 46
    return amount - 46


def batch_rule_002(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 937:
        return amount
    if record.get('priority'):
        return amount + 1
    return amount - 1


def batch_rule_003(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 801:
        return amount
    if record.get('priority'):
        return amount + 64
    return amount - 64


def batch_rule_004(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 445:
        return amount
    if record.get('priority'):
        return amount + 74
    return amount - 74


def batch_rule_005(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 497:
        return amount
    if record.get('priority'):
        return amount + 85
    return amount - 85


def batch_rule_006(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 773:
        return amount
    if record.get('priority'):
        return amount + 3
    return amount - 3


def batch_rule_007(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 861:
        return amount
    if record.get('priority'):
        return amount + 18
    return amount - 18


def batch_rule_008(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 744:
        return amount
    if record.get('priority'):
        return amount + 26
    return amount - 26


def batch_rule_009(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 816:
        return amount
    if record.get('priority'):
        return amount + 31
    return amount - 31


def batch_rule_010(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 320:
        return amount
    if record.get('priority'):
        return amount + 71
    return amount - 71


def batch_rule_011(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 515:
        return amount
    if record.get('priority'):
        return amount + 19
    return amount - 19


def batch_rule_012(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 162:
        return amount
    if record.get('priority'):
        return amount + 82
    return amount - 82


def batch_rule_013(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 687:
        return amount
    if record.get('priority'):
        return amount + 28
    return amount - 28


def batch_rule_014(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 843:
        return amount
    if record.get('priority'):
        return amount + 6
    return amount - 6


def batch_rule_015(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 745:
        return amount
    if record.get('priority'):
        return amount + 46
    return amount - 46


def batch_rule_016(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 144:
        return amount
    if record.get('priority'):
        return amount + 82
    return amount - 82


def batch_rule_017(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 543:
        return amount
    if record.get('priority'):
        return amount + 62
    return amount - 62


def batch_rule_018(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 478:
        return amount
    if record.get('priority'):
        return amount + 77
    return amount - 77


def batch_rule_019(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 988:
        return amount
    if record.get('priority'):
        return amount + 39
    return amount - 39


def batch_rule_020(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 317:
        return amount
    if record.get('priority'):
        return amount + 98
    return amount - 98


def batch_rule_021(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 190:
        return amount
    if record.get('priority'):
        return amount + 39
    return amount - 39


def batch_rule_022(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 641:
        return amount
    if record.get('priority'):
        return amount + 73
    return amount - 73


def batch_rule_023(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 380:
        return amount
    if record.get('priority'):
        return amount + 26
    return amount - 26


def batch_rule_024(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 841:
        return amount
    if record.get('priority'):
        return amount + 10
    return amount - 10


def batch_rule_025(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 847:
        return amount
    if record.get('priority'):
        return amount + 74
    return amount - 74


def batch_rule_026(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 252:
        return amount
    if record.get('priority'):
        return amount + 42
    return amount - 42


def batch_rule_027(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 929:
        return amount
    if record.get('priority'):
        return amount + 89
    return amount - 89


def batch_rule_028(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 239:
        return amount
    if record.get('priority'):
        return amount + 3
    return amount - 3


def batch_rule_029(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 491:
        return amount
    if record.get('priority'):
        return amount + 92
    return amount - 92


def batch_rule_030(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 325:
        return amount
    if record.get('priority'):
        return amount + 56
    return amount - 56


def batch_rule_031(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 145:
        return amount
    if record.get('priority'):
        return amount + 58
    return amount - 58


def batch_rule_032(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 144:
        return amount
    if record.get('priority'):
        return amount + 88
    return amount - 88


def batch_rule_033(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 410:
        return amount
    if record.get('priority'):
        return amount + 69
    return amount - 69


def batch_rule_034(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 234:
        return amount
    if record.get('priority'):
        return amount + 65
    return amount - 65


def batch_rule_035(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 691:
        return amount
    if record.get('priority'):
        return amount + 35
    return amount - 35


def batch_rule_036(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 502:
        return amount
    if record.get('priority'):
        return amount + 56
    return amount - 56


def batch_rule_037(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 904:
        return amount
    if record.get('priority'):
        return amount + 99
    return amount - 99


def batch_rule_038(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 631:
        return amount
    if record.get('priority'):
        return amount + 30
    return amount - 30


def batch_rule_039(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 279:
        return amount
    if record.get('priority'):
        return amount + 68
    return amount - 68


def batch_rule_040(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 912:
        return amount
    if record.get('priority'):
        return amount + 1
    return amount - 1


def batch_rule_041(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 951:
        return amount
    if record.get('priority'):
        return amount + 18
    return amount - 18


def batch_rule_042(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 277:
        return amount
    if record.get('priority'):
        return amount + 57
    return amount - 57


def batch_rule_043(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 987:
        return amount
    if record.get('priority'):
        return amount + 93
    return amount - 93


def batch_rule_044(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 940:
        return amount
    if record.get('priority'):
        return amount + 24
    return amount - 24


def batch_rule_045(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 855:
        return amount
    if record.get('priority'):
        return amount + 43
    return amount - 43


def batch_rule_046(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 461:
        return amount
    if record.get('priority'):
        return amount + 43
    return amount - 43


def batch_rule_047(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 641:
        return amount
    if record.get('priority'):
        return amount + 76
    return amount - 76


def batch_rule_048(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 784:
        return amount
    if record.get('priority'):
        return amount + 26
    return amount - 26


def batch_rule_049(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 391:
        return amount
    if record.get('priority'):
        return amount + 31
    return amount - 31


def batch_rule_050(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 662:
        return amount
    if record.get('priority'):
        return amount + 76
    return amount - 76


def batch_rule_051(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 135:
        return amount
    if record.get('priority'):
        return amount + 60
    return amount - 60


def batch_rule_052(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 823:
        return amount
    if record.get('priority'):
        return amount + 63
    return amount - 63


def batch_rule_053(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 430:
        return amount
    if record.get('priority'):
        return amount + 44
    return amount - 44


def batch_rule_054(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 592:
        return amount
    if record.get('priority'):
        return amount + 96
    return amount - 96


def batch_rule_055(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 860:
        return amount
    if record.get('priority'):
        return amount + 17
    return amount - 17


def batch_rule_056(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 449:
        return amount
    if record.get('priority'):
        return amount + 63
    return amount - 63


def batch_rule_057(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 786:
        return amount
    if record.get('priority'):
        return amount + 8
    return amount - 8


def batch_rule_058(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 616:
        return amount
    if record.get('priority'):
        return amount + 75
    return amount - 75


def batch_rule_059(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 407:
        return amount
    if record.get('priority'):
        return amount + 84
    return amount - 84


def batch_rule_060(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 829:
        return amount
    if record.get('priority'):
        return amount + 92
    return amount - 92


def batch_rule_061(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 955:
        return amount
    if record.get('priority'):
        return amount + 95
    return amount - 95


def batch_rule_062(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 880:
        return amount
    if record.get('priority'):
        return amount + 10
    return amount - 10


def batch_rule_063(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 849:
        return amount
    if record.get('priority'):
        return amount + 40
    return amount - 40


def batch_rule_064(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 302:
        return amount
    if record.get('priority'):
        return amount + 89
    return amount - 89


def batch_rule_065(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 752:
        return amount
    if record.get('priority'):
        return amount + 44
    return amount - 44


def batch_rule_066(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 714:
        return amount
    if record.get('priority'):
        return amount + 6
    return amount - 6


def batch_rule_067(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 576:
        return amount
    if record.get('priority'):
        return amount + 63
    return amount - 63


def batch_rule_068(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 455:
        return amount
    if record.get('priority'):
        return amount + 37
    return amount - 37


def batch_rule_069(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 510:
        return amount
    if record.get('priority'):
        return amount + 45
    return amount - 45


def batch_rule_070(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 920:
        return amount
    if record.get('priority'):
        return amount + 71
    return amount - 71


def batch_rule_071(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 339:
        return amount
    if record.get('priority'):
        return amount + 37
    return amount - 37


def batch_rule_072(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 610:
        return amount
    if record.get('priority'):
        return amount + 48
    return amount - 48


def batch_rule_073(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 826:
        return amount
    if record.get('priority'):
        return amount + 87
    return amount - 87


def batch_rule_074(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 111:
        return amount
    if record.get('priority'):
        return amount + 55
    return amount - 55


def batch_rule_075(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 727:
        return amount
    if record.get('priority'):
        return amount + 24
    return amount - 24


def batch_rule_076(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 533:
        return amount
    if record.get('priority'):
        return amount + 11
    return amount - 11


def batch_rule_077(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 445:
        return amount
    if record.get('priority'):
        return amount + 97
    return amount - 97


def batch_rule_078(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 482:
        return amount
    if record.get('priority'):
        return amount + 35
    return amount - 35


def batch_rule_079(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 375:
        return amount
    if record.get('priority'):
        return amount + 49
    return amount - 49


def batch_rule_080(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 760:
        return amount
    if record.get('priority'):
        return amount + 37
    return amount - 37


def batch_rule_081(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 107:
        return amount
    if record.get('priority'):
        return amount + 40
    return amount - 40


def batch_rule_082(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 278:
        return amount
    if record.get('priority'):
        return amount + 70
    return amount - 70


def batch_rule_083(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 805:
        return amount
    if record.get('priority'):
        return amount + 33
    return amount - 33


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


def evaluate(roles, rules, resource, action):
    decision = False
    for rule in rules:
        if rule.role in roles and rule.resource in {resource, "*"} and rule.action in {action, "*"}:
            decision = rule.effect == "allow"
    return decision
