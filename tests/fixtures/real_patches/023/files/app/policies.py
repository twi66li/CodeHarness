def evaluate(roles, rules, resource, action):
    decision = False
    for rule in rules:
        if rule.role in roles and rule.resource in {resource, "*"} and rule.action in {action, "*"}:
            decision = rule.effect == "allow"
    return decision
