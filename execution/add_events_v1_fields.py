#!/usr/bin/env python3
"""
Idempotently add the v1 event-management fields to T_EVENTS (table 816).

Adds:
- 11 new fields (insurance %, competitor flag, staffing counts, logistics
  booleans, long-text decision/promo/services/materials notes)
- 2 new options on the existing `Event Status` single_select (Maybe, Declined)

Safe to re-run — skips fields that already exist and only appends missing
select options.
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASEROW_URL      = os.getenv("BASEROW_URL")
BASEROW_EMAIL    = os.getenv("BASEROW_EMAIL")
BASEROW_PASSWORD = os.getenv("BASEROW_PASSWORD")
T_EVENTS         = 816

if not (BASEROW_URL and BASEROW_EMAIL and BASEROW_PASSWORD):
    print("Missing BASEROW_URL / BASEROW_EMAIL / BASEROW_PASSWORD in .env", file=sys.stderr)
    sys.exit(1)


_jwt_token = None
_jwt_time  = 0

def fresh_token():
    global _jwt_token, _jwt_time
    if _jwt_token is None or (time.time() - _jwt_time) > 480:
        r = requests.post(
            f"{BASEROW_URL}/api/user/token-auth/",
            json={"email": BASEROW_EMAIL, "password": BASEROW_PASSWORD},
        )
        r.raise_for_status()
        _jwt_token = r.json()["access_token"]
        _jwt_time  = time.time()
    return _jwt_token

def headers():
    return {"Authorization": f"JWT {fresh_token()}", "Content-Type": "application/json"}


def get_fields(table_id):
    r = requests.get(f"{BASEROW_URL}/api/database/fields/table/{table_id}/", headers=headers())
    r.raise_for_status()
    return r.json()

def create_field(table_id, field_config):
    r = requests.post(
        f"{BASEROW_URL}/api/database/fields/table/{table_id}/",
        headers=headers(),
        json=field_config,
    )
    if r.status_code == 200:
        print(f"    + {field_config['name']} ({field_config['type']})")
        return r.json()
    print(f"    WARN: Failed to create '{field_config['name']}': {r.status_code} {r.text[:300]}")
    return None

def patch_field(field_id, patch):
    r = requests.patch(
        f"{BASEROW_URL}/api/database/fields/{field_id}/",
        headers=headers(),
        json=patch,
    )
    if r.status_code == 200:
        return r.json()
    print(f"    WARN: Failed to patch field {field_id}: {r.status_code} {r.text[:300]}")
    return None


NEW_FIELDS = [
    {"name": "Est Insurance Pct",   "type": "number", "number_decimal_places": 0},
    {"name": "Other Chiropractor",  "type": "single_select", "select_options": [
        {"value": "Yes",     "color": "red"},
        {"value": "No",      "color": "green"},
        {"value": "Unknown", "color": "light-gray"},
    ]},
    {"name": "Doctors Needed",      "type": "number", "number_decimal_places": 0},
    {"name": "Front Desk Needed",   "type": "number", "number_decimal_places": 0},
    {"name": "Therapists Needed",   "type": "number", "number_decimal_places": 0},
    {"name": "Generator Needed",    "type": "boolean"},
    {"name": "Table Needed",        "type": "boolean"},
    {"name": "EZ Up Needed",        "type": "boolean"},
    {"name": "Promotion",           "type": "long_text"},
    {"name": "Services Rendered",   "type": "long_text"},
    {"name": "Materials Needed",    "type": "long_text"},
    {"name": "Decision Notes",      "type": "long_text"},
]

EVENT_STATUS_NEW_OPTIONS = [
    {"value": "Maybe",    "color": "yellow"},
    {"value": "Declined", "color": "red"},
]


def main():
    print("=" * 60)
    print(f"Adding events v1 fields to T_EVENTS ({T_EVENTS})")
    print("=" * 60)

    existing = get_fields(T_EVENTS)
    existing_names = {f["name"] for f in existing}

    # 1. Add missing fields
    print("\n1. New fields")
    for f in NEW_FIELDS:
        if f["name"] in existing_names:
            print(f"    = {f['name']} (already exists)")
        else:
            create_field(T_EVENTS, f)

    # 2. Extend Event Status select options
    print("\n2. Event Status — add Maybe + Declined")
    status_field = next((f for f in existing if f["name"] == "Event Status"), None)
    if not status_field:
        print("    WARN: Event Status field not found on table.")
        return

    current_values = {opt["value"] for opt in status_field.get("select_options", [])}
    options_to_add = [o for o in EVENT_STATUS_NEW_OPTIONS if o["value"] not in current_values]
    if not options_to_add:
        print("    = both options already present, nothing to do")
    else:
        # Baserow expects the FULL select_options list on PATCH; append to existing.
        new_options = list(status_field.get("select_options", [])) + options_to_add
        # Strip keys Baserow doesn't accept on write
        cleaned = [
            {k: v for k, v in opt.items() if k in ("id", "value", "color")}
            for opt in new_options
        ]
        res = patch_field(status_field["id"], {"select_options": cleaned})
        if res:
            for opt in options_to_add:
                print(f"    + {opt['value']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
