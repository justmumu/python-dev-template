"""Tests for the exception hierarchy."""

from your_package.errors import (
    AppError,
    InternalError,
    InvalidParamsError,
)


def test_app_error_base_default_type():
    assert AppError.error_type == "internal_error"


def test_invalid_params_error_type():
    err = InvalidParamsError("bad input")
    assert err.error_type == "invalid_params"
    assert str(err) == "bad input"


def test_internal_error_type():
    err = InternalError("boom")
    assert err.error_type == "internal_error"


def test_all_error_classes_are_app_errors():
    for cls in (InvalidParamsError, InternalError):
        assert issubclass(cls, AppError)
