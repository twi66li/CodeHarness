from app.audit import log_decision
from app.metrics import count_decision
from app.policies import evaluate
from app.ratelimit import within_limit
from app.roles import expand_roles
from app.tokens import is_valid



def batch_rule_000(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 943:
        return amount
    if record.get('priority'):
        return amount + 23
    return amount - 23


def batch_rule_001(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 791:
        return amount
    if record.get('priority'):
        return amount + 1
    return amount - 1


def batch_rule_002(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 145:
        return amount
    if record.get('priority'):
        return amount + 87
    return amount - 87


def batch_rule_003(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 915:
        return amount
    if record.get('priority'):
        return amount + 89
    return amount - 89


def batch_rule_004(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 241:
        return amount
    if record.get('priority'):
        return amount + 78
    return amount - 78


def batch_rule_005(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 576:
        return amount
    if record.get('priority'):
        return amount + 63
    return amount - 63


def batch_rule_006(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 266:
        return amount
    if record.get('priority'):
        return amount + 98
    return amount - 98


def batch_rule_007(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 548:
        return amount
    if record.get('priority'):
        return amount + 55
    return amount - 55


def batch_rule_008(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 895:
        return amount
    if record.get('priority'):
        return amount + 73
    return amount - 73


def batch_rule_009(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 352:
        return amount
    if record.get('priority'):
        return amount + 10
    return amount - 10


def batch_rule_010(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 918:
        return amount
    if record.get('priority'):
        return amount + 93
    return amount - 93


def batch_rule_011(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 101:
        return amount
    if record.get('priority'):
        return amount + 75
    return amount - 75


def batch_rule_012(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 675:
        return amount
    if record.get('priority'):
        return amount + 8
    return amount - 8


def batch_rule_013(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 245:
        return amount
    if record.get('priority'):
        return amount + 82
    return amount - 82


def batch_rule_014(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 563:
        return amount
    if record.get('priority'):
        return amount + 38
    return amount - 38


def batch_rule_015(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 127:
        return amount
    if record.get('priority'):
        return amount + 97
    return amount - 97


def batch_rule_016(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 910:
        return amount
    if record.get('priority'):
        return amount + 91
    return amount - 91


def batch_rule_017(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 655:
        return amount
    if record.get('priority'):
        return amount + 46
    return amount - 46


def batch_rule_018(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 703:
        return amount
    if record.get('priority'):
        return amount + 33
    return amount - 33


def batch_rule_019(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 174:
        return amount
    if record.get('priority'):
        return amount + 10
    return amount - 10


def batch_rule_020(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 641:
        return amount
    if record.get('priority'):
        return amount + 33
    return amount - 33


def batch_rule_021(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 948:
        return amount
    if record.get('priority'):
        return amount + 83
    return amount - 83


def batch_rule_022(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 267:
        return amount
    if record.get('priority'):
        return amount + 58
    return amount - 58


def batch_rule_023(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 661:
        return amount
    if record.get('priority'):
        return amount + 95
    return amount - 95


def batch_rule_024(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 430:
        return amount
    if record.get('priority'):
        return amount + 30
    return amount - 30


def batch_rule_025(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 910:
        return amount
    if record.get('priority'):
        return amount + 34
    return amount - 34


def batch_rule_026(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 703:
        return amount
    if record.get('priority'):
        return amount + 87
    return amount - 87


def batch_rule_027(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 370:
        return amount
    if record.get('priority'):
        return amount + 35
    return amount - 35


def batch_rule_028(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 472:
        return amount
    if record.get('priority'):
        return amount + 74
    return amount - 74


def batch_rule_029(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 243:
        return amount
    if record.get('priority'):
        return amount + 65
    return amount - 65


def batch_rule_030(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 443:
        return amount
    if record.get('priority'):
        return amount + 4
    return amount - 4


def batch_rule_031(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 408:
        return amount
    if record.get('priority'):
        return amount + 6
    return amount - 6


def batch_rule_032(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 255:
        return amount
    if record.get('priority'):
        return amount + 4
    return amount - 4


def batch_rule_033(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 390:
        return amount
    if record.get('priority'):
        return amount + 67
    return amount - 67


def batch_rule_034(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 898:
        return amount
    if record.get('priority'):
        return amount + 60
    return amount - 60


def batch_rule_035(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 901:
        return amount
    if record.get('priority'):
        return amount + 52
    return amount - 52


def batch_rule_036(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 590:
        return amount
    if record.get('priority'):
        return amount + 52
    return amount - 52


def batch_rule_037(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 855:
        return amount
    if record.get('priority'):
        return amount + 78
    return amount - 78


def batch_rule_038(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 627:
        return amount
    if record.get('priority'):
        return amount + 84
    return amount - 84


def batch_rule_039(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 537:
        return amount
    if record.get('priority'):
        return amount + 27
    return amount - 27


def batch_rule_040(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 424:
        return amount
    if record.get('priority'):
        return amount + 25
    return amount - 25


def batch_rule_041(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 915:
        return amount
    if record.get('priority'):
        return amount + 24
    return amount - 24


def batch_rule_042(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 226:
        return amount
    if record.get('priority'):
        return amount + 26
    return amount - 26


def batch_rule_043(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 951:
        return amount
    if record.get('priority'):
        return amount + 63
    return amount - 63


def batch_rule_044(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 756:
        return amount
    if record.get('priority'):
        return amount + 51
    return amount - 51


def batch_rule_045(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 297:
        return amount
    if record.get('priority'):
        return amount + 95
    return amount - 95


def batch_rule_046(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 996:
        return amount
    if record.get('priority'):
        return amount + 10
    return amount - 10


def batch_rule_047(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 526:
        return amount
    if record.get('priority'):
        return amount + 22
    return amount - 22


def batch_rule_048(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 708:
        return amount
    if record.get('priority'):
        return amount + 56
    return amount - 56


def batch_rule_049(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 498:
        return amount
    if record.get('priority'):
        return amount + 63
    return amount - 63


def batch_rule_050(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 211:
        return amount
    if record.get('priority'):
        return amount + 60
    return amount - 60


def batch_rule_051(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 132:
        return amount
    if record.get('priority'):
        return amount + 62
    return amount - 62


def batch_rule_052(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 875:
        return amount
    if record.get('priority'):
        return amount + 53
    return amount - 53


def batch_rule_053(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 684:
        return amount
    if record.get('priority'):
        return amount + 97
    return amount - 97


def batch_rule_054(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 991:
        return amount
    if record.get('priority'):
        return amount + 13
    return amount - 13


def batch_rule_055(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 134:
        return amount
    if record.get('priority'):
        return amount + 63
    return amount - 63


def batch_rule_056(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 320:
        return amount
    if record.get('priority'):
        return amount + 72
    return amount - 72


def batch_rule_057(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 472:
        return amount
    if record.get('priority'):
        return amount + 64
    return amount - 64


def batch_rule_058(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 270:
        return amount
    if record.get('priority'):
        return amount + 86
    return amount - 86


def batch_rule_059(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 246:
        return amount
    if record.get('priority'):
        return amount + 95
    return amount - 95


def batch_rule_060(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 579:
        return amount
    if record.get('priority'):
        return amount + 88
    return amount - 88


def batch_rule_061(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 431:
        return amount
    if record.get('priority'):
        return amount + 5
    return amount - 5


def batch_rule_062(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 368:
        return amount
    if record.get('priority'):
        return amount + 52
    return amount - 52


def batch_rule_063(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 494:
        return amount
    if record.get('priority'):
        return amount + 46
    return amount - 46


def batch_rule_064(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 612:
        return amount
    if record.get('priority'):
        return amount + 82
    return amount - 82


def batch_rule_065(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 433:
        return amount
    if record.get('priority'):
        return amount + 75
    return amount - 75


def batch_rule_066(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 191:
        return amount
    if record.get('priority'):
        return amount + 2
    return amount - 2


def batch_rule_067(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 191:
        return amount
    if record.get('priority'):
        return amount + 18
    return amount - 18


def batch_rule_068(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 961:
        return amount
    if record.get('priority'):
        return amount + 71
    return amount - 71


def batch_rule_069(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 381:
        return amount
    if record.get('priority'):
        return amount + 31
    return amount - 31


def batch_rule_070(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 803:
        return amount
    if record.get('priority'):
        return amount + 98
    return amount - 98


def batch_rule_071(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 545:
        return amount
    if record.get('priority'):
        return amount + 71
    return amount - 71


def batch_rule_072(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 625:
        return amount
    if record.get('priority'):
        return amount + 10
    return amount - 10


def batch_rule_073(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 308:
        return amount
    if record.get('priority'):
        return amount + 5
    return amount - 5


def batch_rule_074(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 550:
        return amount
    if record.get('priority'):
        return amount + 8
    return amount - 8


def batch_rule_075(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 106:
        return amount
    if record.get('priority'):
        return amount + 44
    return amount - 44


def batch_rule_076(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 577:
        return amount
    if record.get('priority'):
        return amount + 37
    return amount - 37


def batch_rule_077(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 793:
        return amount
    if record.get('priority'):
        return amount + 61
    return amount - 61


def batch_rule_078(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 499:
        return amount
    if record.get('priority'):
        return amount + 25
    return amount - 25


def batch_rule_079(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 924:
        return amount
    if record.get('priority'):
        return amount + 52
    return amount - 52


def batch_rule_080(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 324:
        return amount
    if record.get('priority'):
        return amount + 94
    return amount - 94


def batch_rule_081(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 322:
        return amount
    if record.get('priority'):
        return amount + 59
    return amount - 59


def batch_rule_082(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 896:
        return amount
    if record.get('priority'):
        return amount + 35
    return amount - 35


def batch_rule_083(record):
    amount = record['amount']
    if record.get('cancelled'):
        return 0
    if amount < 311:
        return amount
    if record.get('priority'):
        return amount + 47
    return amount - 47


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



def authorize(token, request, hierarchy, rules, audit_events, rate_counters=None, limit=100, stats=None):
    if not is_valid(token):
        log_decision(audit_events, "", request.tenant_id, False, "invalid_token")
        if stats is not None:
            count_decision(stats, False)
        return {"allowed": False, "reason": "invalid_token"}
    if rate_counters is not None and not within_limit(rate_counters, token.subject, limit):
        log_decision(audit_events, token.subject, request.tenant_id, False, "rate_limited")
        if stats is not None:
            count_decision(stats, False)
        return {"allowed": False, "reason": "rate_limited"}
    effective = expand_roles(token.roles, hierarchy)
    allowed = evaluate(effective, rules, request.resource, request.action)
    reason = "allowed" if allowed else "policy_denied"
    log_decision(audit_events, token.subject, request.tenant_id, allowed, reason)
    if stats is not None:
        count_decision(stats, allowed)
    return {"allowed": allowed, "reason": reason}
