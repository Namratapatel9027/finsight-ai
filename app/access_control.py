"""Role policy and pure authorization checks for the RAG application."""

ROLE_DEPARTMENTS = {
    "employee": frozenset({"general"}),
    "finance": frozenset({"finance", "general"}),
    "marketing": frozenset({"marketing", "general"}),
    "hr": frozenset({"hr", "general"}),
    "engineering": frozenset({"engineering", "general"}),
    "executive": frozenset({
        "engineering",
        "finance",
        "general",
        "hr",
        "marketing",
    }),
}

ROLE_ALIASES = {
    "c-level": "executive",
    "c_level": "executive",
    "c level": "executive",
}

INTENT_DEPARTMENTS = {
    "finance_information": "finance",
    "marketing_information": "marketing",
    "engineering_information": "engineering",
}


def normalize_role(role):
    """Return a supported canonical role or reject unknown role names."""

    if not isinstance(role, str):
        raise ValueError("Role must be a string.")

    normalized = role.strip().lower()
    normalized = ROLE_ALIASES.get(normalized, normalized)

    if normalized not in ROLE_DEPARTMENTS:
        allowed_roles = ", ".join(sorted(ROLE_DEPARTMENTS))
        raise ValueError(
            f"Unknown role '{role}'. Supported roles: {allowed_roles}."
        )

    return normalized


def get_allowed_departments(role):
    """Return the set of document departments available to a role."""

    return ROLE_DEPARTMENTS[normalize_role(role)]


def required_department_for_intent(intent):
    """Return the protected department associated with a routed intent."""

    return INTENT_DEPARTMENTS.get(intent)


def can_access_department(role, department):
    """Check whether a role may access one department."""

    return department in get_allowed_departments(role)


def can_access_hr_data(role):
    """HR records and aggregates are limited to HR and Executive roles."""

    return can_access_department(role, "hr")