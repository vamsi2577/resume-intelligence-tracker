"""
Custom application exceptions.

Raised by the service layer — never import FastAPI here.
Mapped to HTTP status codes in src/api/middleware.py error handler.
"""


class NotFoundError(Exception):
    """Resource not found."""
    def __init__(self, resource: str, id: str):
        self.resource = resource
        self.id = id
        super().__init__(f"{resource} '{id}' not found")


class DuplicateError(Exception):
    """A resource that must be unique already exists.

    `resource` names what collided (e.g. "application", "group") so the error
    message is meaningful per caller. Defaults to "application" for backward
    compatibility with existing call sites.
    """
    def __init__(self, existing_id: str, resource: str = "application"):
        self.existing_id = existing_id
        self.resource = resource
        super().__init__(f"Duplicate {resource} exists: {existing_id}")


class ValidationError(Exception):
    """Service-level validation failure (distinct from Pydantic)."""
    def __init__(self, message: str):
        super().__init__(message)
