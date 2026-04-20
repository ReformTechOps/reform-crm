#!/usr/bin/env python3
"""
Outreach Hub — Modal FastAPI app.
Google OAuth-protected dashboard for PI Attorney, Guerilla Marketing, Community Outreach.

Deploy:
    $env:PYTHONUTF8="1"
    modal deploy execution/modal_outreach_hub.py

Requires Modal secret "outreach-hub-secrets":
    GOOGLE_CLIENT_ID=<from GCP>
    GOOGLE_CLIENT_SECRET=<from GCP>
    ALLOWED_DOMAIN=reformchiropractic.com
    BASEROW_URL=https://baserow.reformchiropractic.app
    BASEROW_API_TOKEN=<token>
"""

import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
import modal

# Ensure hub package is importable at deploy time
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))

from hub.shared import (
    _tool_page, _has_social_access, _is_admin,
    _has_hub_access, _get_allowed_hubs, _forbidden_page,
    T_ATT_VENUES, T_ATT_ACTS, T_GOR_VENUES, T_GOR_ACTS, T_GOR_BOXES,
    T_COM_VENUES, T_COM_ACTS, T_GOR_ROUTES, T_GOR_ROUTE_STOPS,
    T_PI_ACTIVE, T_PI_BILLED, T_PI_AWAITING, T_PI_CLOSED, T_PI_FINANCE,
    T_STAFF, T_EVENTS, T_LEADS,
)
from hub.guerilla_map import _gorilla_map_page
from hub.route_planner import _route_planner_page, _outreach_list_page
from hub.guerilla_pages import (
    _gorilla_log_page,
    _gorilla_events_internal_page, _gorilla_events_external_page,
    _gorilla_businesses_page, _gorilla_boxes_page,
    _gorilla_routes_page, _gorilla_routes_new_page,
)
from hub.mobile import (
    _mobile_home_page, _mobile_route_page, _mobile_routes_dashboard_page,
    _mobile_lead_capture_page, _mobile_recent_page, _mobile_map_page,
)
from hub.dashboard import _login_page, _hub_page, _calendar_page, _coming_soon_page
from hub.outreach import _directory_page, _unified_directory_page, _map_page
from hub.pi_cases import _patients_page, _firms_page
from hub.billing import _billing_page
from hub.comms import _contacts_page, _communications_email_page
from hub.social import _social_poster_hub_page, _social_schedule_page
from hub.events import _event_detail_page, _lead_form_page, _leads_dashboard_page
from hub import guerilla_api

app = modal.App("outreach-hub")
image = (
    modal.Image.debian_slim()
    .pip_install("fastapi[standard]", "python-multipart", "httpx")
    .add_local_python_source("hub")
)

# ─── Session / OAuth state stores ──────────────────────────────────────────────
hub_sessions     = modal.Dict.from_name("hub-sessions",     create_if_missing=True)
hub_oauth_states = modal.Dict.from_name("hub-oauth-states", create_if_missing=True)
hub_cache        = modal.Dict.from_name("hub-cache",        create_if_missing=True)

CACHE_TTL = 120  # seconds — all tables cached for 2 minutes

# ─── Table cache helpers ───────────────────────────────────────────────────────
async def _fetch_table_all(br: str, bt: str, tid: int) -> list:
    """Fetch all rows for a table using parallel page requests."""
    import asyncio
    headers = {"Authorization": f"Token {bt}"}
    base_url = f"{br}/api/database/rows/table/{tid}/?size=200&user_field_names=true&page="
    async with __import__("httpx").AsyncClient(timeout=30) as client:
        r1 = await client.get(base_url + "1", headers=headers)
        if not r1.is_success:
            return []
        d1 = r1.json()
        rows = list(d1.get("results", []))
        if not d1.get("next"):
            return rows
        total_pages = (d1.get("count", 0) + 199) // 200
        resps = await asyncio.gather(*[
            client.get(base_url + str(p), headers=headers)
            for p in range(2, total_pages + 1)
        ])
        for resp in resps:
            if resp.is_success:
                rows.extend(resp.json().get("results", []))
    return rows

async def _cached_table(tid: int, br: str, bt: str) -> list:
    key = f"table:{tid}"
    try:
        cached = hub_cache.get(key)
        if cached and (time.time() - cached.get("ts", 0)) < CACHE_TTL:
            return cached["data"]
    except Exception:
        pass
    rows = await _fetch_table_all(br, bt, tid)
    try:
        hub_cache[key] = {"data": rows, "ts": time.time()}
    except Exception:
        pass
    return rows

# ─── Auth ──────────────────────────────────────────────────────────────────────
SESSION_COOKIE = "hub_session"

def _get_session(req) -> dict | None:
    sid = req.cookies.get(SESSION_COOKIE)
    if not sid:
        return None
    return hub_sessions.get(sid)

def _ok(req) -> bool:
    return _get_session(req) is not None

def _get_user(req) -> dict:
    return _get_session(req) or {}


# ──────────────────────────────────────────────────────────────────────────────
# BACKGROUND CACHE WARMER — keeps dashboard tables always fresh
# ──────────────────────────────────────────────────────────────────────────────
_WARM_TABLES = [
    T_ATT_VENUES, T_GOR_VENUES, T_COM_VENUES,
    T_PI_ACTIVE, T_PI_BILLED, T_PI_AWAITING, T_PI_CLOSED,
    T_GOR_BOXES, T_GOR_ROUTES, T_GOR_ROUTE_STOPS, T_GOR_ACTS,
]

@app.function(
    image=image,
    secrets=[modal.Secret.from_name("outreach-hub-secrets")],
    schedule=modal.Period(seconds=90),
    timeout=120,
)
async def warm_cache():
    import asyncio
    br = os.environ.get("BASEROW_URL", "")
    bt = os.environ.get("BASEROW_API_TOKEN", "")
    if not br or not bt:
        return
    results = await asyncio.gather(*[
        _fetch_table_all(br, bt, tid) for tid in _WARM_TABLES
    ])
    for tid, rows in zip(_WARM_TABLES, results):
        try:
            hub_cache[f"table:{tid}"] = {"data": rows, "ts": time.time()}
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# MODAL APP
# ──────────────────────────────────────────────────────────────────────────────
@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("outreach-hub-secrets"),
        modal.Secret.from_name("bunny-secrets"),
    ],
    min_containers=1,
)
@modal.asgi_app()
def web():
    import httpx
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

    fapp = FastAPI()

    def _env():
        return {
            "br":     os.environ.get("BASEROW_URL", "https://baserow.reformchiropractic.app"),
            "bt":     os.environ.get("BASEROW_API_TOKEN", ""),
            "gid":    os.environ.get("GOOGLE_CLIENT_ID", ""),
            "gsec":   os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            "domain": os.environ.get("ALLOWED_DOMAIN", ""),
        }

    def _redirect_uri(request: Request) -> str:
        host = request.headers.get("host", "localhost:8000")
        if "localhost" in host or "127.0.0.1" in host:
            return f"http://{host}/auth/google/callback"
        return "https://hub.reformchiropractic.app/auth/google/callback"

    async def _refresh_if_needed(sid: str, session: dict, env: dict) -> str:
        if time.time() < session.get("expires_at", 0) - 60:
            return session["access_token"]
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
        session["expires_at"] = time.time() + data.get("expires_in", 3600)
        hub_sessions[sid] = session
        return session["access_token"]

    # ── Login / OAuth ──────────────────────────────────────────────────────────
    @fapp.get("/login", response_class=HTMLResponse)
    async def login_get(request: Request, error: str = ""):
        if _ok(request):
            return RedirectResponse(url="/")
        return HTMLResponse(_login_page(error))

    @fapp.get("/auth/google", response_class=HTMLResponse)
    async def auth_google(request: Request):
        env = _env()
        state = secrets.token_urlsafe(32)
        hub_oauth_states[state] = time.time()
        params = urlencode({
            "client_id":     env["gid"],
            "redirect_uri":  _redirect_uri(request),
            "response_type": "code",
            "scope":         "openid email profile https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly",
            "access_type":   "offline",
            "prompt":        "consent",
            "state":         state,
        })
        google_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
        # Use client-side redirect so browser navigates to Google directly
        # (Cloudflare Worker's redirect:follow would proxy Google's page otherwise)
        return HTMLResponse(
            f'<html><head></head><body>'
            f'<script>window.location.href={repr(google_url)};</script>'
            f'<noscript><meta http-equiv="refresh" content="0;url={google_url}"></noscript>'
            f'</body></html>'
        )

    @fapp.get("/auth/google/callback")
    async def auth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        if error or not code:
            return RedirectResponse("/login?error=1")
        stored_time = hub_oauth_states.get(state)
        if not stored_time or (time.time() - stored_time) > 300:
            return RedirectResponse("/login?error=1")
        del hub_oauth_states[state]

        env = _env()
        async with httpx.AsyncClient() as client:
            token_resp = await client.post("https://oauth2.googleapis.com/token", data={
                "code":          code,
                "client_id":     env["gid"],
                "client_secret": env["gsec"],
                "redirect_uri":  _redirect_uri(request),
                "grant_type":    "authorization_code",
            })
            tokens = token_resp.json()
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {tokens.get('access_token','')}"}
            )
            user = userinfo_resp.json()

        email = user.get("email", "")
        allowed = env["domain"]
        if allowed and not email.endswith(f"@{allowed}"):
            return RedirectResponse("/login?error=domain")

        sid = secrets.token_urlsafe(32)
        hub_sessions[sid] = {
            "email":         email,
            "name":          user.get("name", email),
            "picture":       user.get("picture", ""),
            "access_token":  tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token", ""),
            "expires_at":    time.time() + tokens.get("expires_in", 3600),
        }

        # Auto-register in Staff table if not already there
        try:
            staff_tid = T_STAFF
            if staff_tid:
                async with httpx.AsyncClient(timeout=10) as sc:
                    sr = await sc.get(
                        f"{env['br']}/api/database/rows/table/{staff_tid}/"
                        f"?user_field_names=true&search={email}&size=5",
                        headers={"Authorization": f"Token {env['bt']}"},
                    )
                    found = False
                    if sr.status_code == 200:
                        for row in sr.json().get("results", []):
                            if (row.get("Email") or "").lower().strip() == email.lower():
                                found = True
                                break
                    if not found:
                        await sc.post(
                            f"{env['br']}/api/database/rows/table/{staff_tid}/"
                            f"?user_field_names=true",
                            headers={"Authorization": f"Token {env['bt']}",
                                     "Content-Type": "application/json"},
                            json={
                                "Name": user.get("name", email),
                                "Email": email,
                                "Role": "field",
                                "Active": True,
                            },
                        )
        except Exception:
            pass  # Don't block login if staff registration fails

        resp = HTMLResponse('<html><head><meta http-equiv="refresh" content="0;url=/"></head></html>')
        resp.set_cookie(SESSION_COOKIE, sid, httponly=True, max_age=86400 * 7, samesite="lax")
        return resp

    @fapp.get("/logout")
    async def logout(request: Request):
        sid = request.cookies.get(SESSION_COOKIE)
        if sid:
            try:
                del hub_sessions[sid]
            except KeyError:
                pass
        resp = HTMLResponse('<html><head><meta http-equiv="refresh" content="0;url=/login"></head></html>')
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    # ── Table data proxy (cached) ───────────────────────────────────────────────
    @fapp.get("/api/data/{tid}")
    async def table_data(tid: int, request: Request):
        if not _ok(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        env = _env()
        rows = await _cached_table(tid, env["br"], env["bt"])
        return JSONResponse(rows)

    # ── Edit patient firm (writes Law Firm Name + Firm History) ────────────────
    _STAGE_TO_PI_TID = {
        "active":   T_PI_ACTIVE,
        "billed":   T_PI_BILLED,
        "awaiting": T_PI_AWAITING,
        "closed":   T_PI_CLOSED,
    }

    @fapp.patch("/api/patients/{stage}/{row_id}/firm")
    async def edit_patient_firm(stage: str, row_id: int, request: Request):
        if not _ok(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        tid = _STAGE_TO_PI_TID.get(stage)
        if not tid:
            return JSONResponse({"error": f"invalid stage: {stage}"}, status_code=400)

        body = await request.json()
        new_firm = (body.get("new_firm") or "").strip()
        if not new_firm:
            return JSONResponse({"error": "new_firm required"}, status_code=400)

        env = _env()
        br, bt = env["br"], env["bt"]

        # Fetch current row to read old firm + existing history
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{br}/api/database/rows/table/{tid}/{row_id}/?user_field_names=true",
                headers={"Authorization": f"Token {bt}"},
            )
            if r.status_code != 200:
                return JSONResponse({"error": f"fetch failed: {r.status_code}"}, status_code=r.status_code)
            row = r.json()

        old_firm = (row.get("Law Firm Name") or "").strip()
        existing_history = (row.get("Firm History") or "").strip()

        if new_firm == old_firm:
            return JSONResponse({"error": "no change"}, status_code=400)

        # Build new history chain. Existing format: "A -> B -> C (current)".
        # Strip (current) from the existing chain, append old_firm with today's
        # date marker, then append new firm as current.
        import datetime
        today = datetime.date.today().isoformat()

        def strip_current(chain: str) -> str:
            # Remove trailing " (current)" from the last segment if present
            if chain.endswith("(current)"):
                return chain[:-len("(current)")].strip()
            return chain

        parts = []
        if existing_history:
            parts.append(strip_current(existing_history))
        if old_firm:
            parts.append(f"{old_firm} (until {today})")
        parts.append(f"{new_firm} (current)")
        new_history = " -> ".join(p for p in parts if p)

        # Write to Baserow
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.patch(
                f"{br}/api/database/rows/table/{tid}/{row_id}/?user_field_names=true",
                headers={"Authorization": f"Token {bt}", "Content-Type": "application/json"},
                json={"Law Firm Name": new_firm, "Firm History": new_history},
            )
            if r.status_code != 200:
                return JSONResponse(
                    {"error": f"update failed: {r.status_code}", "detail": r.text[:300]},
                    status_code=r.status_code,
                )
            updated = r.json()

        # Invalidate cache so next read reflects the change
        try:
            hub_cache.pop(f"table:{tid}", None)
        except Exception:
            pass

        return JSONResponse({
            "ok": True,
            "row": updated,
            "Law Firm Name": new_firm,
            "Firm History": new_history,
        })

    # ── Contact autocomplete (for compose modal) ───────────────────────────────
    @fapp.get("/api/contacts/autocomplete")
    async def contacts_autocomplete(request: Request):
        if not _ok(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        import asyncio
        env = _env()
        br, bt = env["br"], env["bt"]
        att, gor, com = await asyncio.gather(
            _cached_table(T_ATT_VENUES, br, bt),
            _cached_table(T_GOR_VENUES, br, bt),
            _cached_table(T_COM_VENUES, br, bt),
        )
        contacts = []
        for r in att:
            n = r.get("Law Firm Name") or ""
            e = r.get("Email") or r.get("Contact Email") or ""
            if n: contacts.append({"n": n, "e": e})
        for r in gor:
            n = r.get("Name") or ""
            e = r.get("Email") or ""
            if n: contacts.append({"n": n, "e": e})
        for r in com:
            n = r.get("Name") or ""
            e = r.get("Email") or ""
            if n: contacts.append({"n": n, "e": e})
        contacts.sort(key=lambda c: c["n"].lower())
        return JSONResponse(contacts)

    # ── Dashboard batch endpoint (single request for all dashboard data) ──────
    @fapp.get("/api/dashboard")
    async def dashboard_batch(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        import asyncio
        env = _env()
        br, bt = env["br"], env["bt"]
        hubs = _get_allowed_hubs(session)

        # Only fetch tables the user has access to
        att = gor = com = boxes = []
        pi_act = pi_bil = pi_aw = pi_cl = []
        fetches = {}
        if "attorney" in hubs:
            fetches["att"] = _cached_table(T_ATT_VENUES, br, bt)
        if "guerilla" in hubs:
            fetches["gor"] = _cached_table(T_GOR_VENUES, br, bt)
            fetches["boxes"] = _cached_table(T_GOR_BOXES, br, bt)
        if "community" in hubs:
            fetches["com"] = _cached_table(T_COM_VENUES, br, bt)
        if "pi_cases" in hubs:
            fetches["pi_act"] = _cached_table(T_PI_ACTIVE, br, bt)
            fetches["pi_bil"] = _cached_table(T_PI_BILLED, br, bt)
            fetches["pi_aw"] = _cached_table(T_PI_AWAITING, br, bt)
            fetches["pi_cl"] = _cached_table(T_PI_CLOSED, br, bt)

        if fetches:
            keys = list(fetches.keys())
            results = await asyncio.gather(*fetches.values())
            resolved = dict(zip(keys, results))
            att = resolved.get("att", [])
            gor = resolved.get("gor", [])
            com = resolved.get("com", [])
            boxes = resolved.get("boxes", [])
            pi_act = resolved.get("pi_act", [])
            pi_bil = resolved.get("pi_bil", [])
            pi_aw = resolved.get("pi_aw", [])
            pi_cl = resolved.get("pi_cl", [])

        def slim(row, name_field):
            return {
                "cs": row.get("Contact Status"),
                "fu": row.get("Follow-Up Date"),
                "n": row.get(name_field) or row.get("Name") or row.get("Law Firm Name") or "",
            }

        return JSONResponse({
            "att": [slim(r, "Law Firm Name") for r in att],
            "gor": [slim(r, "Name") for r in gor],
            "com": [slim(r, "Name") for r in com],
            "pi": {"a": len(pi_act), "b": len(pi_bil), "w": len(pi_aw), "c": len(pi_cl)},
            "boxes": [{"s": r.get("Status"), "d": r.get("Date Placed"), "p": r.get("Pickup Days")} for r in boxes],
        })

    # ── Calendar API ───────────────────────────────────────────────────────────
    @fapp.get("/api/calendar/events")
    async def calendar_events(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        env = _env()
        sid = request.cookies.get(SESSION_COOKIE, "")
        token = await _refresh_if_needed(sid, session, env)
        if not token:
            return JSONResponse({"error": "no_token"}, status_code=401)
        cal_id = os.environ.get("CALENDAR_ID", "")
        if not cal_id:
            embed = os.environ.get("GOOGLE_CALENDAR_EMBED_URL", "")
            cal_id = unquote(parse_qs(urlparse(embed).query).get("src", [""])[0])
        if not cal_id:
            return JSONResponse({"items": []})
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        url = (f"https://www.googleapis.com/calendar/v3/calendars/{quote(cal_id)}/events"
               f"?timeMin={now_iso}&maxResults=20&singleEvents=true&orderBy=startTime")
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            return JSONResponse({"error": "fetch_failed", "status": r.status_code, "detail": r.text[:500]},
                                status_code=502)
        data = r.json()
        def slim(ev):
            start = ev.get("start", {})
            end   = ev.get("end", {})
            all_day = "date" in start
            return {
                "summary":  ev.get("summary", "(no title)"),
                "start":    start.get("dateTime") or start.get("date", ""),
                "end":      end.get("dateTime") or end.get("date", ""),
                "allDay":   all_day,
                "location": ev.get("location", ""),
                "link":     ev.get("htmlLink", ""),
            }
        return JSONResponse({"items": [slim(ev) for ev in data.get("items", [])]})

    # ── Gmail API ──────────────────────────────────────────────────────────────
    @fapp.post("/api/gmail/send")
    async def gmail_send(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        body = await request.json()
        to = body.get("to", "")
        cc = body.get("cc", "")
        bcc = body.get("bcc", "")
        subject = body.get("subject", "")
        text = body.get("body", "")
        thread_id = body.get("threadId", "")
        if not to or not subject or not text:
            return JSONResponse({"error": "missing fields"}, status_code=400)

        env = _env()
        sid = request.cookies.get(SESSION_COOKIE, "")
        token = await _refresh_if_needed(sid, session, env)

        import base64, email as emaillib
        msg = emaillib.message.EmailMessage()
        msg["From"] = session["email"]
        msg["To"] = to
        if cc:  msg["Cc"] = cc
        if bcc: msg["Bcc"] = bcc
        msg["Subject"] = subject
        msg.set_content(text)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        payload = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id

        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
        return JSONResponse(r.json(), status_code=r.status_code)

    @fapp.get("/api/gmail/threads")
    async def gmail_threads(request: Request, contact_email: str = ""):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)

        env = _env()
        sid = request.cookies.get(SESSION_COOKIE, "")
        token = await _refresh_if_needed(sid, session, env)

        params = {"maxResults": 15}
        if contact_email:
            params["q"] = f"from:{contact_email} OR to:{contact_email}"

        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/threads",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            meta = r.json().get("threads", [])
            threads = []
            for t in meta[:10]:
                tr = await client.get(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{t['id']}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"format": "metadata", "metadataHeaders": ["Subject", "From", "To", "Date"]},
                )
                td = tr.json()
                # Flatten into a simpler structure
                msgs = td.get("messages", [])
                subject = ""
                snippet = td.get("snippet", "")
                from_addr = ""
                date_str = ""
                for m in msgs[:1]:
                    for h in m.get("payload", {}).get("headers", []):
                        if h["name"] == "Subject": subject = h["value"]
                        if h["name"] == "From": from_addr = h["value"]
                        if h["name"] == "Date": date_str = h["value"]
                threads.append({
                    "id": td.get("id", ""),
                    "subject": subject,
                    "snippet": snippet,
                    "from": from_addr,
                    "date": date_str,
                    "messageCount": len(msgs),
                })
        return JSONResponse({"threads": threads})

    @fapp.get("/api/gmail/thread/{thread_id}")
    async def gmail_thread_detail(thread_id: str, request: Request):
        import base64
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        env = _env()
        sid = request.cookies.get(SESSION_COOKIE, "")
        token = await _refresh_if_needed(sid, session, env)

        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "full"},
            )
        td = r.json()
        messages = []
        for m in td.get("messages", []):
            headers = {h["name"]: h["value"] for h in m.get("payload", {}).get("headers", [])}
            # Extract text body
            body_text = ""
            def _extract(part):
                nonlocal body_text
                if body_text:
                    return
                mime = part.get("mimeType", "")
                if mime == "text/plain" and part.get("body", {}).get("data"):
                    body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                for sub in part.get("parts", []):
                    _extract(sub)
            _extract(m.get("payload", {}))
            messages.append({
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "date": headers.get("Date", ""),
                "subject": headers.get("Subject", ""),
                "body": body_text,
            })
        return JSONResponse({"messages": messages})

    # ── Page helper ────────────────────────────────────────────────────────────
    def _guard(request):
        """Return (user, br, bt) or raise redirect."""
        session = _get_session(request)
        if not session:
            return None, None, None
        env = _env()
        return session, env["br"], env["bt"]

    # ── Hub ────────────────────────────────────────────────────────────────────
    def _is_mobile(request: Request) -> bool:
        ua = (request.headers.get("user-agent") or "").lower()
        return any(k in ua for k in ("iphone", "android", "mobile", "ipod"))

    @fapp.get("/", response_class=HTMLResponse)
    async def hub(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        return HTMLResponse(_hub_page(br, bt, user=user))

    # ── Tool dashboards (viewable by field users, read-only) ──────────────────
    @fapp.get("/attorney", response_class=HTMLResponse)
    async def attorney(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _has_hub_access(user, "attorney"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_tool_page("attorney", br, bt, user=user))

    @fapp.get("/guerilla", response_class=HTMLResponse)
    async def gorilla(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _has_hub_access(user, "guerilla"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_tool_page("gorilla", br, bt, user=user))

    @fapp.get("/community", response_class=HTMLResponse)
    async def community(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _has_hub_access(user, "community"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_tool_page("community", br, bt, user=user))

    # ── Map directories (admin only) ──────────────────────────────────────────
    @fapp.get("/outreach/planner", response_class=HTMLResponse)
    async def route_planner(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user):
            return RedirectResponse(url="/m")
        return HTMLResponse(_route_planner_page(br, bt, user=user))

    @fapp.get("/outreach/list", response_class=HTMLResponse)
    async def outreach_list(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_outreach_list_page(br, bt, user=user))

    @fapp.get("/attorney/map")
    async def attorney_map(request: Request):
        return RedirectResponse(url="/outreach/planner", status_code=302)

    @fapp.get("/guerilla/map")
    async def gorilla_map(request: Request):
        return RedirectResponse(url="/outreach/planner", status_code=302)

    @fapp.get("/guerilla/log")
    async def gorilla_log_page(request: Request):
        return RedirectResponse(url="/guerilla", status_code=302)

    @fapp.get("/guerilla/events/internal", response_class=HTMLResponse)
    async def gorilla_events_internal(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        if not _has_hub_access(user, "guerilla"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_gorilla_events_internal_page(br, bt, user=user))

    @fapp.get("/guerilla/events/external", response_class=HTMLResponse)
    async def gorilla_events_external(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        if not _has_hub_access(user, "guerilla"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_gorilla_events_external_page(br, bt, user=user))

    @fapp.get("/guerilla/businesses", response_class=HTMLResponse)
    async def gorilla_businesses(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        if not _has_hub_access(user, "guerilla"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_gorilla_businesses_page(br, bt, user=user))

    @fapp.get("/guerilla/boxes", response_class=HTMLResponse)
    async def gorilla_boxes(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        if not _has_hub_access(user, "guerilla"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_gorilla_boxes_page(br, bt, user=user))

    @fapp.get("/community/map")
    async def community_map(request: Request):
        return RedirectResponse(url="/outreach/planner", status_code=302)

    @fapp.get("/guerilla/routes", response_class=HTMLResponse)
    async def gorilla_routes(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _has_hub_access(user, "guerilla"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_gorilla_routes_page(br, bt, user=user))

    @fapp.get("/guerilla/routes/new", response_class=HTMLResponse)
    async def gorilla_routes_new(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        if not _has_hub_access(user, "guerilla"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_gorilla_routes_new_page(br, bt, user=user))

    # ── Unified contact list — redirect to Outreach Directory ───────────────
    @fapp.get("/outreach/contacts", response_class=HTMLResponse)
    async def outreach_contacts(request: Request):
        return RedirectResponse(url="/outreach/list", status_code=302)

    # ── Contact list directories (admin only, legacy — kept for bookmarks) ───
    @fapp.get("/attorney/directory", response_class=HTMLResponse)
    async def attorney_directory(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        if not _has_hub_access(user, "attorney"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_directory_page("attorney", br, bt, user=user))

    @fapp.get("/guerilla/directory", response_class=HTMLResponse)
    async def gorilla_directory(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        if not _has_hub_access(user, "guerilla"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_directory_page("gorilla", br, bt, user=user))

    @fapp.get("/community/directory", response_class=HTMLResponse)
    async def community_directory(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        if not _has_hub_access(user, "community"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_directory_page("community", br, bt, user=user))

    # ── PI Cases (admin only) ─────────────────────────────────────────────────
    @fapp.get("/patients", response_class=HTMLResponse)
    async def patients(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        if not _has_hub_access(user, "pi_cases"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_patients_page(br, bt, user=user))

    @fapp.get("/patients/active", response_class=HTMLResponse)
    async def patients_active(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_patients_page(br, bt, 'active', user=user))

    @fapp.get("/patients/billed", response_class=HTMLResponse)
    async def patients_billed(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_patients_page(br, bt, 'billed', user=user))

    @fapp.get("/patients/awaiting", response_class=HTMLResponse)
    async def patients_awaiting(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_patients_page(br, bt, 'awaiting', user=user))

    @fapp.get("/patients/closed", response_class=HTMLResponse)
    async def patients_closed(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_patients_page(br, bt, 'closed', user=user))

    @fapp.get("/firms", response_class=HTMLResponse)
    async def firms(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_firms_page(br, bt, user=user))

    # ── Billing (admin only) ──────────────────────────────────────────────────
    @fapp.get("/billing/collections", response_class=HTMLResponse)
    async def billing_collections(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_billing_page("collections", br, bt, user=user))

    @fapp.get("/billing/settlements", response_class=HTMLResponse)
    async def billing_settlements(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_billing_page("settlements", br, bt, user=user))

    # ── Communications (admin only) ───────────────────────────────────────────
    @fapp.get("/communications/email", response_class=HTMLResponse)
    async def communications_email(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_communications_email_page(br, bt, user=user))

    # ── Contacts (admin only) ─────────────────────────────────────────────────
    @fapp.get("/contacts", response_class=HTMLResponse)
    async def contacts(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_contacts_page(br, bt, user=user))

    @fapp.post("/api/contacts")
    async def contacts_create(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        if not _has_hub_access(session, "communications"):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        env = _env()
        body = await request.json()
        category = body.get("category", "gorilla")
        name     = (body.get("name") or "").strip()
        phone    = (body.get("phone") or "").strip()
        email    = (body.get("email") or "").strip()
        address  = (body.get("address") or "").strip()
        status   = body.get("status", "Not Contacted")
        if not name:
            return JSONResponse({"error": "name required"}, status_code=400)
        TABLE_MAP = {
            "attorney":  {"tid": T_ATT_VENUES, "name_f": "Law Firm Name",  "phone_f": "Phone Number", "addr_f": "Law Office Address", "email_f": "Email"},
            "gorilla":   {"tid": T_GOR_VENUES, "name_f": "Name",            "phone_f": "Phone",        "addr_f": "Address",            "email_f": "Email"},
            "community": {"tid": T_COM_VENUES, "name_f": "Name",            "phone_f": "Phone",        "addr_f": "Address",            "email_f": "Email"},
        }
        cfg = TABLE_MAP.get(category, TABLE_MAP["gorilla"])
        fields: dict = {
            cfg["name_f"]:    name,
            "Contact Status": {"value": status},
        }
        if phone:   fields[cfg["phone_f"]] = phone
        if email:   fields[cfg["email_f"]] = email
        if address: fields[cfg["addr_f"]]  = address
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{env['br']}/api/database/rows/table/{cfg['tid']}/?user_field_names=true",
                headers={"Authorization": f"Token {env['bt']}", "Content-Type": "application/json"},
                json=fields,
            )
        if r.status_code in (200, 201):
            return JSONResponse({"ok": True})
        return JSONResponse({"error": r.text}, status_code=r.status_code)

    # ── Guerilla Field Reports ─────────────────────────────────────────────────
    @fapp.post("/api/guerilla/log")
    async def guerilla_log(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
        env = _env()
        return await guerilla_api.guerilla_log(
            request, env["br"], env["bt"], session,
            bunny_zone=os.environ.get("BUNNY_STORAGE_ZONE", "techopssocialmedia"),
            bunny_key=os.environ.get("BUNNY_STORAGE_API_KEY", ""),
            bunny_cdn_base="https://techopssocialmedia.b-cdn.net",
        )


    # ── Massage Box CRUD ──────────────────────────────────────────────────────
    def _invalidate(*tids: int) -> None:
        for tid in tids:
            try:
                hub_cache.pop(f"table:{tid}", None)
            except Exception:
                pass

    @fapp.post("/api/guerilla/boxes")
    async def create_box(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
        env = _env()
        resp = await guerilla_api.create_box(request, env["br"], env["bt"], session)
        _invalidate(T_GOR_BOXES)
        return resp

    @fapp.patch("/api/guerilla/boxes/{box_id}/pickup")
    async def pickup_box(request: Request, box_id: int):
        session = _get_session(request)
        if not session:
            return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
        env = _env()
        resp = await guerilla_api.pickup_box(request, env["br"], env["bt"], session, box_id)
        _invalidate(T_GOR_BOXES)
        return resp

    @fapp.patch("/api/guerilla/venues/{venue_id}")
    async def update_venue(request: Request, venue_id: int):
        session = _get_session(request)
        if not session:
            return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
        resp = await guerilla_api.update_venue(request, _env()["br"], _env()["bt"], session, venue_id)
        _invalidate(T_GOR_VENUES)
        return resp

    @fapp.patch("/api/guerilla/boxes/{box_id}")
    async def update_box(request: Request, box_id: int):
        session = _get_session(request)
        if not session:
            return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
        env = _env()
        resp = await guerilla_api.update_box(request, env["br"], env["bt"], session, box_id)
        _invalidate(T_GOR_BOXES)
        return resp

    @fapp.patch("/api/guerilla/boxes/{box_id}/days")
    async def update_box_days(request: Request, box_id: int):
        session = _get_session(request)
        if not session:
            return JSONResponse({"ok": False, "error": "unauthenticated"}, status_code=401)
        env = _env()
        resp = await guerilla_api.update_box_days(request, env["br"], env["bt"], session, box_id)
        _invalidate(T_GOR_BOXES)
        return resp

    # ── Route API Endpoints ───────────────────────────────────────────────────
    async def _hub_cached_rows(tid: int) -> list:
        env = _env()
        return await _cached_table(tid, env["br"], env["bt"])

    @fapp.get("/api/guerilla/routes/today")
    async def routes_today(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        env = _env()
        return await guerilla_api.routes_today(request, env["br"], env["bt"], session,
                                               _hub_cached_rows)

    @fapp.patch("/api/guerilla/routes/stops/{stop_id}")
    async def update_route_stop(request: Request, stop_id: int):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        env = _env()
        resp = await guerilla_api.update_route_stop(request, env["br"], env["bt"], session, stop_id)
        _invalidate(T_GOR_ROUTE_STOPS)
        return resp

    @fapp.post("/api/guerilla/routes")
    async def gorilla_routes_create(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        env = _env()
        resp = await guerilla_api.gorilla_routes_create(request, env["br"], env["bt"], session)
        _invalidate(T_GOR_ROUTES, T_GOR_ROUTE_STOPS)
        return resp

    @fapp.patch("/api/guerilla/routes/{route_id}/status")
    async def gorilla_route_status(request: Request, route_id: int):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        env = _env()
        resp = await guerilla_api.gorilla_route_status(request, env["br"], env["bt"], session, route_id)
        _invalidate(T_GOR_ROUTES)
        return resp

    @fapp.patch("/api/guerilla/routes/{route_id}")
    async def gorilla_route_update(request: Request, route_id: int):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        env = _env()
        resp = await guerilla_api.gorilla_route_update(request, env["br"], env["bt"], session,
                                                       route_id, _hub_cached_rows)
        _invalidate(T_GOR_ROUTES, T_GOR_ROUTE_STOPS)
        return resp

    @fapp.delete("/api/guerilla/routes/{route_id}")
    async def gorilla_route_delete(request: Request, route_id: int):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        env = _env()
        resp = await guerilla_api.gorilla_route_delete(request, env["br"], env["bt"], session,
                                                       route_id, _hub_cached_rows)
        _invalidate(T_GOR_ROUTES, T_GOR_ROUTE_STOPS)
        return resp

    # ── Social Poster Hub ──────────────────────────────────────────────────────
    @fapp.get("/social/poster", response_class=HTMLResponse)
    async def social_poster(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        if not _has_hub_access(user, "social"):
            return HTMLResponse(_forbidden_page(br, bt, user=user), status_code=403)
        return HTMLResponse(_social_poster_hub_page(br, bt, user=user))

    @fapp.get("/api/social/queue")
    async def social_queue(request: Request):
        if not _ok(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        user = _get_user(request)
        if not _has_social_access(user):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        zone = os.environ.get("BUNNY_STORAGE_ZONE", "")
        key  = os.environ.get("BUNNY_STORAGE_API_KEY", "")
        if not zone or not key:
            return JSONResponse({"error": "bunny not configured"}, status_code=500)
        import asyncio
        base = f"https://la.storage.bunnycdn.com/{zone}"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{base}/Scheduled/",
                headers={"AccessKey": key, "Accept": "application/json"})
            if not r.is_success:
                return JSONResponse([], status_code=200)
            files = [f for f in r.json() if (f.get("ObjectName") or "").endswith(".meta.json")]
            async def fetch_meta(f):
                mr = await client.get(f"{base}/Scheduled/{f['ObjectName']}",
                    headers={"AccessKey": key})
                if mr.is_success:
                    try: return mr.json()
                    except: return None
                return None
            metas = await asyncio.gather(*[fetch_meta(f) for f in files])
        return JSONResponse([m for m in metas if m])

    @fapp.get("/api/social/posted")
    async def social_posted(request: Request):
        if not _ok(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        user = _get_user(request)
        if not _has_social_access(user):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        zone = os.environ.get("BUNNY_STORAGE_ZONE", "")
        key  = os.environ.get("BUNNY_STORAGE_API_KEY", "")
        if not zone or not key:
            return JSONResponse({"error": "bunny not configured"}, status_code=500)
        import asyncio
        base = f"https://la.storage.bunnycdn.com/{zone}"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{base}/Posted/",
                headers={"AccessKey": key, "Accept": "application/json"})
            if not r.is_success:
                return JSONResponse([], status_code=200)
            files = [f for f in r.json() if (f.get("ObjectName") or "").endswith(".meta.json")]
            files.sort(key=lambda f: f.get("LastChanged", ""), reverse=True)
            files = files[:30]
            async def fetch_meta(f):
                mr = await client.get(f"{base}/Posted/{f['ObjectName']}",
                    headers={"AccessKey": key})
                if mr.is_success:
                    try: return mr.json()
                    except: return None
                return None
            metas = await asyncio.gather(*[fetch_meta(f) for f in files])
        return JSONResponse([m for m in metas if m])

    # ── Coming soon ────────────────────────────────────────────────────────────

    @fapp.get("/social", response_class=HTMLResponse)
    async def social(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_social_schedule_page(br, bt, user=user))

    @fapp.get("/social/history", response_class=HTMLResponse)
    async def social_history(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_coming_soon_page("social_history", "Social Media History", br, bt, user=user))

    @fapp.get("/calendar", response_class=HTMLResponse)
    async def calendar(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        return HTMLResponse(_calendar_page(br, bt, user=user))

    # ── Mobile pages (/m) ─────���──────────────────────��────────────────────────
    @fapp.get("/m", response_class=HTMLResponse)
    async def mobile_home(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        return HTMLResponse(_mobile_home_page(br, bt, user=user))

    @fapp.get("/m/log")
    async def mobile_log(request: Request):
        return RedirectResponse(url="/m/map", status_code=302)

    @fapp.get("/m/map", response_class=HTMLResponse)
    async def mobile_map(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user):
            return RedirectResponse(url="/m/route", status_code=302)
        return HTMLResponse(_mobile_map_page(br, bt, user=user))

    @fapp.get("/m/routes", response_class=HTMLResponse)
    async def mobile_routes_dashboard(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        return HTMLResponse(_mobile_routes_dashboard_page(br, bt, user=user))

    @fapp.get("/m/lead", response_class=HTMLResponse)
    async def mobile_lead_capture(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        return HTMLResponse(_mobile_lead_capture_page(br, bt, user=user))

    @fapp.get("/m/route", response_class=HTMLResponse)
    async def mobile_route(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        return HTMLResponse(_mobile_route_page(br, bt, user=user))

    @fapp.get("/m/recent", response_class=HTMLResponse)
    async def mobile_recent(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        return HTMLResponse(_mobile_recent_page(br, bt, user=user))

    # ── Events & Leads ─────────────────────────────────────────────────────────

    @fapp.get("/events/{event_id}", response_class=HTMLResponse)
    async def event_detail(request: Request, event_id: int):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_event_detail_page(event_id, br, bt, user=user))

    @fapp.get("/leads", response_class=HTMLResponse)
    async def leads_hub(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        if not _is_admin(user): return RedirectResponse(url="/m")
        return HTMLResponse(_leads_dashboard_page(br, bt, user=user))

    @fapp.get("/form/{slug}", response_class=HTMLResponse)
    async def public_lead_form(slug: str):
        """Public lead capture form — no auth required."""
        if not T_EVENTS:
            return HTMLResponse("<h1>Not configured</h1>", status_code=503)
        env = _env()
        events = await _cached_table(T_EVENTS, env["br"], env["bt"])
        event = next((e for e in events if e.get("Form Slug") == slug), None)
        if not event:
            return HTMLResponse("<h1>Form not found</h1>", status_code=404)
        name = event.get("Name") or "Reform Chiropractic Event"
        return HTMLResponse(_lead_form_page(name, slug))

    @fapp.post("/api/leads")
    async def create_lead(request: Request):
        """Public endpoint — no auth required. Creates a lead from the form."""
        if not T_EVENTS or not T_LEADS:
            return JSONResponse({"ok": False, "error": "not configured"}, status_code=503)
        body = await request.json()
        slug = (body.get("slug") or "").strip()
        name = (body.get("name") or "").strip()
        phone = (body.get("phone") or "").strip()
        email = (body.get("email") or "").strip()
        reason = (body.get("reason") or "").strip()
        if not name or not phone:
            return JSONResponse({"ok": False, "error": "name and phone required"}, status_code=400)
        env = _env()
        br, bt = env["br"], env["bt"]
        # Find event by slug
        events = await _cached_table(T_EVENTS, br, bt)
        event = next((e for e in events if e.get("Form Slug") == slug), None)
        if not event:
            return JSONResponse({"ok": False, "error": "event not found"}, status_code=404)
        fields = {
            "Name": name,
            "Phone": phone,
            "Status": {"value": "New"},
            "Source": event.get("Name") or slug,
            "Event": [{"id": event["id"]}],
        }
        if email: fields["Email"] = email
        if reason: fields["Reason"] = reason
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{br}/api/database/rows/table/{T_LEADS}/?user_field_names=true",
                headers={"Authorization": f"Token {bt}", "Content-Type": "application/json"},
                json=fields,
            )
            # Update lead count on event
            cur_count = event.get("Lead Count") or 0
            await client.patch(
                f"{br}/api/database/rows/table/{T_EVENTS}/{event['id']}/?user_field_names=true",
                headers={"Authorization": f"Token {bt}", "Content-Type": "application/json"},
                json={"Lead Count": cur_count + 1},
            )
        if r.status_code in (200, 201):
            try:
                hub_cache.pop(f"table:{T_LEADS}")
                hub_cache.pop(f"table:{T_EVENTS}")
            except Exception:
                pass
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "error": r.text[:200]}, status_code=500)

    @fapp.post("/api/leads/capture")
    async def capture_lead(request: Request):
        """Authenticated endpoint for field reps to capture leads."""
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        if not T_LEADS:
            return JSONResponse({"ok": False, "error": "not configured"}, status_code=503)
        body = await request.json()
        name = (body.get("name") or "").strip()
        phone = (body.get("phone") or "").strip()
        email = (body.get("email") or "").strip()
        service = (body.get("service") or "").strip()
        event_id = body.get("event_id")
        notes = (body.get("notes") or "").strip()
        if not name or not phone:
            return JSONResponse({"ok": False, "error": "name and phone required"}, status_code=400)
        env = _env()
        br, bt = env["br"], env["bt"]
        # Build source string
        source = "Field Capture"
        if event_id and T_EVENTS:
            events = await _cached_table(T_EVENTS, br, bt)
            event = next((e for e in events if e.get("id") == int(event_id)), None)
            if event:
                source = event.get("Name") or "Event"
        fields = {
            "Name": name,
            "Phone": phone,
            "Status": "New",
            "Source": source,
            "Reason": service,
        }
        if email:
            fields["Email"] = email
        if notes:
            fields["Notes"] = f"[{session.get('email','')}] {notes}"
        if event_id and T_EVENTS:
            fields["Event"] = [int(event_id)]
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{br}/api/database/rows/table/{T_LEADS}/?user_field_names=true",
                headers={"Authorization": f"Token {bt}", "Content-Type": "application/json"},
                json=fields,
            )
            # Update event lead count if linked
            if event_id and T_EVENTS and event:
                cur_count = event.get("Lead Count") or 0
                await client.patch(
                    f"{br}/api/database/rows/table/{T_EVENTS}/{event['id']}/?user_field_names=true",
                    headers={"Authorization": f"Token {bt}", "Content-Type": "application/json"},
                    json={"Lead Count": cur_count + 1},
                )
        hub_cache.pop(f"table:{T_LEADS}", None)
        hub_cache.pop(f"table:{T_EVENTS}", None)
        if r.status_code in (200, 201):
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "error": r.text[:200]}, status_code=500)

    @fapp.patch("/api/leads/{lead_id}")
    async def update_lead(request: Request, lead_id: int):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        body = await request.json()
        env = _env()
        from datetime import date as _date
        fields = {}
        if "status" in body:
            fields["Status"] = {"value": body["status"]}
            if body["status"] == "Contacted":
                fields["Contacted At"] = _date.today().isoformat()
                fields["Contacted By"] = session.get("email", "")
        if "notes" in body:
            fields["Notes"] = body["notes"]
        async with httpx.AsyncClient(timeout=30) as client:
            await client.patch(
                f"{env['br']}/api/database/rows/table/{T_LEADS}/{lead_id}/?user_field_names=true",
                headers={"Authorization": f"Token {env['bt']}", "Content-Type": "application/json"},
                json=fields,
            )
        try:
            hub_cache.pop(f"table:{T_LEADS}")
        except Exception:
            pass
        return JSONResponse({"ok": True})

    @fapp.post("/api/leads/bulk-contact")
    async def bulk_contact_leads(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        body = await request.json()
        ids = body.get("ids", [])
        env = _env()
        from datetime import date as _date
        today = _date.today().isoformat()
        email = session.get("email", "")
        async with httpx.AsyncClient(timeout=60) as client:
            for lid in ids:
                await client.patch(
                    f"{env['br']}/api/database/rows/table/{T_LEADS}/{lid}/?user_field_names=true",
                    headers={"Authorization": f"Token {env['bt']}", "Content-Type": "application/json"},
                    json={"Status": {"value": "Contacted"}, "Contacted At": today, "Contacted By": email},
                )
        try:
            hub_cache.pop(f"table:{T_LEADS}")
        except Exception:
            pass
        return JSONResponse({"ok": True})

    @fapp.patch("/api/events/{event_id}/status")
    async def update_event_status(request: Request, event_id: int):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        body = await request.json()
        status = body.get("status", "")
        if status not in ("Prospective", "Approved", "Scheduled", "Completed"):
            return JSONResponse({"error": "invalid status"}, status_code=400)
        env = _env()
        async with httpx.AsyncClient(timeout=30) as client:
            await client.patch(
                f"{env['br']}/api/database/rows/table/{T_EVENTS}/{event_id}/?user_field_names=true",
                headers={"Authorization": f"Token {env['bt']}", "Content-Type": "application/json"},
                json={"Event Status": {"value": status}},
            )
        try:
            hub_cache.pop(f"table:{T_EVENTS}")
        except Exception:
            pass
        return JSONResponse({"ok": True})

    @fapp.patch("/api/events/{event_id}/checkin")
    async def event_checkin(request: Request, event_id: int):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        env = _env()
        async with httpx.AsyncClient(timeout=30) as client:
            await client.patch(
                f"{env['br']}/api/database/rows/table/{T_EVENTS}/{event_id}/?user_field_names=true",
                headers={"Authorization": f"Token {env['bt']}", "Content-Type": "application/json"},
                json={"Checked In": True},
            )
        try:
            hub_cache.pop(f"table:{T_EVENTS}")
        except Exception:
            pass
        return JSONResponse({"ok": True})

    return fapp


# ──────────────────────────────────────────────────────────────────────────────
# LOCAL DEV  —  python execution/modal_outreach_hub.py
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import httpx
    import uvicorn
    from pathlib import Path
    from dotenv import load_dotenv
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

    load_dotenv(Path(__file__).parent.parent / ".env")

    local_app = FastAPI()

    def _env():
        return {
            "br":     os.getenv("BASEROW_URL",        "https://baserow.reformchiropractic.app"),
            "bt":     os.getenv("BASEROW_API_TOKEN",  ""),
            "gid":    os.getenv("GOOGLE_CLIENT_ID",   ""),
            "gsec":   os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "domain": os.getenv("ALLOWED_DOMAIN",     ""),
        }

    def _redirect_uri(request: Request) -> str:
        host = request.headers.get("host", "localhost:8000")
        if "localhost" in host or "127.0.0.1" in host:
            return f"http://{host}/auth/google/callback"
        return "https://hub.reformchiropractic.app/auth/google/callback"

    async def _refresh_if_needed(sid: str, session: dict, env: dict) -> str:
        if time.time() < session.get("expires_at", 0) - 60:
            return session["access_token"]
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
        session["expires_at"] = time.time() + data.get("expires_in", 3600)
        hub_sessions[sid] = session
        return session["access_token"]

    def _guard(request):
        session = _get_session(request)
        if not session:
            return None, None, None
        env = _env()
        return session, env["br"], env["bt"]

    # ── Login / OAuth ──────────────────────────────────────────────────────────
    @local_app.get("/login", response_class=HTMLResponse)
    async def _login_get(request: Request, error: str = ""):
        if _ok(request):
            return RedirectResponse(url="/")
        return HTMLResponse(_login_page(error))

    @local_app.get("/auth/google", response_class=HTMLResponse)
    async def _auth_google(request: Request):
        env = _env()
        state = secrets.token_urlsafe(32)
        hub_oauth_states[state] = time.time()
        params = urlencode({
            "client_id":     env["gid"],
            "redirect_uri":  _redirect_uri(request),
            "response_type": "code",
            "scope":         "openid email profile https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly",
            "access_type":   "offline",
            "prompt":        "consent",
            "state":         state,
        })
        google_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
        return HTMLResponse(
            f'<html><head></head><body>'
            f'<script>window.location.href={repr(google_url)};</script>'
            f'<noscript><meta http-equiv="refresh" content="0;url={google_url}"></noscript>'
            f'</body></html>'
        )

    @local_app.get("/auth/google/callback")
    async def _auth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        if error or not code:
            return RedirectResponse("/login?error=1")
        stored_time = hub_oauth_states.get(state)
        if not stored_time or (time.time() - stored_time) > 300:
            return RedirectResponse("/login?error=1")
        del hub_oauth_states[state]

        env = _env()
        async with httpx.AsyncClient() as client:
            token_resp = await client.post("https://oauth2.googleapis.com/token", data={
                "code":          code,
                "client_id":     env["gid"],
                "client_secret": env["gsec"],
                "redirect_uri":  _redirect_uri(request),
                "grant_type":    "authorization_code",
            })
            tokens = token_resp.json()
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {tokens.get('access_token','')}"}
            )
            user = userinfo_resp.json()

        email = user.get("email", "")
        allowed = env["domain"]
        if allowed and not email.endswith(f"@{allowed}"):
            return RedirectResponse("/login?error=domain")

        sid = secrets.token_urlsafe(32)
        hub_sessions[sid] = {
            "email":         email,
            "name":          user.get("name", email),
            "picture":       user.get("picture", ""),
            "access_token":  tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token", ""),
            "expires_at":    time.time() + tokens.get("expires_in", 3600),
        }
        resp = HTMLResponse('<html><head><meta http-equiv="refresh" content="0;url=/"></head></html>')
        resp.set_cookie(SESSION_COOKIE, sid, httponly=True, max_age=86400 * 7, samesite="lax")
        return resp

    @local_app.get("/logout")
    async def _logout(request: Request):
        sid = request.cookies.get(SESSION_COOKIE)
        if sid:
            try:
                del hub_sessions[sid]
            except KeyError:
                pass
        resp = HTMLResponse('<html><head><meta http-equiv="refresh" content="0;url=/login"></head></html>')
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    # ── Gmail API ──────────────────────────────────────────────────────────────
    @local_app.post("/api/gmail/send")
    async def _gmail_send(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        body = await request.json()
        to = body.get("to", "")
        subject = body.get("subject", "")
        text = body.get("body", "")
        if not to or not subject or not text:
            return JSONResponse({"error": "missing fields"}, status_code=400)
        env = _env()
        sid = request.cookies.get(SESSION_COOKIE, "")
        token = await _refresh_if_needed(sid, session, env)
        import base64, email as emaillib
        msg = emaillib.message.EmailMessage()
        msg["From"] = session["email"]
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {token}"},
                json={"raw": raw},
            )
        return JSONResponse(r.json(), status_code=r.status_code)

    @local_app.get("/api/gmail/threads")
    async def _gmail_threads(request: Request, contact_email: str = ""):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        if not contact_email:
            return JSONResponse({"error": "contact_email required"}, status_code=400)
        env = _env()
        sid = request.cookies.get(SESSION_COOKIE, "")
        token = await _refresh_if_needed(sid, session, env)
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/threads",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": f"from:{contact_email} OR to:{contact_email}", "maxResults": 20},
            )
            meta = r.json().get("threads", [])
            threads = []
            for t in meta[:10]:
                tr = await client.get(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{t['id']}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"format": "metadata", "metadataHeaders": ["Subject", "From", "To", "Date"]},
                )
                threads.append(tr.json())
        return JSONResponse({"threads": threads})

    @local_app.get("/api/data/{tid}")
    async def _table_data(tid: int, request: Request):
        if not _ok(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        env = _env()
        rows = await _cached_table(tid, env["br"], env["bt"])
        return JSONResponse(rows)

    @local_app.post("/api/contacts")
    async def _contacts_create(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        env = _env()
        body = await request.json()
        category = body.get("category", "gorilla")
        name     = (body.get("name") or "").strip()
        phone    = (body.get("phone") or "").strip()
        address  = (body.get("address") or "").strip()
        status   = body.get("status", "Not Contacted")
        if not name:
            return JSONResponse({"error": "name required"}, status_code=400)
        TABLE_MAP = {
            "attorney":  {"tid": T_ATT_VENUES, "name_f": "Law Firm Name",  "phone_f": "Phone Number", "addr_f": "Law Office Address"},
            "gorilla":   {"tid": T_GOR_VENUES, "name_f": "Name",            "phone_f": "Phone",        "addr_f": "Address"},
            "community": {"tid": T_COM_VENUES, "name_f": "Name",            "phone_f": "Phone",        "addr_f": "Address"},
        }
        cfg = TABLE_MAP.get(category, TABLE_MAP["gorilla"])
        fields: dict = {
            cfg["name_f"]:    name,
            "Contact Status": {"value": status},
        }
        if phone:   fields[cfg["phone_f"]] = phone
        if address: fields[cfg["addr_f"]]  = address
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{env['br']}/api/database/rows/table/{cfg['tid']}/?user_field_names=true",
                headers={"Authorization": f"Token {env['bt']}", "Content-Type": "application/json"},
                json=fields,
            )
        if r.status_code in (200, 201):
            return JSONResponse({"ok": True})
        return JSONResponse({"error": r.text}, status_code=r.status_code)

    @local_app.get("/api/geocode")
    async def _geocode(request: Request, lat: float = 0.0, lng: float = 0.0):
        if not _ok(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if not lat or not lng:
            return JSONResponse({"error": "lat/lng required"}, status_code=400)
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    "https://nominatim.openstreetmap.org/reverse",
                    params={"lat": lat, "lon": lng, "format": "json"},
                    headers={"User-Agent": "ReformHub/1.0 (reformchiropractic.com)"},
                )
                d = r.json()
            a = d.get("address", {})
            parts = []
            num  = a.get("house_number", "")
            road = a.get("road", "")
            if num and road:
                parts.append(f"{num} {road}")
            elif road:
                parts.append(road)
            city = a.get("city") or a.get("town") or a.get("village") or ""
            if city:  parts.append(city)
            if a.get("state"):    parts.append(a["state"])
            if a.get("postcode"): parts.append(a["postcode"])
            addr = ", ".join(parts) if parts else d.get("display_name", "")
            return JSONResponse({"address": addr})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @local_app.get("/api/guerilla/routes/today")
    async def _gorilla_routes_today(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        if not T_GOR_ROUTES or not T_GOR_ROUTE_STOPS:
            return JSONResponse({"route": None, "stops": []})
        env = _env()
        user_email = session.get("email", "")
        import datetime
        today = datetime.date.today().isoformat()
        try:
            routes = await _cached_table(T_GOR_ROUTES, env["br"], env["bt"])
            # Find active route for today assigned to this user
            route = None
            for row in routes:
                row_date  = (row.get("Date") or "")[:10]
                row_email = (row.get("Assigned To") or "").strip().lower()
                row_status = row.get("Status") or ""
                if isinstance(row_status, dict): row_status = row_status.get("value", "")
                if row_date == today and row_email == user_email.lower() and row_status in ("Active", "Draft"):
                    route = row
                    break
            if not route:
                return JSONResponse({"route": None, "stops": []})
            route_id = route.get("id")
            stops_all = await _cached_table(T_GOR_ROUTE_STOPS, env["br"], env["bt"])
            # Filter stops for this route, sorted by Stop Order
            stops = [s for s in stops_all if any(
                (isinstance(v, dict) and v.get("id") == route_id) or v == route_id
                for v in (s.get("Route") or [])
            )]
            stops.sort(key=lambda s: s.get("Stop Order") or 999)
            # Enrich with venue lat/lng
            venues = await _cached_table(T_GOR_VENUES, env["br"], env["bt"])
            venue_map = {v["id"]: v for v in venues}
            stop_list = []
            for s in stops:
                venue_id = None
                for v in (s.get("Venue") or []):
                    if isinstance(v, dict): venue_id = v.get("id"); break
                    venue_id = v; break
                venue = venue_map.get(venue_id, {}) if venue_id else {}
                status = s.get("Status") or ""
                if isinstance(status, dict): status = status.get("value", "Pending")
                stop_list.append({
                    "stop_id":  s.get("id"),
                    "name":     venue.get("Name") or "",
                    "address":  venue.get("Address") or "",
                    "lat":      venue.get("Latitude"),
                    "lng":      venue.get("Longitude"),
                    "status":   status or "Pending",
                    "order":    s.get("Stop Order") or 0,
                    "notes":    s.get("Notes") or "",
                })
            route_status = route.get("Status") or ""
            if isinstance(route_status, dict): route_status = route_status.get("value", "")
            return JSONResponse({
                "route": {"id": route_id, "name": route.get("Route Name") or "Route", "status": route_status},
                "stops": stop_list,
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @local_app.patch("/api/guerilla/routes/stops/{stop_id}")
    async def _gorilla_route_stop_patch(stop_id: int, request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        if not T_GOR_ROUTE_STOPS:
            return JSONResponse({"error": "routes not configured"}, status_code=503)
        env = _env()
        body = await request.json()
        new_status = body.get("status", "")
        if new_status not in ("Pending", "Visited", "Skipped"):
            return JSONResponse({"error": "invalid status"}, status_code=400)
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{env['br']}/api/database/rows/table/{T_GOR_ROUTE_STOPS}/{stop_id}/?user_field_names=true",
                headers={"Authorization": f"Token {env['bt']}", "Content-Type": "application/json"},
                json={"Status": {"value": new_status}},
            )
        # Bust cache so next fetch reflects the update
        try: del hub_cache[f"table:{T_GOR_ROUTE_STOPS}"]
        except Exception: pass
        if r.status_code in (200, 201):
            return JSONResponse({"ok": True})
        return JSONResponse({"error": r.text}, status_code=r.status_code)

    @local_app.post("/api/guerilla/routes")
    async def _gorilla_routes_create(request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        if not T_GOR_ROUTES or not T_GOR_ROUTE_STOPS:
            return JSONResponse({"error": "routes not configured"}, status_code=503)
        env = _env()
        body = await request.json()
        name     = (body.get("name") or "").strip()
        date_str = (body.get("date") or "").strip()
        assignee = (body.get("assigned_to") or "").strip()
        status   = body.get("status") or "Draft"
        stops    = body.get("stops") or []  # [{venue_id}]
        if not name:
            return JSONResponse({"error": "name required"}, status_code=400)
        if status not in ("Draft", "Active", "Completed"):
            status = "Draft"
        async with httpx.AsyncClient() as client:
            # Create route record
            route_payload = {"Name": name, "Assigned To": assignee, "Status": {"value": status}}
            if date_str:
                route_payload["Date"] = date_str
            r = await client.post(
                f"{env['br']}/api/database/rows/table/{T_GOR_ROUTES}/?user_field_names=true",
                headers={"Authorization": f"Token {env['bt']}", "Content-Type": "application/json"},
                json=route_payload,
            )
            if r.status_code not in (200, 201):
                return JSONResponse({"error": r.text}, status_code=r.status_code)
            route_id = r.json()["id"]
            # Create stop records
            for i, stop in enumerate(stops):
                venue_id = stop.get("venue_id")
                if not venue_id:
                    continue
                stop_payload = {
                    "Route":      [{"id": route_id}],
                    "Venue":      [{"id": venue_id}],
                    "Stop Order": i + 1,
                    "Status":     {"value": "Pending"},
                }
                await client.post(
                    f"{env['br']}/api/database/rows/table/{T_GOR_ROUTE_STOPS}/?user_field_names=true",
                    headers={"Authorization": f"Token {env['bt']}", "Content-Type": "application/json"},
                    json=stop_payload,
                )
        try: del hub_cache[f"table:{T_GOR_ROUTES}"]
        except Exception: pass
        try: del hub_cache[f"table:{T_GOR_ROUTE_STOPS}"]
        except Exception: pass
        return JSONResponse({"ok": True, "route_id": route_id})

    @local_app.patch("/api/guerilla/routes/{route_id}/status")
    async def _gorilla_route_status_patch(route_id: int, request: Request):
        session = _get_session(request)
        if not session:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        if not T_GOR_ROUTES:
            return JSONResponse({"error": "routes not configured"}, status_code=503)
        env = _env()
        body = await request.json()
        new_status = body.get("status", "")
        if new_status not in ("Draft", "Active", "Completed"):
            return JSONResponse({"error": "invalid status"}, status_code=400)
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{env['br']}/api/database/rows/table/{T_GOR_ROUTES}/{route_id}/?user_field_names=true",
                headers={"Authorization": f"Token {env['bt']}", "Content-Type": "application/json"},
                json={"Status": {"value": new_status}},
            )
        try: del hub_cache[f"table:{T_GOR_ROUTES}"]
        except Exception: pass
        if r.status_code in (200, 201):
            return JSONResponse({"ok": True})
        return JSONResponse({"error": r.text}, status_code=r.status_code)

    @local_app.patch("/api/guerilla/routes/{route_id}")
    async def _gorilla_route_update(route_id: int, request: Request):
        return await gorilla_route_update(request, route_id)

    @local_app.delete("/api/guerilla/routes/{route_id}")
    async def _gorilla_route_delete(route_id: int, request: Request):
        return await gorilla_route_delete(request, route_id)

    # ── Mobile detection for root route ───────────────────────────────────────
    def _is_mobile_local(request):
        ua = (request.headers.get("user-agent") or "").lower()
        return any(k in ua for k in ("iphone", "android", "mobile", "ipod"))

    async def _root_handler(request: Request):
        user, br, bt = _guard(request)
        if not user: return RedirectResponse(url="/login")
        return HTMLResponse(_hub_page(br, bt, user=user))
    local_app.add_api_route("/", _root_handler, methods=["GET"])

    # ── Pages ──────────────────────────────────────────────────────────────────
    for route, fn in [
        ("/attorney",            lambda r, u, br, bt: _tool_page("attorney",  br, bt, user=u)),
        ("/guerilla",             lambda r, u, br, bt: _tool_page("gorilla",   br, bt, user=u)),
        ("/community",           lambda r, u, br, bt: _tool_page("community", br, bt, user=u)),
        ("/attorney/map",        lambda r, u, br, bt: _map_page("attorney",   br, bt, user=u)),
        ("/guerilla/map",         lambda r, u, br, bt: _map_page("gorilla",    br, bt, user=u)),
        ("/community/map",       lambda r, u, br, bt: _map_page("community",  br, bt, user=u)),
        ("/m",             lambda r, u, br, bt: _mobile_home_page(br, bt, user=u)),
        ("/m/map",         lambda r, u, br, bt: _mobile_map_page(br, bt, user=u)),
        ("/m/routes",      lambda r, u, br, bt: _mobile_routes_dashboard_page(br, bt, user=u)),
        ("/m/lead",        lambda r, u, br, bt: _mobile_lead_capture_page(br, bt, user=u)),
        ("/m/route",       lambda r, u, br, bt: _mobile_route_page(br, bt, user=u)),
        ("/m/recent",      lambda r, u, br, bt: _mobile_recent_page(br, bt, user=u)),
        ("/guerilla/events/internal",  lambda r, u, br, bt: _gorilla_events_internal_page(br, bt, user=u)),
        ("/guerilla/events/external",  lambda r, u, br, bt: _gorilla_events_external_page(br, bt, user=u)),
        ("/guerilla/businesses",       lambda r, u, br, bt: _gorilla_businesses_page(br, bt, user=u)),
        ("/guerilla/boxes",            lambda r, u, br, bt: _gorilla_boxes_page(br, bt, user=u)),
        ("/guerilla/routes",           lambda r, u, br, bt: _gorilla_routes_page(br, bt, user=u)),
        ("/guerilla/routes/new",       lambda r, u, br, bt: _gorilla_routes_new_page(br, bt, user=u)),
        ("/outreach/contacts",   lambda r, u, br, bt: _unified_directory_page(br, bt, user=u)),
        ("/attorney/directory",  lambda r, u, br, bt: _directory_page("attorney",  br, bt, user=u)),
        ("/guerilla/directory",   lambda r, u, br, bt: _directory_page("gorilla",   br, bt, user=u)),
        ("/community/directory", lambda r, u, br, bt: _directory_page("community", br, bt, user=u)),
        ("/patients",            lambda r, u, br, bt: _patients_page(br, bt, user=u)),
        ("/firms",               lambda r, u, br, bt: _firms_page(br, bt, user=u)),
        ("/billing/collections", lambda r, u, br, bt: _billing_page("collections", br, bt, user=u)),
        ("/billing/settlements", lambda r, u, br, bt: _billing_page("settlements", br, bt, user=u)),
        ("/communications/email", lambda r, u, br, bt: _communications_email_page(br, bt, user=u)),
        ("/contacts",            lambda r, u, br, bt: _contacts_page(br, bt, user=u)),
        ("/social/poster",       lambda r, u, br, bt: _social_poster_hub_page(br, bt, user=u)),
        ("/social",              lambda r, u, br, bt: _social_schedule_page(br, bt, user=u)),
        ("/social/history",      lambda r, u, br, bt: _coming_soon_page("social_history", "Social Media History", br, bt, user=u)),
        ("/calendar",            lambda r, u, br, bt: _calendar_page(br, bt, user=u)),
    ]:
        def make_handler(f):
            async def handler(request: Request):
                user, br, bt = _guard(request)
                if not user: return RedirectResponse(url="/login")
                return HTMLResponse(f(request, user, br, bt))
            return handler
        local_app.add_api_route(route, make_handler(fn), methods=["GET"])

    # patients sub-routes need stage arg — add separately
    for route, stage in [("/patients/active","active"),("/patients/billed","billed"),("/patients/awaiting","awaiting"),("/patients/closed","closed")]:
        def make_stage_handler(s):
            async def handler(request: Request):
                user, br, bt = _guard(request)
                if not user: return RedirectResponse(url="/login")
                return HTMLResponse(_patients_page(br, bt, s, user=user))
            return handler
        local_app.add_api_route(route, make_stage_handler(stage), methods=["GET"])

    print("Hub running at http://localhost:8000/login")
    uvicorn.run(local_app, host="0.0.0.0", port=8000)
