from __future__ import annotations

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class UploadRateThrottle(SimpleRateThrottle):
    """Batas laju unggahan; membaca `settings.THROTTLE_UPLOAD_RATE` per request."""

    scope = "upload"

    def get_rate(self) -> str:
        return settings.THROTTLE_UPLOAD_RATE

    def get_cache_key(self, request, view) -> str | None:
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
