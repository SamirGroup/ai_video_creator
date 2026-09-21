from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from providers.exceptions import (
    ProviderPermanentError,
    ProviderResponseError,
    ProviderAuthError,
    ProviderRateLimitError,
)
from video_pipeline.services.higgsfield_client import HiggsfieldClient


def client(responses):
    options = {
        "allowed_durations": list(range(3, 16)),
        "request_options": {"sound": "on"},
    }
    cfg = SimpleNamespace(
        model_name="kling-video/v3.0/pro/text-to-video",
        get_option=lambda key, default=None: options.get(key, default),
    )
    session = Mock()
    session.request.side_effect = [
        SimpleNamespace(status_code=status, headers={}, json=lambda data=data: data)
        for status, data in responses
    ]
    return HiggsfieldClient(
        cfg, api_key="key:secret", session=session, sleep=lambda _: None
    ), session


def test_submit_poll_and_accounted_duration():
    url = "https://api.higgsfield.ai/requests/abc/status"
    c, s = client(
        [
            (200, {"request_id": "abc", "status_url": url}),
            (200, {"status": "queued"}),
            (
                200,
                {
                    "status": "completed",
                    "video": {"url": "https://cdn.example.com/a.mp4"},
                },
            ),
        ]
    )
    task = c.create_task(prompt="Ocean", target_duration_sec=4.2, aspect_ratio="9:16")
    assert task.duration_sec == 5
    assert s.request.call_args.kwargs["headers"]["Authorization"] == "Key key:secret"
    assert s.request.call_args.kwargs["json"]["aspect_ratio"] == "9:16"
    assert c.wait_for_task(task.task_id).output_urls == (
        "https://cdn.example.com/a.mp4",
    )
    assert s.request.call_args.args[1] == url
    assert sum(call.args[0] == "POST" for call in s.request.call_args_list) == 1


@pytest.mark.parametrize(
    "status,exc", [(401, ProviderAuthError), (429, ProviderRateLimitError)]
)
def test_http_failures(status, exc):
    c, _ = client([(status, {})])
    with pytest.raises(exc):
        c.create_task(prompt="Ocean", target_duration_sec=5)


def test_moderation_and_unknown_status_fail_closed():
    c, _ = client([(200, {"status": "nsfw"})])
    with pytest.raises(ProviderPermanentError):
        c.wait_for_task("abc")
    c, _ = client([(200, {"status": "unexpected"})])
    with pytest.raises(ProviderResponseError):
        c.wait_for_task("abc")


def test_no_credentials_sent_to_untrusted_status_url():
    c, s = client(
        [
            (
                200,
                {
                    "request_id": "abc",
                    "status_url": "https://evil.example/requests/abc",
                },
            )
        ]
    )
    with pytest.raises(ProviderResponseError):
        c.create_task(prompt="Ocean", target_duration_sec=5)
    assert s.request.call_count == 1
