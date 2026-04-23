"""
Shared business logic for /api/outreach/* endpoints.

Backend-agnostic handlers (no modal.*, no os.environ reads) that both the
Modal hub and the Coolify field_rep app wrap with thin route handlers.
See `execution/hub/guerilla_api.py` for the established pattern.
"""
from datetime import date as _date
from typing import Awaitable, Callable

from fastapi.responses import JSONResponse

from .constants import T_COMPANIES, T_ACTIVITIES

CachedRowsFn = Callable[[int], Awaitable[list]]


def _sv(v):
    """Extract scalar from Baserow single_select / link_row shapes."""
    if isinstance(v, dict):
        return v.get("value", "") or v.get("name", "") or ""
    if isinstance(v, list) and v:
        x = v[0]
        if isinstance(x, dict):
            return x.get("value", "") or x.get("name", "") or ""
        return str(x)
    return v or ""


def _fu_date(company: dict) -> str:
    """Return the patient/contact's scheduled follow-up date (ISO yyyy-mm-dd)
    or empty string. T_COMPANIES uses `Follow-Up Date` as the canonical field;
    some legacy migration data may fall back to alternate casings."""
    v = (company.get("Follow-Up Date")
         or company.get("Follow Up Date")
         or "").strip()
    if not v:
        return ""
    return str(v)[:10]


def _is_overdue(company: dict, today_iso: str) -> bool:
    fu = _fu_date(company)
    if not fu:
        return False
    return fu < today_iso


def _excluded_status(company: dict) -> bool:
    """Blacklisted or permanently-closed companies are dropped from outreach."""
    status = _sv(company.get("Contact Status")).strip().lower()
    if status == "blacklisted":
        return True
    if company.get("Permanently Closed") is True:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/outreach/due — all companies with Follow-Up Date < today
# ─────────────────────────────────────────────────────────────────────────────
async def get_outreach_due(
    br: str, bt: str, user: dict,
    cached_rows: CachedRowsFn,
    *,
    limit: int = 200,
) -> JSONResponse:
    """Return overdue-follow-up companies across all categories, sorted
    by how overdue. Shape: lightweight list tailored for a mobile dashboard.

    Each row: {id, name, category, phone, address, latitude, longitude,
               status, follow_up_date, days_overdue}
    """
    if not T_COMPANIES:
        return JSONResponse([])
    rows = await cached_rows(T_COMPANIES)
    today_iso = _date.today().isoformat()

    out: list[dict] = []
    for c in rows or []:
        if _excluded_status(c):
            continue
        if not _is_overdue(c, today_iso):
            continue
        fu = _fu_date(c)
        try:
            y, m, d = fu.split("-")
            from datetime import date as _d
            days = (_date.today() - _d(int(y), int(m), int(d))).days
        except Exception:
            days = 0
        out.append({
            "id":              c.get("id"),
            "name":            (c.get("Name") or "").strip() or "(unnamed)",
            "category":        _sv(c.get("Category")) or "other",
            "phone":           (c.get("Phone") or "").strip(),
            "address":         (c.get("Address") or "").strip(),
            "latitude":        (c.get("Latitude") or "").strip() if isinstance(c.get("Latitude"), str) else c.get("Latitude"),
            "longitude":       (c.get("Longitude") or "").strip() if isinstance(c.get("Longitude"), str) else c.get("Longitude"),
            "status":          _sv(c.get("Contact Status")),
            "follow_up_date":  fu,
            "days_overdue":    days,
        })
    out.sort(key=lambda r: r["days_overdue"], reverse=True)
    return JSONResponse(out[:limit])
