"""Kiosk mode + consent submission backend.

A "kiosk session" lets an authenticated rep hand a device to the public so
leads can self-fill a capture form and walk through the consent forms the
rep selected. Sessions live in Redis (12h TTL) and are keyed by a random
URL-safe token; the public /kiosk/run/{kiosk_id} URL contains the token.

This module is pure logic (no FastAPI router); thin endpoint wrappers in
field_rep/routes/api.py call into here.
"""

import base64
import json
import os
import secrets
import time
from typing import Any
from urllib.parse import quote

import httpx

from . import storage


_BUNNY_ZONE = os.environ.get("BUNNY_STORAGE_ZONE", "techopssocialmedia")
_BUNNY_KEY  = os.environ.get("BUNNY_STORAGE_API_KEY", "")
_BUNNY_BASE = os.environ.get("BUNNY_CDN_BASE", "https://techopssocialmedia.b-cdn.net")


def new_kiosk_id() -> str:
    """22-char URL-safe token. Not crypto-strict; hard to guess."""
    return secrets.token_urlsafe(16)


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ─── Kiosk lifecycle ────────────────────────────────────────────────────────

async def start_kiosk(
    *,
    event_id: int,
    event_name: str,
    consent_slugs: list[str],
    pin: str,
    created_by: str,
) -> dict:
    """Create a new kiosk session and return {kiosk_id, ...}.

    `pin` must be 4-6 digits; we strip non-digits before storing.
    """
    digits = "".join(c for c in str(pin or "") if c.isdigit())
    if not (4 <= len(digits) <= 6):
        raise ValueError("PIN must be 4-6 digits")
    kid = new_kiosk_id()
    payload = {
        "event_id": int(event_id),
        "event_name": event_name or f"Event {event_id}",
        "consent_slugs": [s for s in (consent_slugs or []) if isinstance(s, str)],
        "pin": digits,
        "created_by": created_by,
        "created_at": _utc_iso(),
        "active": True,
    }
    await storage.put_kiosk_session(kid, payload)
    public = {k: v for k, v in payload.items() if k != "pin"}
    public["kiosk_id"] = kid
    return public


async def exit_kiosk(kiosk_id: str, pin: str) -> bool:
    """Validate PIN; on success delete the session and return True."""
    sess = await storage.get_kiosk_session(kiosk_id)
    if not sess:
        return False
    digits = "".join(c for c in str(pin or "") if c.isdigit())
    if digits != sess.get("pin"):
        return False
    await storage.del_kiosk_session(kiosk_id)
    return True


async def get_public_kiosk(kiosk_id: str) -> dict | None:
    """Return kiosk session metadata sans PIN. None if not found."""
    sess = await storage.get_kiosk_session(kiosk_id)
    if not sess:
        return None
    return {
        "kiosk_id": kiosk_id,
        "event_id": sess.get("event_id"),
        "event_name": sess.get("event_name"),
        "consent_slugs": sess.get("consent_slugs") or [],
        "active": bool(sess.get("active", True)),
    }


# ─── Bunny upload (signature PNG) ───────────────────────────────────────────

async def _upload_signature_png(
    *,
    client: httpx.AsyncClient,
    png_bytes: bytes,
    lead_id: int,
    slug: str,
) -> str | None:
    """PUT png_bytes to Bunny under Routes/consents/{lead_id}/{slug}_{ts}.png.

    Returns the public CDN URL on success, or None on failure. The LA region
    storage endpoint is required (see CLAUDE.md memory)."""
    if not (_BUNNY_KEY and _BUNNY_ZONE):
        return None
    safe_slug = "".join(c for c in slug if c.isalnum() or c in ("_", "-"))
    ts = int(time.time())
    path = f"Routes/consents/{int(lead_id)}/{safe_slug}_{ts}.png"
    upload_url = f"https://la.storage.bunnycdn.com/{_BUNNY_ZONE}/{quote(path)}"
    r = await client.put(
        upload_url,
        content=png_bytes,
        headers={"AccessKey": _BUNNY_KEY, "Content-Type": "image/png"},
    )
    if r.status_code in (200, 201):
        return f"{_BUNNY_BASE}/{path}"
    return None


def _decode_data_url(data_url: str) -> bytes | None:
    """Pull the b64 payload out of a `data:image/png;base64,...` URL."""
    if not data_url or not isinstance(data_url, str):
        return None
    marker = "base64,"
    idx = data_url.find(marker)
    if idx < 0:
        return None
    try:
        return base64.b64decode(data_url[idx + len(marker):])
    except Exception:
        return None


# ─── Consent submission ─────────────────────────────────────────────────────

async def submit_consent(
    *,
    br: str,
    bt: str,
    kiosk_id: str,
    lead_id: int,
    consent_form_id: int,
    form_slug: str,
    form_version: str,
    signed_name: str,
    signature_data_url: str,
    payload: dict[str, Any] | None = None,
) -> dict:
    """Upload signature, write a Consent Submissions row, return the row.

    Caller validates kiosk_id beforehand. Returns {ok, error?, row?}.
    """
    from hub.constants import T_CONSENT_SUBMISSIONS

    sess = await storage.get_kiosk_session(kiosk_id)
    if not sess:
        return {"ok": False, "error": "kiosk session not found or expired"}
    png = _decode_data_url(signature_data_url)
    if not png:
        return {"ok": False, "error": "invalid signature image"}

    async with httpx.AsyncClient(timeout=20) as client:
        sig_url = await _upload_signature_png(
            client=client,
            png_bytes=png,
            lead_id=lead_id,
            slug=form_slug,
        )
        if not sig_url:
            return {"ok": False, "error": "signature upload failed"}

        row_payload = {
            "Signed Name": signed_name or "",
            "Signed At": _utc_iso(),
            "Signature URL": sig_url,
            "Form Slug": form_slug,
            "Form Version": form_version or "",
            "Payload JSON": json.dumps(payload or {}),
            "Kiosk Session": kiosk_id,
            "Lead": [int(lead_id)] if lead_id else None,
            "Event": [int(sess["event_id"])] if sess.get("event_id") else None,
            "Consent Form": [int(consent_form_id)] if consent_form_id else None,
        }
        # Strip Nones so Baserow doesn't complain about empty link arrays.
        row_payload = {k: v for k, v in row_payload.items() if v is not None}

        r = await client.post(
            f"{br}/api/database/rows/table/{T_CONSENT_SUBMISSIONS}/?user_field_names=true",
            headers={"Authorization": f"Token {bt}", "Content-Type": "application/json"},
            json=row_payload,
        )
        if r.status_code not in (200, 201):
            return {"ok": False, "error": f"baserow {r.status_code}: {r.text[:200]}"}
        return {"ok": True, "row": r.json(), "signature_url": sig_url}


# ─── Lead capture (kiosk-public path) ───────────────────────────────────────

async def capture_lead_via_kiosk(
    *,
    br: str,
    bt: str,
    kiosk_id: str,
    name: str,
    phone: str,
    email: str,
    reason: str,
    notes: str,
) -> dict:
    """Public lead capture for kiosk mode. Auto-links the kiosk's event and
    sets Owner to the rep who started the kiosk. Returns the new lead row.
    """
    from hub.constants import T_LEADS

    sess = await storage.get_kiosk_session(kiosk_id)
    if not sess:
        return {"ok": False, "error": "kiosk session not found or expired"}

    fields: dict[str, Any] = {
        "Name": (name or "").strip(),
        "Phone": (phone or "").strip(),
        "Email": (email or "").strip(),
        "Status": "New",
        "Source": sess.get("event_name") or "Kiosk",
        "Owner": sess.get("created_by") or "",
        "Reason": (reason or "").strip(),
        "Notes": (notes or "").strip(),
    }
    if sess.get("event_id"):
        fields["Event"] = [int(sess["event_id"])]

    if not fields["Name"] or not fields["Phone"]:
        return {"ok": False, "error": "name and phone are required"}

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{br}/api/database/rows/table/{T_LEADS}/?user_field_names=true",
            headers={"Authorization": f"Token {bt}", "Content-Type": "application/json"},
            json=fields,
        )
        if r.status_code not in (200, 201):
            return {"ok": False, "error": f"baserow {r.status_code}: {r.text[:200]}"}
        await storage.invalidate_table(T_LEADS)
        return {"ok": True, "row": r.json()}
