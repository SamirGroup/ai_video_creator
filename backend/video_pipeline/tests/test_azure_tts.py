from unittest.mock import Mock
from xml.etree.ElementTree import fromstring

import pytest
from providers.models import ApiCredentialConfig
from providers.exceptions import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from video_pipeline.services.azure_tts_client import AzureTTSClient


def client_and_session(status=200, content_type="audio/mpeg"):
    config = ApiCredentialConfig(
        provider="azure_tts",
        model_name="neural",
        config={
            "endpoint": "https://example.invalid/cognitiveservices/v1",
            "language_codes": {"uz": "uz-UZ"},
        },
    )
    session = Mock()
    session.post.return_value = Mock(
        status_code=status, content=b"audio", headers={"Content-Type": content_type}
    )
    return AzureTTSClient(config, api_key="test-only", session=session), session


def test_ssml_escapes_narration_and_preserves_locale():
    client, session = client_and_session()
    result = client.synthesize(
        "A < B & C", voice_id="uz-UZ-MadinaNeural", language_code="uz"
    )
    kwargs = session.post.call_args.kwargs
    xml = fromstring(kwargs["data"])
    assert xml[0].text == "A < B & C"
    assert xml.attrib["{http://www.w3.org/XML/1998/namespace}lang"] == "uz-UZ"
    assert result.audio == b"audio"
    assert kwargs["timeout"] == 120


@pytest.mark.parametrize(
    ("status", "error"), [(401, ProviderAuthError), (429, ProviderRateLimitError)]
)
def test_provider_errors_are_classified(status, error):
    client, _ = client_and_session(status)
    with pytest.raises(error):
        client.synthesize("Hello", voice_id="voice", language_code="uz")


def test_non_audio_response_is_rejected():
    client, _ = client_and_session(content_type="application/json")
    with pytest.raises(ProviderResponseError):
        client.synthesize("Hello", voice_id="voice", language_code="uz")
