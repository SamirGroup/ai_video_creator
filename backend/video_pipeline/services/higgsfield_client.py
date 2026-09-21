"""Higgsfield asynchronous video API; credentials never leave the backend."""

from urllib.parse import quote, urlsplit

from providers.exceptions import ProviderPermanentError, ProviderResponseError

from .video_gen_client import RunwayClient, VideoTask, pick_clip_duration


class HiggsfieldClient(RunwayClient):
    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.base_url = "https://api.higgsfield.ai"
        self.status_urls = {}
        if ":" not in self._api_key or not all(self._api_key.split(":", 1)):
            raise ProviderPermanentError("HF_KEY must contain KEY_ID:KEY_SECRET.")

    def _headers(self):
        return {
            "Authorization": f"Key {self._api_key}",
            "Content-Type": "application/json",
        }

    def create_task(
        self,
        *,
        prompt,
        target_duration_sec,
        aspect_ratio="16:9",
        image_url=None,
        seed=None,
    ):
        if not prompt.strip() or aspect_ratio not in ("16:9", "9:16", "1:1"):
            raise ProviderPermanentError("Invalid Higgsfield prompt or aspect ratio.")
        if image_url or seed is not None:
            raise ProviderPermanentError(
                "This integration uses the documented text-to-video schema."
            )
        path = self.model.strip("/")
        if not path.startswith("kling-video/v3.0/") or not path.endswith(
            "/text-to-video"
        ):
            raise ProviderPermanentError("Unsupported Higgsfield endpoint.")
        duration = pick_clip_duration(target_duration_sec, self.allowed_durations)
        payload = {
            **self.config.get_option("request_options", {}),
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
        }
        response = self._request("POST", f"{self.base_url}/{path}", json=payload)
        data = self._json(response)
        task_id = str(data.get("request_id") or "")
        status_url = data.get("status_url")
        if not task_id or not status_url:
            raise ProviderResponseError(
                "Higgsfield response omitted request_id or status_url."
            )
        self.validate_status_url(status_url)
        self.status_urls[task_id] = status_url
        return VideoTask(
            task_id, duration, aspect_ratio, task_id, http_status=response.status_code
        )

    @staticmethod
    def validate_status_url(url):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.higgsfield.ai"
            or not parsed.path.startswith("/requests/")
        ):
            raise ProviderResponseError("Unexpected Higgsfield status URL.")

    def get_task(self, task_id):
        url = (
            self.status_urls.get(task_id)
            or f"{self.base_url}/requests/{quote(task_id, safe='')}/status"
        )
        self.validate_status_url(url)
        data = self._json(self._request("GET", url))
        state = data.get("status")
        mapping = {
            "queued": "PENDING",
            "in_progress": "RUNNING",
            "completed": "SUCCEEDED",
            "failed": "FAILED",
            "nsfw": "FAILED",
            "canceled": "CANCELED",
        }
        if state not in mapping:
            raise ProviderResponseError("Unknown Higgsfield request status.")
        return {
            **data,
            "status": mapping[state],
            "failureCode": state,
            "output": [data["video"]["url"]]
            if data.get("video", {}).get("url")
            else [],
        }
