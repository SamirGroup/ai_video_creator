"""Bind publication approval to the exact public metadata."""

import hashlib
import json


def metadata_digest(job):
    payload = {"title": job.title, "description": job.description, "tags": job.tags}
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
