"""
Sanity checks for the IAM permission catalog (src/core/permissions.py).

These guard against typos / drift in the role→permission map without needing a
DB. Effective-permission resolution and require_permission are tested in PR2/PR4.
"""
from __future__ import annotations

from src.core import permissions as perms


def _catalog_keys() -> set[str]:
    return {key for key, _cat, _desc in perms.PERMISSION_CATALOG}


def test_catalog_has_no_duplicate_keys():
    keys = [key for key, _cat, _desc in perms.PERMISSION_CATALOG]
    assert len(keys) == len(set(keys))


def test_role_map_keys_all_exist_in_catalog():
    catalog = _catalog_keys()
    for role, keys in perms.ROLE_PERMISSIONS.items():
        unknown = set(keys) - catalog
        assert not unknown, f"{role} references unknown permissions: {unknown}"


def test_role_permission_lists_have_no_duplicates():
    for role, keys in perms.ROLE_PERMISSIONS.items():
        assert len(keys) == len(set(keys)), f"{role} has duplicate permissions"


def test_role_hierarchy_is_additive():
    rp = perms.ROLE_PERMISSIONS
    support = set(rp[perms.ROLE_SUPPORT])
    admin = set(rp[perms.ROLE_ADMIN])
    superadmin = set(rp[perms.ROLE_SUPERADMIN])
    # admin builds on support; superadmin builds on admin.
    assert support <= admin
    assert admin <= superadmin
    assert perms.Permissions.ROLES_MANAGE in superadmin
    assert perms.Permissions.ROLES_MANAGE not in admin


def test_user_role_is_self_service_only():
    user = set(perms.ROLE_PERMISSIONS[perms.ROLE_USER])
    # the plain user holds only `.own` / self-service permissions — no `.any`.
    assert all(not k.endswith(".any") for k in user)
    assert perms.Permissions.APPLICATIONS_READ_OWN in user


def test_seeded_roles_are_known():
    role_names = {name for name, _desc in perms.SYSTEM_ROLES}
    assert set(perms.ROLE_PERMISSIONS) == role_names
    for r in perms.DEFAULT_OWNER_ROLES:
        assert r in role_names
    assert perms.DEFAULT_SIGNUP_ROLE in role_names


def test_default_owner_has_self_service_and_admin():
    # The owner must be able to use normal (.own) endpoints AND admin ones.
    owner_perms = set()
    for role in perms.DEFAULT_OWNER_ROLES:
        owner_perms |= set(perms.ROLE_PERMISSIONS[role])
    assert perms.Permissions.APPLICATIONS_READ_OWN in owner_perms
    assert perms.Permissions.ROLES_MANAGE in owner_perms
