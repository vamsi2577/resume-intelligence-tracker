"""
IAM permission catalog and built-in role definitions (Phase 1b).

This module is the single source of truth the application uses for
authorization: `require_permission` checks against these keys and `/auth/me`
returns the caller's effective set. Migration 009 seeds the database from a
SNAPSHOT of these values (migrations stay self-contained — adding a new
permission later requires its own migration).

Authorization (these permissions) is orthogonal to tenancy (owner_id):
  - `.own`  permissions gate self-service actions on the caller's own rows,
            checked ALONGSIDE the owner_id filter.
  - `.any`  permissions power the privileged /api/v1/admin/* routes that
            deliberately cross the owner boundary (audit-logged).
"""
from __future__ import annotations


class Permissions:
    # ── Self-service (held by every user) ─────────────────
    APPLICATIONS_READ_OWN = "applications.read.own"
    APPLICATIONS_WRITE_OWN = "applications.write.own"
    BASE_RESUME_MANAGE_OWN = "base_resume.manage.own"
    GENERATION_CREATE = "generation.create"
    GENERATION_HISTORY_OWN = "generation.history.own"
    BILLING_MANAGE_OWN = "billing.manage.own"  # Phase 4 self-serve portal

    # ── Support (read any tenant, no writes) ──────────────
    APPLICATIONS_READ_ANY = "applications.read.any"
    GENERATION_HISTORY_ANY = "generation.history.any"

    # ── Admin ─────────────────────────────────────────────
    ADMIN_ACCESS = "admin.access"  # may reach /admin/* at all
    USERS_MANAGE = "users.manage"  # list / deactivate / assign roles
    APPLICATIONS_WRITE_ANY = "applications.write.any"
    GROUPS_MANAGE = "groups.manage"

    # ── Superadmin ────────────────────────────────────────
    ROLES_MANAGE = "roles.manage"  # roles, permissions, role maps


# (key, category, human description) — the seedable catalog.
PERMISSION_CATALOG: list[tuple[str, str, str]] = [
    (Permissions.APPLICATIONS_READ_OWN, "applications", "Read own applications"),
    (Permissions.APPLICATIONS_WRITE_OWN, "applications", "Create/update own applications"),
    (Permissions.BASE_RESUME_MANAGE_OWN, "base_resume", "Manage own base résumé"),
    (Permissions.GENERATION_CREATE, "generation", "Generate a résumé from a JD"),
    (Permissions.GENERATION_HISTORY_OWN, "generation", "View own generation history"),
    (Permissions.BILLING_MANAGE_OWN, "billing", "Manage own subscription/billing"),
    (Permissions.APPLICATIONS_READ_ANY, "admin", "Read any tenant's applications"),
    (Permissions.GENERATION_HISTORY_ANY, "admin", "View any tenant's generation history"),
    (Permissions.ADMIN_ACCESS, "admin", "Access the admin area"),
    (Permissions.USERS_MANAGE, "admin", "Manage users, roles, and group membership"),
    (Permissions.APPLICATIONS_WRITE_ANY, "admin", "Edit any tenant's applications"),
    (Permissions.GROUPS_MANAGE, "admin", "Create and manage groups"),
    (Permissions.ROLES_MANAGE, "admin", "Manage roles and permission assignments"),
]

# Built-in role names.
ROLE_USER = "user"
ROLE_SUPPORT = "support"
ROLE_ADMIN = "admin"
ROLE_SUPERADMIN = "superadmin"

SYSTEM_ROLES: list[tuple[str, str]] = [
    (ROLE_USER, "Standard self-service user"),
    (ROLE_SUPPORT, "Read-only access across tenants for support"),
    (ROLE_ADMIN, "Manage users, groups, and any tenant's data"),
    (ROLE_SUPERADMIN, "Full access including role/permission management"),
]

# Role → permission keys. Higher roles include the lower role's permissions.
_USER_PERMS = [
    Permissions.APPLICATIONS_READ_OWN,
    Permissions.APPLICATIONS_WRITE_OWN,
    Permissions.BASE_RESUME_MANAGE_OWN,
    Permissions.GENERATION_CREATE,
    Permissions.GENERATION_HISTORY_OWN,
    Permissions.BILLING_MANAGE_OWN,
]
_SUPPORT_PERMS = [
    Permissions.ADMIN_ACCESS,
    Permissions.APPLICATIONS_READ_ANY,
    Permissions.GENERATION_HISTORY_ANY,
]
_ADMIN_PERMS = _SUPPORT_PERMS + [
    Permissions.USERS_MANAGE,
    Permissions.APPLICATIONS_WRITE_ANY,
    Permissions.GROUPS_MANAGE,
]
_SUPERADMIN_PERMS = _ADMIN_PERMS + [Permissions.ROLES_MANAGE]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    ROLE_USER: _USER_PERMS,
    ROLE_SUPPORT: _SUPPORT_PERMS,
    ROLE_ADMIN: _ADMIN_PERMS,
    ROLE_SUPERADMIN: _SUPERADMIN_PERMS,
}

# Roles the seeded default owner gets. Roles are ADDITIVE, and an admin human
# is also a normal user — so the default owner holds `user` (self-service over
# their own data) AND `superadmin` (full admin). Without `user`, the
# `.own`-gated endpoints added in PR2 would deny the owner their own rows.
DEFAULT_OWNER_ROLES = [ROLE_USER, ROLE_SUPERADMIN]

# Role auto-assigned to every new user at sign-up (Phase 2).
DEFAULT_SIGNUP_ROLE = ROLE_USER
