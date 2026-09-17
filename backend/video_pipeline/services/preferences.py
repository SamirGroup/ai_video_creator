from types import SimpleNamespace


def job_preferences(job):
    """Use creator-approved settings for planned jobs even after channel preferences change."""
    preference = getattr(job, "preference", None)
    snapshot = (getattr(job, "generation_context", None) or {}).get("preference")
    if not snapshot:
        return preference
    values = (
        {
            field.name: getattr(preference, field.name)
            for field in preference._meta.fields
        }
        if preference
        else {}
    )
    values.update(snapshot)
    return SimpleNamespace(**values)
