from app.audit import log_decision
from app.metrics import count_decision
from app.policies import evaluate
from app.ratelimit import within_limit
from app.roles import expand_roles
from app.tokens import is_valid

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
