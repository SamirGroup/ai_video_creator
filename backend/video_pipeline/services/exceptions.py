"""Pipeline-level errors that are not "the provider misbehaved".

Retry semantics are encoded in the base class, so `tasks.py` never has to keep a
list of "which errors are worth retrying":

* `ScriptParseError` extends `ProviderRetryableError` on purpose. LLM output is
  stochastic: a malformed JSON body is very often fixed by simply sampling again,
  and the retry budget (3) bounds the cost.
* `CostCeilingExceeded` extends `ProviderPermanentError`: retrying would spend
  more money, which is precisely what the ceiling exists to prevent (FR-52).
"""
from __future__ import annotations

from providers.exceptions import ProviderPermanentError, ProviderRetryableError


class ScriptParseError(ProviderRetryableError):
    """The model answered, but the payload was not a usable script object."""

    error_code = "script_unparseable"


class ScriptValidationError(ProviderRetryableError):
    """Parsed fine, but violated a hard content contract (e.g. no segments)."""

    error_code = "script_invalid"


class CostCeilingExceeded(ProviderPermanentError):
    """FR-52: the job's accumulated provider spend passed the configured limit."""

    error_code = "cost_ceiling_exceeded"


class JobNotReady(ProviderPermanentError):
    """The job is in a state where this stage must not run (cancelled, terminal,
    missing content preferences, ...). Retrying cannot change that.
    """

    error_code = "job_not_ready"
