def expand_roles(direct_roles, hierarchy):
    result = set(direct_roles)
    for role in list(direct_roles):
        result.update(hierarchy.get(role, ()))
    return result
