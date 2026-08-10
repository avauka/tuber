"""Login und Logout (ADR 0005)."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.core.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_S,
    check_login_allowed,
    client_key,
    issue_token,
    record_login_failure,
    reset_login_failures,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    schluessel = client_key(request)
    check_login_allowed(schluessel)

    if not verify_password(payload.password):
        record_login_failure(schluessel)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Passwort falsch.")

    reset_login_failures(schluessel)
    response.set_cookie(
        SESSION_COOKIE,
        issue_token(),
        max_age=SESSION_MAX_AGE_S,
        # httpOnly: kein Zugriff aus JavaScript, damit ein XSS die Sitzung
        # nicht mitnehmen kann. Secure: nur ueber HTTPS — Railway terminiert
        # TLS, im Feld laeuft ohnehin nichts anderes.
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return {"status": "angemeldet"}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "abgemeldet"}
