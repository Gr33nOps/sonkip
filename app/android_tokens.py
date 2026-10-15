"""On-device public-session token provider (no desktop browser or login)."""
from yt_dlp.extractor.youtube.pot.provider import (
    PoTokenContext, PoTokenProvider, PoTokenResponse, PoTokenProviderError,
    register_provider,
)
from yt_dlp.extractor.youtube.pot.utils import WEBPO_CLIENTS, get_webpo_content_binding


@register_provider
class AndroidWebPoPTP(PoTokenProvider):
    PROVIDER_NAME = "sonkip-android"
    PROVIDER_VERSION = "1.0.0"
    BUG_REPORT_LOCATION = "https://github.com/Gr33nOps/sonkip/issues"
    _SUPPORTED_CLIENTS = WEBPO_CLIENTS
    _SUPPORTED_CONTEXTS = (PoTokenContext.GVS, PoTokenContext.PLAYER, PoTokenContext.SUBS)
    _SUPPORTED_EXTERNAL_REQUEST_FEATURES = ()

    def is_available(self):
        return True

    def _real_request_pot(self, request):
        from java import jclass
        try:
            token = jclass("io.github.gr33nops.sonkip.PublicTokenProvider").requestToken(
                get_webpo_content_binding(request)[0])
            if not token:
                raise ValueError("Empty public-session token")
            return PoTokenResponse(po_token=str(token))
        except Exception as exc:
            raise PoTokenProviderError("On-device YouTube token unavailable: " + str(exc)) from exc
