"""Custom exceptions. Each carries a stable ``error_type`` identifier."""


class AppError(Exception):
    """Base class for all application exceptions."""

    error_type: str = "internal_error"


class InvalidParamsError(AppError):
    """Input fails validation."""

    error_type = "invalid_params"


class InternalError(AppError):
    """Unexpected internal failure not covered by a more specific type."""

    error_type = "internal_error"
