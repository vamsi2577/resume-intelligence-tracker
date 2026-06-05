"""Model registry.

Importing this package registers every ORM table on `Base.metadata`. This
matters for cross-module ForeignKey resolution: `job_applications`,
`base_resumes`, and `resume_generations` all declare `owner_id` FKs to
`users.id`, so the `User` model must be imported wherever those models are
used (otherwise SQLAlchemy raises NoReferencedTableError when it resolves the
foreign key). `src.main` imports this package at startup so the running app
and the test suite both get a complete metadata.
"""
from src.models.user import User
from src.models.application import ApplicationStatusHistory, JobApplication
from src.models.base_resume import BaseResume
from src.models.resume_generation import ResumeGeneration
from src.models.iam import (
    Group,
    GroupMember,
    GroupRole,
    IamAuditLog,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from src.models.login_token import LoginToken
from src.models.api_token import ApiToken

__all__ = [
    "User",
    "JobApplication",
    "ApplicationStatusHistory",
    "BaseResume",
    "ResumeGeneration",
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "Group",
    "GroupMember",
    "GroupRole",
    "IamAuditLog",
    "LoginToken",
    "ApiToken",
]
