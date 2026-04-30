#!/usr/bin/env python3
"""Add a Staff Attending text field to T_EVENTS (816).

Stores a comma-joined list of staff emails (matching T_STAFF.Email). Long_text
rather than link_row because T_STAFF lives in a different Baserow database
(197 / CRM) than T_EVENTS (203 / Outreach), and Baserow rejects cross-database
link_row writes (ERROR_LINK_ROW_TABLE_NOT_IN_SAME_DATABASE).

The UI does a client-side cross-db read of T_STAFF to render a checkbox picker.

Idempotent — skips creation if the field already exists.
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
T_EVENTS = 816
T_STAFF  = 815

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


def main():
    print("=" * 60)
    print(f"Adding Staff Attending (long_text) to T_EVENTS ({T_EVENTS})")
    print("=" * 60)

    existing = get_fields(T_EVENTS)
    existing_names = {f["name"] for f in existing}

    if "Staff Attending" in existing_names:
        print("    = Staff Attending (already exists)")
    else:
        create_field(T_EVENTS, {
            "name": "Staff Attending",
            "type": "long_text",
        })

    print("\nDone.")


if __name__ == "__main__":
    main()
