"""
Core exceptions — uniform API error handling.

Ports Flask `bridge_app/utils/errors.py` into DRF idioms: an `APIError`
exception that DRF handlers translate into JSON {status, message, code}.
"""
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class APIError(APIException):
    """Base API exception with an explicit HTTP status code."""

    default_code = "api_error"

    def __init__(self, message, status_code=status.HTTP_400_BAD_REQUEST, payload=None):
        super().__init__(detail=message, code=status_code)
        self.status_code = status_code
        self.message = message
        self.payload = payload

    def __str__(self):
        return self.message


def api_exception_handler(exc, context):
    """DRF exception handler producing a uniform {status, message, code} body."""
    response = exception_handler(exc, context)
    if response is None:
        # Non-DRF exceptions (e.g. Django Http404, PermissionDenied) — re-raise
        # so Django's own handlers produce sensible responses.
        return None

    if isinstance(exc, APIError):
        body = {
            "status": "error",
            "message": exc.message,
            "code": exc.status_code,
        }
        if exc.payload:
            body["details"] = exc.payload
    elif isinstance(exc, APIException) and isinstance(exc.detail, (dict, list)):
        body = {
            "status": "error",
            "message": "Validation failed",
            "code": response.status_code,
            "details": exc.detail,
        }
    else:
        detail = getattr(exc, "detail", str(exc))
        body = {
            "status": "error",
            "message": str(detail),
            "code": response.status_code,
        }
    response.data = body
    return response
