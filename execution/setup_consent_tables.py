#!/usr/bin/env python3
"""Set up consent-form tables in the Outreach database (203).

Creates two tables:
  1. T_CONSENT_FORMS — catalog of consent docs (slug, name, body, version, active)
  2. T_CONSENT_SUBMISSIONS — signed records (Lead, Event, Form, signed name,
     signed at, signature URL, payload JSON)

Both tables live in db 203 so link_rows can reach T_LEADS (817), T_EVENTS (816),
and the new T_CONSENT_FORMS in the same db.

Also seeds two consent forms (massage_v1, adjustment_v1) with placeholder
legalese — replace the body text once legal-reviewed copy is available.

Idempotent: skips creation if the table/field/seed row already exists.
Prints the resulting table IDs at the end — add them to .env and Modal secrets.

Usage:
    python execution/setup_consent_tables.py
"""

import os
import sys
import time
import json
import requests
from dotenv import load_dotenv

load_dotenv()

BASEROW_URL      = os.getenv("BASEROW_URL")
BASEROW_API_TOKEN = os.getenv("BASEROW_API_TOKEN")
BASEROW_EMAIL    = os.getenv("BASEROW_EMAIL")
BASEROW_PASSWORD = os.getenv("BASEROW_PASSWORD")
DATABASE_ID      = 203

T_LEADS  = 817
T_EVENTS = 816

if not (BASEROW_URL and BASEROW_EMAIL and BASEROW_PASSWORD):
    print("Missing BASEROW_URL / BASEROW_EMAIL / BASEROW_PASSWORD in .env", file=sys.stderr)
    sys.exit(1)


_jwt_token = None
_jwt_time  = 0

def fresh_token():
    global _jwt_token, _jwt_time
    if _jwt_token is None or (time.time() - _jwt_time) > 480:
        r = requests.post(f"{BASEROW_URL}/api/user/token-auth/", json={
            "email": BASEROW_EMAIL, "password": BASEROW_PASSWORD,
        })
        r.raise_for_status()
        _jwt_token = r.json()["access_token"]
        _jwt_time  = time.time()
    return _jwt_token

def jwt_headers():
    return {"Authorization": f"JWT {fresh_token()}", "Content-Type": "application/json"}

def token_headers():
    return {"Authorization": f"Token {BASEROW_API_TOKEN}", "Content-Type": "application/json"}


def list_tables(db_id):
    r = requests.get(f"{BASEROW_URL}/api/database/tables/database/{db_id}/", headers=jwt_headers())
    r.raise_for_status()
    return r.json()

def create_table(db_id, name):
    r = requests.post(
        f"{BASEROW_URL}/api/database/tables/database/{db_id}/",
        headers=jwt_headers(),
        json={"name": name},
    )
    r.raise_for_status()
    return r.json()

def get_fields(table_id):
    r = requests.get(f"{BASEROW_URL}/api/database/fields/table/{table_id}/", headers=jwt_headers())
    r.raise_for_status()
    return r.json()

def create_field(table_id, field_config):
    r = requests.post(
        f"{BASEROW_URL}/api/database/fields/table/{table_id}/",
        headers=jwt_headers(),
        json=field_config,
    )
    if r.status_code == 200:
        print(f"    + {field_config['name']} ({field_config['type']})")
        return r.json()
    print(f"    WARN: Failed to create '{field_config['name']}': {r.status_code} {r.text[:200]}")
    return None

def delete_field(field_id):
    r = requests.delete(f"{BASEROW_URL}/api/database/fields/{field_id}/", headers=jwt_headers())
    return r.status_code in (200, 204)

def get_or_create_table(db_id, name):
    tables = list_tables(db_id)
    existing = next((t for t in tables if t["name"] == name), None)
    if existing:
        print(f"  Table '{name}' already exists (ID: {existing['id']})")
        return existing["id"], False
    print(f"  Creating table '{name}'...")
    table = create_table(db_id, name)
    print(f"  Created '{name}' (ID: {table['id']})")
    return table["id"], True

def ensure_fields(table_id, fields_config):
    # Drop default Notes/Active fields Baserow auto-creates BEFORE ensuring our
    # schema — otherwise a real Active boolean we want to add gets skipped as
    # "already exists" and then the cleanup deletes it.
    desired_names = {f["name"] for f in fields_config}
    existing = get_fields(table_id)
    for f in existing:
        if f["name"] in {"Notes", "Active"} and f["name"] not in desired_names and not f.get("primary", False):
            if delete_field(f["id"]):
                print(f"    - Removed default field '{f['name']}'")
    # If a default Active/Notes field's name overlaps with one we want, drop it
    # too (it's the wrong type — Baserow's default is text, ours is typed).
    for f in existing:
        if f["name"] in desired_names and f["name"] in {"Notes", "Active"} and not f.get("primary", False):
            # Compare type: only delete if the existing default doesn't match
            wanted_type = next((c["type"] for c in fields_config if c["name"] == f["name"]), None)
            if wanted_type and f.get("type") != wanted_type:
                if delete_field(f["id"]):
                    print(f"    - Replaced default '{f['name']}' (was {f.get('type')}, want {wanted_type})")
    existing = get_fields(table_id)
    existing_names = {f["name"] for f in existing}
    for field_config in fields_config:
        if field_config["name"] in existing_names:
            print(f"    = {field_config['name']} (already exists)")
        else:
            create_field(table_id, field_config)


# ─── Schemas ────────────────────────────────────────────────────────────────

# T_CONSENT_FORMS — the catalog of consents the kiosk can present.
CONSENT_FORMS_FIELDS = [
    {"name": "Slug",    "type": "text"},      # e.g. massage_v1
    {"name": "Display Name", "type": "text"}, # e.g. "Massage Consent"
    {"name": "Body",    "type": "long_text"}, # markdown body shown to the lead
    {"name": "Version", "type": "text"},      # e.g. "v1"
    {"name": "Active",  "type": "boolean"},
]

# T_CONSENT_SUBMISSIONS — one row per signed consent
CONSENT_SUBMISSIONS_FIELDS = [
    {"name": "Signed Name",   "type": "text"},
    {"name": "Signed At",     "type": "date", "date_format": "ISO",
     "date_include_time": True, "date_time_format": "24"},
    {"name": "Signature URL", "type": "url"},
    {"name": "Form Slug",     "type": "text"},   # denormalized for fast filter/lookup
    {"name": "Form Version",  "type": "text"},
    {"name": "Payload JSON",  "type": "long_text"},  # captured form fields
    {"name": "Kiosk Session", "type": "text"},   # kiosk_id (for audit / dedup)
]


# ─── Seed data ──────────────────────────────────────────────────────────────

PLACEHOLDER_MASSAGE_BODY = """\
# Massage Therapy Consent (Placeholder)

I, the undersigned, voluntarily consent to receive massage therapy services
from Reform Chiropractic. I acknowledge and agree to the following terms:

1. **Disclosure of conditions.** I have disclosed any medical conditions,
   injuries, allergies, medications, or other relevant health information that
   may affect my ability to safely receive massage therapy.

2. **No medical diagnosis.** I understand that massage therapy is not a
   substitute for medical examination, diagnosis, or treatment. I will consult
   a physician for any condition I believe may require medical attention.

3. **Right to stop.** I understand I may decline any technique, request changes
   in pressure or focus, or terminate the session at any time without penalty.

4. **Risk acknowledgment.** I understand that, while uncommon, massage may
   cause soreness, bruising, or temporary discomfort, and I accept this as a
   normal part of treatment.

5. **Privacy.** I authorize Reform Chiropractic to collect and retain the
   information on this form solely for service-delivery and recordkeeping
   purposes consistent with applicable law.

By signing below I confirm I have read and understood the foregoing and that
I am of legal age (or am authorized to consent on behalf of the recipient).
"""

PLACEHOLDER_ADJUSTMENT_BODY = """\
# Chiropractic Adjustment Consent (Placeholder)

I, the undersigned, voluntarily consent to chiropractic evaluation and
adjustment performed by a licensed practitioner of Reform Chiropractic. I
acknowledge and agree to the following terms:

1. **Nature of care.** Chiropractic care may include spinal and joint
   manipulation, mobilization, soft-tissue therapy, and rehabilitative
   exercise instruction.

2. **Material risks.** As with any healthcare procedure, chiropractic
   adjustment carries potential risks including but not limited to: temporary
   soreness, stiffness, muscle strain, rib injury, dizziness, and — in rare
   cases — disc injury or vertebrobasilar injury. I have had the opportunity
   to discuss these risks and any questions I may have.

3. **No guarantee of results.** I understand that no guarantee or assurance
   has been given as to the outcome of any treatment, and that results vary
   based on the individual.

4. **Right to refuse.** I may refuse any specific procedure, request a
   different approach, or terminate care at any time.

5. **Honest disclosure.** I have honestly disclosed all conditions, prior
   injuries, and medications relevant to my care.

By signing below, I confirm that I have read and understood this consent in
its entirety and have had any questions answered to my satisfaction.
"""

SEED_FORMS = [
    {
        "Slug": "massage_v1",
        "Display Name": "Massage Therapy Consent",
        "Body": PLACEHOLDER_MASSAGE_BODY,
        "Version": "v1",
        "Active": True,
    },
    {
        "Slug": "adjustment_v1",
        "Display Name": "Chiropractic Adjustment Consent",
        "Body": PLACEHOLDER_ADJUSTMENT_BODY,
        "Version": "v1",
        "Active": True,
    },
]


def seed_consent_forms(forms_table_id):
    print("\n4. Seeding consent forms")
    # Read existing rows by slug so we don't duplicate
    r = requests.get(
        f"{BASEROW_URL}/api/database/rows/table/{forms_table_id}/?user_field_names=true&size=200",
        headers=token_headers(),
    )
    if r.status_code != 200:
        print(f"    WARN: list seed rows failed: {r.status_code} {r.text[:200]}")
        return
    existing = {row.get("Slug"): row for row in r.json().get("results", [])}
    for form in SEED_FORMS:
        slug = form["Slug"]
        if slug in existing:
            print(f"    = {slug} (already seeded)")
            continue
        rr = requests.post(
            f"{BASEROW_URL}/api/database/rows/table/{forms_table_id}/?user_field_names=true",
            headers=token_headers(),
            json=form,
        )
        if rr.status_code in (200, 201):
            print(f"    + seeded {slug}")
        else:
            print(f"    WARN: seed {slug} failed: {rr.status_code} {rr.text[:200]}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Setting up Consent Forms + Submissions tables")
    print("=" * 60)

    # ── T_CONSENT_FORMS ────────────────────────────────────
    print("\n1. Consent Forms table")
    forms_id, _ = get_or_create_table(DATABASE_ID, "Consent Forms")
    ensure_fields(forms_id, CONSENT_FORMS_FIELDS)

    # ── T_CONSENT_SUBMISSIONS ──────────────────────────────
    print("\n2. Consent Submissions table")
    subs_id, _ = get_or_create_table(DATABASE_ID, "Consent Submissions")
    ensure_fields(subs_id, CONSENT_SUBMISSIONS_FIELDS)

    # ── Link rows on submissions ───────────────────────────
    print("\n3. Adding link_rows on Consent Submissions")
    existing = get_fields(subs_id)
    existing_names = {f["name"] for f in existing}
    for name, target in [("Lead", T_LEADS), ("Event", T_EVENTS), ("Consent Form", forms_id)]:
        if name in existing_names:
            print(f"    = {name} (already exists)")
        else:
            create_field(subs_id, {
                "name": name,
                "type": "link_row",
                "link_row_table_id": target,
            })

    # ── Seed catalog ───────────────────────────────────────
    seed_consent_forms(forms_id)

    # ── Summary ────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"T_CONSENT_FORMS       = {forms_id}")
    print(f"T_CONSENT_SUBMISSIONS = {subs_id}")
    print("=" * 60)
    print("\nAdd these to .env:")
    print(f"  T_CONSENT_FORMS={forms_id}")
    print(f"  T_CONSENT_SUBMISSIONS={subs_id}")


if __name__ == "__main__":
    main()
