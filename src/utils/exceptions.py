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
    """Hard duplicate — same company_name + job_id."""
    def __init__(self, existing_id: str):
        self.existing_id = existing_id
        super().__init__(f"Duplicate application exists: {existing_id}")


class ValidationError(Exception):
    """Service-level validation failure (distinct from Pydantic)."""
    def __init__(self, message: str):
        super().__init__(message)
