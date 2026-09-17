"""Font selection for scripts shipped by the render image's Noto packages."""

from pathlib import Path

from django.conf import settings

_FONTS = {
    "zh": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "ja": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "ko": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "ar": "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "ar-EG": "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "fa": "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "ur": "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    "hi": "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "bn": "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
    "th": "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
    "ka": "/usr/share/fonts/truetype/noto/NotoSansGeorgian-Regular.ttf",
}


def font_for_language(language: str) -> str:
    override = getattr(settings, "ASSEMBLY_LANGUAGE_FONTS", {}).get(language)
    candidate = override or _FONTS.get(
        language, "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
    )
    if Path(candidate).is_file():
        return candidate
    return str(getattr(settings, "ASSEMBLY_FONT_FILE", "") or "")
