"""Single-User-Session (ADR 0005).

Ein Passwort, ein langlebiges signiertes Cookie, kein User-Modell und keine
DB-Berührung. Der Ablauf steckt im Token selbst — abgelaufene Signaturen sind
damit nicht widerrufbar, dafür kostet die Prüfung keine Abfrage.

Der Schutz greift als globale Dependency und ist bewusst fail-closed: Alles
unter `/api/` ist geschützt, sofern es nicht ausdrücklich in
PUBLIC_API_PATHS steht. Ein neuer Endpunkt ist damit von sich aus geschützt,
statt es erst zu werden, wenn jemand daran denkt.
"""

import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError
from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeTimedSerializer

SESSION_COOKIE = "tuber_session"
SESSION_SALT = "tuber-session"
TOKEN_SUBJECT = "single-user"

# 90 Tage (ADR 0005): Ein Re-Login mitten im Feldgang waere genau das, was
# der Offline-Sync nicht gebrauchen kann.
SESSION_MAX_AGE_S = 90 * 24 * 60 * 60

PUBLIC_API_PATHS = frozenset({"/api/health", "/api/auth/login"})

LOGIN_MAX_FAILURES = 5
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)

# Bewusst in-memory: Der Zähler wird bei jedem Neustart zurückgesetzt. Für
# einen Single-User-Dienst akzeptiert — wer den Prozess neu starten kann, hat
# ohnehin mehr Möglichkeiten als das Login-Formular.
_login_failures: dict[str, list[datetime]] = defaultdict(list)


def clear_login_attempts() -> None:
    """Zähler zurücksetzen (Tests, Wartung)."""
    _login_failures.clear()


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        # Fehlkonfiguration des Servers, nicht Fehler des Aufrufers.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{name} ist nicht gesetzt.",
        )
    return value


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_required_env("SESSION_SECRET"), salt=SESSION_SALT)


def issue_token() -> str:
    return _serializer().dumps(TOKEN_SUBJECT)


def token_is_valid(token: str) -> bool:
    try:
        # SignatureExpired erbt von BadSignature — abgelaufen und gefälscht
        # führen beide zum selben 401, ohne dem Aufrufer zu verraten, welches.
        _serializer().loads(token, max_age=SESSION_MAX_AGE_S)
    except BadSignature:
        return False
    return True


def verify_password(password: str) -> bool:
    hashed = _required_env("AUTH_PASSWORD_HASH")
    try:
        return PasswordHasher().verify(hashed, password)
    except (Argon2Error, InvalidHashError):
        return False


def _now() -> datetime:
    return datetime.now(UTC)


def check_login_allowed(key: str) -> None:
    jetzt = _now()
    aktuell = [zeit for zeit in _login_failures[key] if jetzt - zeit < LOGIN_FAILURE_WINDOW]
    _login_failures[key] = aktuell
    if len(aktuell) >= LOGIN_MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Zu viele Fehlversuche. Naechster Versuch in maximal "
                f"{int(LOGIN_FAILURE_WINDOW.total_seconds() // 60)} Minuten."
            ),
        )


def record_login_failure(key: str) -> None:
    _login_failures[key].append(_now())


def reset_login_failures(key: str) -> None:
    _login_failures.pop(key, None)


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unbekannt"


def require_session(request: Request) -> None:
    """Globale Dependency. Alles unter /api/ ausser den PUBLIC_API_PATHS."""
    pfad = request.url.path
    if not pfad.startswith("/api/") or pfad in PUBLIC_API_PATHS:
        return

    token = request.cookies.get(SESSION_COOKIE)
    if token is None or not token_is_valid(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht angemeldet oder Sitzung abgelaufen.",
        )
