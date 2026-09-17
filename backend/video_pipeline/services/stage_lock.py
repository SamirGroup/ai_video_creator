"""Serialize paid stages for a job across Celery workers without a long DB transaction."""

from functools import wraps
from django.db import connection
from providers.exceptions import ProviderRetryableError


def serialized_paid_stage(function):
    @wraps(function)
    def run(job, *args, **kwargs):
        key = job.pk.int % (2**63)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
            if not cursor.fetchone()[0]:
                raise ProviderRetryableError(
                    "Another worker is processing this video.",
                    error_code="job_stage_busy",
                )
        try:
            return function(job, *args, **kwargs)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [key])

    return run
