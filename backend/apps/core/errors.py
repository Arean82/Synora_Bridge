"""
Django-level error handlers for plain (non-DRF) API views.

The pull/mock views are plain Django views, so DRF's exception handler does
not apply. `api_error_response` is a decorator that converts APIError /
Http404 raised in those views into uniform JSON responses, so a missing
template or path returns JSON instead of an HTML 500/404 page.
"""
import logging

from django.http import JsonResponse

from apps.core.exceptions import APIError

logger = logging.getLogger(__name__)


def api_error_response(view_func):
    """Wrap a Django view: return APIError / Http404 as JSON responses.

    Uses functools.wraps so attributes on the inner view (e.g. csrf_exempt,
    ratelimit flags) propagate to the wrapper — the CSRF middleware checks
    the final view object for csrf_exempt=True.
    """
    import functools

    @functools.wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except APIError as exc:
            return JsonResponse(
                {"status": "error", "message": exc.message, "code": exc.status_code},
                status=exc.status_code,
            )
        except Exception as exc:  # noqa: BLE001 - blanket for API views
            if getattr(exc, "status_code", None) == 404:
                return JsonResponse(
                    {"status": "error", "message": "Not found.", "code": 404}, status=404
                )
            logger.exception("Unhandled error in API view %s", view_func.__name__)
            return JsonResponse(
                {"status": "error", "message": "Internal server error.", "code": 500}, status=500
            )

    return _wrapped
