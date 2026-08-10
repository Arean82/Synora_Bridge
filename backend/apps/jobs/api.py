"""Jobs domain router."""
from rest_framework.routers import DefaultRouter

from apps.jobs.views import FailedPayloadViewSet, JobLogViewSet, JobViewSet

router = DefaultRouter()
router.register("jobs", JobViewSet, basename="job")
router.register("job-logs", JobLogViewSet, basename="joblog")
router.register("failed-payloads", FailedPayloadViewSet, basename="failedpayload")
