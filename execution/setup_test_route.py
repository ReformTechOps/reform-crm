#!/usr/bin/env python3
"""
Ensure route-stop schema has check-in fields, then create a test route
with N nearest venues so the mobile field-rep app has something to render.

Phase 1 — ensure schema:
  T_GOR_ROUTE_STOPS (802) gains if missing:
    - Check-In Lat  (text)   — captured when the rep marks a stop visited
    - Check-In Lng  (text)
    - Completed At  (datetime)
    - Completed By  (text)
  The `update_route_stop` handler in hub/guerilla_api.py writes these but
  the original setup never added them.

Phase 2 — seed a test route with N nearest geocoded venues, ordered by
distance from the Downey office.

Idempotent — safe to re-run. An existing route with the same Name is
patched; its stops are wiped + recreated so edits to the seed data take
effect on a re-run.

Usage:
    python execution/setup_test_route.py
    python execution/setup_test_route.py --name "Test Route 2 — 5 Stops" --stops 5
    python execution/setup_test_route.py --assigned-to other@reformchiropractic.com
"""
import argparse
import math
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

BASEROW_URL      = os.getenv("BASEROW_URL")
BASEROW_EMAIL    = os.getenv("BASEROW_EMAIL")
BASEROW_PASSWORD = os.getenv("BASEROW_PASSWORD")
BT               = os.getenv("BASEROW_API_TOKEN")

T_GOR_VENUES      = 790
T_GOR_ROUTES      = 801
T_GOR_ROUTE_STOPS = 802

OFFICE_LAT = 33.9478
OFFICE_LNG = -118.1335

DEFAULT_ROUTE_NAME  = "Test Route — Field Rep Demo"
DEFAULT_ASSIGNED_TO = "daniel.cis@reformchiropractic.com"
DEFAULT_STOP_COUNT  = 3


# ─── JWT helpers (for schema mutation — requires email/password auth) ────────
_jwt_token = None
_jwt_time  = 0


def fresh_jwt() -> str:
    global _jwt_token, _jwt_time
    if _jwt_token is None or (time.time() - _jwt_time) > 480:
        r = requests.post(f"{BASEROW_URL}/api/user/token-auth/", json={
            "email": BASEROW_EMAIL, "password": BASEROW_PASSWORD,
        })
        r.raise_for_status()
        _jwt_token = r.json()["access_token"]
        _jwt_time  = time.time()
    return _jwt_token


def jwt_headers() -> dict:
    return {"Authorization": f"JWT {fresh_jwt()}", "Content-Type": "application/json"}


def token_headers() -> dict:
    return {"Authorization": f"Token {BT}", "Content-Type": "application/json"}


# ─── Phase 1 — schema fields ─────────────────────────────────────────────────

STOP_FIELDS = [
    {"name": "Check-In Lat",   "type": "text"},
    {"name": "Check-In Lng",   "type": "text"},
    {"name": "Completed At",   "type": "date", "date_format": "US", "date_include_time": True},
    {"name": "Completed By",   "type": "text"},
]


def ensure_stop_fields() -> None:
    print("\n[1/3] Ensuring T_GOR_ROUTE_STOPS schema has check-in fields")
    r = requests.get(
        f"{BASEROW_URL}/api/database/fields/table/{T_GOR_ROUTE_STOPS}/",
        headers=jwt_headers(), timeout=30,
    )
    r.raise_for_status()
    existing = {f["name"] for f in r.json()}
    for cfg in STOP_FIELDS:
        if cfg["name"] in existing:
            print(f"  = {cfg['name']} (exists)")
            continue
        add = requests.post(
            f"{BASEROW_URL}/api/database/fields/table/{T_GOR_ROUTE_STOPS}/",
            headers=jwt_headers(), json=cfg, timeout=30,
        )
        if add.status_code == 200:
            print(f"  + {cfg['name']} ({cfg['type']})")
        else:
            print(f"  WARN: '{cfg['name']}' failed: {add.status_code} {add.text[:160]}")


# ─── Phase 2 — pick venues ───────────────────────────────────────────────────

def haversine_miles(lat1, lng1, lat2, lng2) -> float:
    R = 3959.0  # earth radius, miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def fetch_all(tid: int) -> list:
    """Token-auth paginated fetch via user_field_names."""
    out: list = []
    page = 1
    while True:
        r = requests.get(
            f"{BASEROW_URL}/api/database/rows/table/{tid}/",
            params={"user_field_names": "true", "size": 200, "page": page},
            headers={"Authorization": f"Token {BT}"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("results", []))
        if not data.get("next"):
            break
        page += 1
    return out


def pick_n_nearest_venues(n: int) -> list[dict]:
    print(f"\n[2/3] Picking {n} nearest venues from T_GOR_VENUES with lat/lng")
    venues = fetch_all(T_GOR_VENUES)
    scored: list[tuple[float, dict]] = []
    for v in venues:
        try:
            lat = float(v.get("Latitude") or 0)
            lng = float(v.get("Longitude") or 0)
        except (TypeError, ValueError):
            continue
        if lat == 0 or lng == 0:
            continue
        d = haversine_miles(OFFICE_LAT, OFFICE_LNG, lat, lng)
        scored.append((d, v))
    scored.sort(key=lambda t: t[0])
    picks = [v for _, v in scored[:n]]
    for (d, v), order in zip(scored[:n], range(1, n + 1)):
        print(f"  #{order}  {v.get('Name') or '(unnamed)'}  —  {d:.2f}mi  (venue id: {v['id']})")
    if len(picks) < n:
        raise SystemExit(f"Only found {len(picks)} geocoded venues; need at least {n}.")
    return picks


# ─── Phase 3 — write test route ──────────────────────────────────────────────

def find_test_route(name: str) -> dict | None:
    rows = fetch_all(T_GOR_ROUTES)
    for r in rows:
        if (r.get("Name") or "").strip() == name:
            return r
    return None


def upsert_test_route(venues: list[dict], name: str, assigned_to: str) -> dict:
    print("\n[3/3] Upserting test route")
    from datetime import date as _date
    today = _date.today().isoformat()
    payload = {
        "Name":        name,
        "Date":        today,
        "Assigned To": assigned_to,
        "Status":      "Active",
        "Notes":       "Seeded by setup_test_route.py for mobile field-rep testing.",
    }
    existing = find_test_route(name)
    if existing:
        rid = existing["id"]
        print(f"  = Route exists (id={rid}); patching")
        r = requests.patch(
            f"{BASEROW_URL}/api/database/rows/table/{T_GOR_ROUTES}/{rid}/?user_field_names=true",
            headers=token_headers(), json=payload, timeout=30,
        )
        r.raise_for_status()
        # Wipe old stops — re-run should reflect new stop data
        old_stops = fetch_all(T_GOR_ROUTE_STOPS)
        to_delete = [s["id"] for s in old_stops if any(x.get("id") == rid for x in (s.get("Route") or []))]
        for sid in to_delete:
            requests.delete(
                f"{BASEROW_URL}/api/database/rows/table/{T_GOR_ROUTE_STOPS}/{sid}/",
                headers={"Authorization": f"Token {BT}"}, timeout=30,
            )
        print(f"  - Removed {len(to_delete)} old stops")
        route = r.json()
    else:
        print("  + Creating new route")
        r = requests.post(
            f"{BASEROW_URL}/api/database/rows/table/{T_GOR_ROUTES}/?user_field_names=true",
            headers=token_headers(), json=payload, timeout=30,
        )
        r.raise_for_status()
        route = r.json()

    # Create stops
    for order, v in enumerate(venues, start=1):
        stop_payload = {
            "Route":      [route["id"]],
            "Venue":      [v["id"]],
            "Stop Order": order,
            "Status":     "Pending",
            "Notes":      "",
        }
        sr = requests.post(
            f"{BASEROW_URL}/api/database/rows/table/{T_GOR_ROUTE_STOPS}/?user_field_names=true",
            headers=token_headers(), json=stop_payload, timeout=30,
        )
        if sr.status_code in (200, 201):
            print(f"  + stop {order}: {v.get('Name')}")
        else:
            print(f"  WARN: stop {order} failed: {sr.status_code} {sr.text[:160]}")
    return route


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--name", default=DEFAULT_ROUTE_NAME,
                        help=f"Route name (default: {DEFAULT_ROUTE_NAME!r})")
    parser.add_argument("--stops", type=int, default=DEFAULT_STOP_COUNT,
                        help=f"Number of nearest venues to add as stops (default: {DEFAULT_STOP_COUNT})")
    parser.add_argument("--assigned-to", default=DEFAULT_ASSIGNED_TO,
                        help=f"Email to assign the route to (default: {DEFAULT_ASSIGNED_TO})")
    args = parser.parse_args()

    if not (BASEROW_URL and BASEROW_EMAIL and BASEROW_PASSWORD and BT):
        raise SystemExit("Missing BASEROW_URL / BASEROW_EMAIL / BASEROW_PASSWORD / BASEROW_API_TOKEN in .env")
    print(f"Baserow: {BASEROW_URL}")
    print(f"Route:   {args.name}  →  {args.assigned_to}  ({args.stops} stops)")

    ensure_stop_fields()
    venues = pick_n_nearest_venues(args.stops)
    route = upsert_test_route(venues, name=args.name, assigned_to=args.assigned_to)

    print(f"\nDone. Route id={route['id']} created/updated with {args.stops} stops.")
    print(f"Sign into routes.reformchiropractic.app as {args.assigned_to} and")
    print("the test route should appear on the Routes dashboard. Tap")
    print("'Today's Route' to see the map.")


if __name__ == "__main__":
    main()
