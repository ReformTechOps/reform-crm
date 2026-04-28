"""
Add 'In Progress' option to the Status single_select on T_GOR_ROUTE_STOPS (802).

Phase 1.4 introduced an Arrive flow that flips a stop's Status to 'In Progress'
between Pending and Visited. Baserow rejects writes to single_select values
that aren't in the field's option list — without this option, our PATCH gets
dropped silently and the stop stays Pending (marker color changes client-side
because that's local-only, but the row never updates).

JWT auth (email/password from .env). Idempotent.
"""
import os, sys, requests
from dotenv import load_dotenv

load_dotenv()
BR = os.environ["BASEROW_URL"]
EMAIL = os.environ["BASEROW_EMAIL"]
PW = os.environ["BASEROW_PASSWORD"]

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TID = 802
FIELD_NAME = "Status"
NEW_OPTION = {"value": "In Progress", "color": "purple"}


def jwt():
    r = requests.post(f"{BR}/api/user/token-auth/", json={"email": EMAIL, "password": PW})
    r.raise_for_status()
    d = r.json()
    return d.get("access_token") or d.get("token")


def main():
    token = jwt()
    h = {"Authorization": f"JWT {token}", "Content-Type": "application/json"}
    fields = requests.get(f"{BR}/api/database/fields/table/{TID}/", headers=h).json()
    status_field = next((f for f in fields if f["name"] == FIELD_NAME), None)
    if not status_field:
        print(f"  FAIL  no '{FIELD_NAME}' field on table {TID}")
        return
    if status_field.get("type") != "single_select":
        print(f"  FAIL  '{FIELD_NAME}' is type {status_field.get('type')}, not single_select")
        return
    opts = status_field.get("select_options", []) or []
    existing_values = [(o.get("value") or "").strip() for o in opts]
    if NEW_OPTION["value"] in existing_values:
        print(f"  SKIP  '{NEW_OPTION['value']}' already in {FIELD_NAME} options")
        return
    new_opts = [{k: o[k] for k in ("value", "color") if k in o} for o in opts] + [NEW_OPTION]
    r = requests.patch(
        f"{BR}/api/database/fields/{status_field['id']}/",
        headers=h,
        json={"select_options": new_opts},
    )
    if r.status_code in (200, 201):
        print(f"  OK    added '{NEW_OPTION['value']}' to {FIELD_NAME} on table {TID}")
        print(f"        full options now: {[o['value'] for o in r.json().get('select_options', [])]}")
    else:
        print(f"  FAIL  {r.status_code}: {r.text[:300]}")


if __name__ == "__main__":
    main()
