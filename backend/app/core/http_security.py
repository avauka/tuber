"""Sicherheits-Header für alle Antworten (AP9c).

Bewusst ohne Content-Security-Policy: Die gehört mit dem Frontend gesetzt
(AP10). Eine Policy für eine App zu schreiben, die es noch nicht gibt, führt
entweder zu einer wirkungslos weiten Regel oder zu einer, die beim ersten
echten Asset bricht.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Zwei Jahre. Kein preload: Der Eintrag in die Browser-Preload-Liste ist
# praktisch nicht zurückzuholen, und diese Domain ist eine
# Railway-Subdomain, die wir womöglich noch wechseln.
HSTS_VALUE = "max-age=63072000; includeSubDomains"

SECURITY_HEADERS = {
    "Strict-Transport-Security": HSTS_VALUE,
    # Verhindert, dass der Browser einen Antworttyp errät statt Content-Type
    # zu glauben — relevant bei allem, was später hochgeladen wird.
    "X-Content-Type-Options": "nosniff",
    # Die App wird nie in einem fremden Rahmen dargestellt.
    "X-Frame-Options": "DENY",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            # setdefault: Ein Endpunkt, der bewusst etwas anderes setzt,
            # behält es.
            response.headers.setdefault(name, value)
        return response
