"""Sicherheits-Header für alle Antworten (AP9c, CSP seit AP10b)."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Zwei Jahre. Kein preload: Der Eintrag in die Browser-Preload-Liste ist
# praktisch nicht zurückzuholen, und diese Domain ist eine
# Railway-Subdomain, die wir womöglich noch wechseln.
HSTS_VALUE = "max-age=63072000; includeSubDomains"

# Content-Security-Policy (AP10b).
#
# Aufgestellt gegen die tatsächlich gebaute Oberfläche und im Browser
# nachgeprüft — nicht aus dem Gedächtnis geschrieben. Eine zu enge Policy
# ergibt hier eine weisse Karte ohne einen einzigen Fehler im Netzwerk-Tab,
# weil die Kacheln im Worker verarbeitet werden.
#
# Warum die einzelnen Regeln so aussehen:
#
#   default-src 'none'   Alles, was nicht ausdrücklich erlaubt ist, bleibt
#                        verboten. Jede weitere Zeile ist damit eine bewusste
#                        Öffnung.
#   worker-src 'self'    MapLibre 6 laedt seinen Kachel-Worker als echte
#          blob:         Datei von der eigenen Origin
#                        (/assets/maplibre-gl-worker.mjs) — im Browser
#                        nachgeprüft, mit `worker-src blob:` allein bleibt
#                        die Karte weiss und im Netzwerk-Tab steht nichts.
#                        `blob:` bleibt daneben stehen, weil MapLibre je nach
#                        Bündelung auf den Blob-Weg zurückfällt.
#   child-src            Fallback für Browser, die worker-src nicht kennen
#                        (Safari vor 15.4) — sonst greift dort default-src.
#   img-src ... data:    MapLibre zeichnet auf Canvas und legt Sprites und
#          ... blob:     Glyphen als Blob/Data-URL an.
#   connect-src 'self'   Die PMTiles-Range-Requests und die API. Fremde Hosts
#                        gibt es bewusst keine: Schriften und Sprite liegen
#                        unter /basemap-assets im eigenen Build (ADR 0002).
#   style-src 'self'     Vite baut eine echte CSS-Datei; MapLibre setzt seine
#          'unsafe-inline'  Layout-Werte per Skript (davon unberührt), legt
#                        aber für die Controls ein <style>-Element an.
#
# Bewusst NICHT enthalten: 'unsafe-eval' (wird nicht gebraucht) und irgendein
# fremder Host.
CSP_DIRECTIVES = {
    "default-src": "'none'",
    "script-src": "'self'",
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: blob:",
    "font-src": "'self'",
    "connect-src": "'self'",
    "worker-src": "'self' blob:",
    "child-src": "'self' blob:",
    "manifest-src": "'self'",
    "base-uri": "'none'",
    "form-action": "'self'",
    "frame-ancestors": "'none'",
    "object-src": "'none'",
}

CSP_VALUE = "; ".join(f"{name} {wert}" for name, wert in CSP_DIRECTIVES.items())

SECURITY_HEADERS = {
    "Strict-Transport-Security": HSTS_VALUE,
    # Verhindert, dass der Browser einen Antworttyp errät statt Content-Type
    # zu glauben — relevant bei allem, was später hochgeladen wird.
    "X-Content-Type-Options": "nosniff",
    # Die App wird nie in einem fremden Rahmen dargestellt.
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": CSP_VALUE,
    # Kein Referrer an fremde Ziele: Die Pfade dieser App verraten sonst
    # Fund-IDs an jeden angeklickten Attributionslink.
    "Referrer-Policy": "no-referrer",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            # setdefault: Ein Endpunkt, der bewusst etwas anderes setzt,
            # behält es.
            response.headers.setdefault(name, value)
        return response
