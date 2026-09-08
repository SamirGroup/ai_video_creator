"""Project-wide pytest fixtures.

DRF's Anon/User/scoped throttle classes (FR-7) store their counters in
Django's cache framework. In dev/prod that's Redis (CACHES["default"]), which
persists across test runs — unlike the DB, pytest-django never resets it
between tests. Without clearing it, throttle counters accumulate across
unrelated tests in the same file/session and start returning 429s for
requests a test expects to succeed (e.g. more than 5 logins/minute across a
handful of tests). Clearing it before every test keeps each test's throttle
window independent, matching how a fresh cache backend behaves in CI.
"""
from __future__ import annotations

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    cache.clear()
    yield
