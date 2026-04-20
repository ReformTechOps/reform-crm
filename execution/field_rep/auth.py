"""
Google OAuth for the field-rep app.

Ports the hub's `/auth/google` flow with one key change: the redirect URI is
env-driven (`OAUTH_REDIRECT_URI`) rather than hardcoded, so the same code can
serve `routes.reformchiropractic.app` in prod and `localhost` in docker-dev.

Required env vars (Coolify-injected in prod):
    GOOGLE_CLIENT_ID
    GOOGLE_CLIENT_SECRET
    OAUTH_REDIRECT_URI       e.g. https://routes.reformchiropractic.app/auth/google/callback
    ALLOWED_DOMAIN           e.g. reformchiropractic.com
    BASEROW_URL / BASEROW_API_TOKEN   for first-login staff registration (optional)

Sessions are stored in Redis (see `storage.py`) — completely separate from
hub.reformchiropractic.app sessions. No cross-domain SSO.
"""
import os
import secrets as _secrets
import time
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from hub.constants import T_STAFF

from . import storage

SESSION_COOKIE = "fr_session"
_SCOPE = "openid email profile"

router = APIRouter()


def _env() -> dict:
    return {
        "gid":          os.environ.get("GOOGLE_CLIENT_ID", ""),
        "gsec":         os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        "redirect_uri": os.environ.get("OAUTH_REDIRECT_URI", ""),
        "domain":       os.environ.get("ALLOWED_DOMAIN", ""),
        "br":           os.environ.get("BASEROW_URL", ""),
        "bt":           os.environ.get("BASEROW_API_TOKEN", ""),
    }


# ── Helpers used by the rest of the app ──────────────────────────────────────
async def get_session(request: Request) -> Optional[dict]:
    sid = request.cookies.get(SESSION_COOKIE, "")
    if not sid:
        return None
    return await storage.get_session(sid)


async def refresh_if_needed(sid: str, session: dict) -> str:
    if time.time() < session.get("expires_at", 0) - 60:
        return session.get("access_token", "")
    env = _env()
    async with httpx.AsyncClient() as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id":     env["gid"],
            "client_secret": env["gsec"],
            "refresh_token": session.get("refresh_token", ""),
            "grant_type":    "refresh_token",
        })
        data = r.json()
    if "access_token" not in data:
        return session.get("access_token", "")
    session["access_token"] = data["access_token"]
    session["expires_at"]   = time.time() + data.get("expires_in", 3600)
    await storage.put_session(sid, session)
    return session["access_token"]


# ── Routes ───────────────────────────────────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, error: str = ""):
    if await get_session(request):
        return RedirectResponse(url="/")
    err = ""
    if error == "domain":
        err = '<p class="login-err">Access restricted to authorized staff accounts.</p>'
    elif error:
        err = '<p class="login-err">Sign-in failed. Please try again.</p>'
    return HTMLResponse(f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Field Routes — Reform</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,-apple-system,sans-serif;background:#0d1b2a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh}}
.box{{background:#0a1628;border:1px solid #1e3a5f;border-radius:16px;padding:40px;width:340px;max-width:90vw}}
h1{{font-size:22px;font-weight:700;margin-bottom:6px}}
.sub{{font-size:13px;color:#64748b;margin-bottom:28px}}
.btn{{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;padding:11px;background:#fff;color:#333;border:1px solid #ddd;border-radius:8px;font-size:14px;font-weight:500;text-decoration:none}}
.btn:hover{{background:#f5f5f5}}
.login-err{{color:#ef4444;font-size:13px;margin-top:14px;text-align:center}}
</style></head><body><div class="box">
<h1>Field Routes</h1>
<div class="sub">Sign in with your Reform account</div>
<a href="/auth/google" class="btn">Sign in with Google</a>
{err}
</div></body></html>""")


@router.get("/auth/google", response_class=HTMLResponse)
async def auth_google(request: Request):
    env = _env()
    state = _secrets.token_urlsafe(32)
    await storage.put_oauth_state(state)
    params = urlencode({
        "client_id":     env["gid"],
        "redirect_uri":  env["redirect_uri"],
        "response_type": "code",
        "scope":         _SCOPE,
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    })
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    # Client-side redirect so any intermediary (e.g. Caddy) doesn't proxy Google's page.
    return HTMLResponse(
        '<html><head></head><body>'
        f'<script>window.location.href={url!r};</script>'
        f'<noscript><meta http-equiv="refresh" content="0;url={url}"></noscript>'
        '</body></html>'
    )


@router.get("/auth/google/callback")
async def auth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error or not code:
        return RedirectResponse("/login?error=1")
    if not await storage.check_and_del_oauth_state(state):
        return RedirectResponse("/login?error=1")

    env = _env()
    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth2.googleapis.com/token", data={
            "code":          code,
            "client_id":     env["gid"],
            "client_secret": env["gsec"],
            "redirect_uri":  env["redirect_uri"],
            "grant_type":    "authorization_code",
        })
        tokens = token_resp.json()
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {tokens.get('access_token', '')}"},
        )
        user = userinfo_resp.json()

    email = (user.get("email") or "").lower()
    allowed = env["domain"]
    if allowed and not email.endswith(f"@{allowed}"):
        return RedirectResponse("/login?error=domain")

    # First-login staff registration (same as hub) — non-fatal on failure.
    if T_STAFF and env["br"] and env["bt"]:
        try:
            async with httpx.AsyncClient(timeout=10) as sc:
                sr = await sc.get(
                    f"{env['br']}/api/database/rows/table/{T_STAFF}/"
                    f"?user_field_names=true&search={email}&size=5",
                    headers={"Authorization": f"Token {env['bt']}"},
                )
                found = any(
                    (row.get("Email") or "").lower().strip() == email
                    for row in sr.json().get("results", [])
                ) if sr.status_code == 200 else False
                if not found:
                    await sc.post(
                        f"{env['br']}/api/database/rows/table/{T_STAFF}/?user_field_names=true",
                        headers={"Authorization": f"Token {env['bt']}",
                                 "Content-Type": "application/json"},
                        json={"Name": user.get("name", email), "Email": email,
                              "Role": "field", "Active": True},
                    )
        except Exception:
            pass  # Don't block login if staff registration fails.

    sid = _secrets.token_urlsafe(32)
    await storage.put_session(sid, {
        "email":         email,
        "name":          user.get("name", email),
        "picture":       user.get("picture", ""),
        "access_token":  tokens.get("access_token", ""),
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at":    time.time() + tokens.get("expires_in", 3600),
    })
    resp = HTMLResponse('<html><head><meta http-equiv="refresh" content="0;url=/"></head></html>')
    resp.set_cookie(SESSION_COOKIE, sid, httponly=True, max_age=7 * 24 * 3600, samesite="lax")
    return resp


@router.get("/logout")
async def logout(request: Request):
    sid = request.cookies.get(SESSION_COOKIE, "")
    if sid:
        await storage.del_session(sid)
    resp = HTMLResponse('<html><head><meta http-equiv="refresh" content="0;url=/login"></head></html>')
    resp.delete_cookie(SESSION_COOKIE)
    return resp
