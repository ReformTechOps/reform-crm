#!/usr/bin/env python3
"""Upsert the 2026-05 batch of kiosk consent forms into T_CONSENT_FORMS (828).

Matches existing rows by Slug and PATCHes; creates new rows otherwise. Run
this any time the canonical consent text needs to be re-pushed — it's
idempotent.

Slugs used (suffixed _v1 to match the convention seeded in
setup_consent_tables.py — bump to _v2 if/when legal makes substantive
changes so old submissions stay tied to the version they signed).
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

BASEROW_URL       = os.getenv("BASEROW_URL", "").rstrip("/")
BASEROW_API_TOKEN = os.getenv("BASEROW_API_TOKEN", "")
T_CONSENT_FORMS   = 828

if not BASEROW_URL or not BASEROW_API_TOKEN:
    print("Missing BASEROW_URL / BASEROW_API_TOKEN in .env", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Token {BASEROW_API_TOKEN}",
    "Content-Type":  "application/json",
}


MASSAGE_BODY = """INFORMED CONSENT FOR MASSAGE THERAPY

I, the undersigned, request and consent to receive massage therapy services
from Reform Chiropractic and its licensed therapists.

I understand that:
- Massage therapy is provided for relaxation, muscle relief, and general
  wellness. It is not a substitute for medical diagnosis or treatment.
- I will inform the therapist of any allergies, injuries, areas of pain, or
  medical conditions before the session begins, and during if anything
  changes.
- Pressure can be adjusted at any time. I may pause or end the session at
  any moment for any reason.
- Massage may briefly cause soreness, light bruising, or temporary
  tenderness. Reactions vary by individual.
- Reform Chiropractic does not diagnose illness, prescribe medication, or
  perform spinal manipulation under this consent.

I confirm I am 18 or older, or that a parent/legal guardian is signing on
behalf of a minor. I have had the chance to ask questions and have my
questions answered.

By signing below I acknowledge I have read and understood this form, and I
voluntarily consent to massage therapy."""


CHIRO_ADJUSTMENT_BODY = """INFORMED CONSENT FOR CHIROPRACTIC ADJUSTMENT

I, the undersigned, request and consent to receive chiropractic adjustment
and related care from a licensed chiropractor at Reform Chiropractic.

I understand that chiropractic care includes hands-on spinal manipulation,
joint mobilization, soft-tissue therapy, and similar techniques used to
restore joint motion and relieve pain.

I have been informed that, as with any health-care procedure, there are
certain risks. These risks include, but are not limited to:
- Temporary soreness, stiffness, or mild bruising near the area treated
- Aggravation of an existing condition
- Rare risk of disc injury, rib injury, or strain to nearby tissue
- Very rare risk of stroke associated with cervical (neck) manipulation

These outcomes are uncommon, and the chiropractor will adjust technique to
my comfort. I may stop the adjustment at any time.

I confirm that I have:
- Disclosed all current and past medical conditions, medications, prior
  surgeries, recent injuries, and any pregnancy status
- Had the chance to ask questions about the proposed care plan
- Been informed that other treatment options exist, including medical care,
  physical therapy, and choosing not to receive treatment

I confirm I am 18 or older, or that a parent/legal guardian is signing on
behalf of a minor.

By signing below I acknowledge I have read and understood this form, and I
voluntarily consent to chiropractic adjustment and related care."""


CHIRO_CONSULT_BODY = """CONSENT TO CHIROPRACTIC CONSULTATION

I authorize Reform Chiropractic and its licensed providers to perform an
initial consultation, history intake, and noninvasive assessment.

I understand that:
- A consultation is for evaluation only. No treatment, adjustment, or
  spinal manipulation will be performed under this consent.
- I will be asked about my medical history, current symptoms, medications,
  prior injuries, and goals.
- Light range-of-motion and posture observation may be performed. I may
  decline any portion of the assessment.
- Information shared in the consultation is treated confidentially under
  HIPAA. It may be used to recommend appropriate next steps, including a
  separate care plan that would require its own consent.

I confirm I am 18 or older, or that a parent/legal guardian is signing on
behalf of a minor.

By signing below I acknowledge I have read and understood this form, and I
voluntarily consent to a chiropractic consultation."""


HEALTH_SCREENING_BODY = """INFORMED CONSENT FOR HEALTH SCREENING

I voluntarily consent to participate in a health screening offered by
Reform Chiropractic at this event.

The screening may include:
- Posture and range-of-motion observation
- Blood pressure and pulse measurement
- A short questionnaire about pain, sleep, stress, and lifestyle

I understand that:
- A screening is not a medical exam, diagnosis, or treatment plan. It is
  intended only to flag wellness areas worth following up on.
- Results will be shared with me directly and may be used in aggregate
  (without my name) for event reporting.
- If a follow-up consultation is recommended I am free to decline it.
- I will tell the person screening me about any pain, recent injuries, or
  medical conditions before we begin.

By signing below I acknowledge I have read and understood this form, and I
voluntarily consent to participate in the screening."""


HIPAA_COMMS_BODY = """HIPAA NOTICE & COMMUNICATIONS CONSENT

By signing below I acknowledge I have received Reform Chiropractic's Notice
of Privacy Practices, which explains how my protected health information
may be used and disclosed.

I also consent to be contacted by Reform Chiropractic by phone, text, or
email at the contact details I provided, regarding:
- Appointment scheduling, confirmations, and reminders
- Follow-up about my consultation, screening, or service
- Educational and wellness information related to my visit

I understand:
- Standard message and data rates may apply for SMS messages.
- I may revoke this consent at any time by replying STOP to a text or
  contacting the office directly.
- Revoking consent will not affect care I have already received.

By signing below I confirm I have read and agreed to the above."""


FORMS = [
    {
        "Slug":         "massage_v1",
        "Display Name": "Massage Therapy Consent",
        "Body":         MASSAGE_BODY,
        "Version":      "v1",
        "Active":       True,
    },
    {
        "Slug":         "adjustment_v1",
        "Display Name": "Chiropractic Adjustment Consent",
        "Body":         CHIRO_ADJUSTMENT_BODY,
        "Version":      "v1",
        "Active":       True,
    },
    {
        "Slug":         "chiropractic_consult_v1",
        "Display Name": "Chiropractic Consultation Consent",
        "Body":         CHIRO_CONSULT_BODY,
        "Version":      "v1",
        "Active":       True,
    },
    {
        "Slug":         "health_screening_v1",
        "Display Name": "Health Screening Consent",
        "Body":         HEALTH_SCREENING_BODY,
        "Version":      "v1",
        "Active":       True,
    },
    {
        "Slug":         "hipaa_communications_v1",
        "Display Name": "HIPAA & Communications Consent",
        "Body":         HIPAA_COMMS_BODY,
        "Version":      "v1",
        "Active":       True,
    },
]


def list_existing_by_slug() -> dict:
    """Pull every row, key by Slug. Tiny table — one page is enough."""
    url = f"{BASEROW_URL}/api/database/rows/table/{T_CONSENT_FORMS}/"
    r = requests.get(
        url,
        headers=HEADERS,
        params={"size": 200, "user_field_names": "true"},
    )
    r.raise_for_status()
    out = {}
    for row in r.json().get("results", []):
        slug = (row.get("Slug") or "").strip()
        if slug:
            out[slug] = row
    return out


def create_row(payload: dict) -> dict:
    url = f"{BASEROW_URL}/api/database/rows/table/{T_CONSENT_FORMS}/?user_field_names=true"
    r = requests.post(url, headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()


def update_row(row_id: int, payload: dict) -> dict:
    url = f"{BASEROW_URL}/api/database/rows/table/{T_CONSENT_FORMS}/{row_id}/?user_field_names=true"
    r = requests.patch(url, headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()


def main() -> None:
    existing = list_existing_by_slug()
    print(f"Found {len(existing)} existing consent forms in T_CONSENT_FORMS.")
    for form in FORMS:
        slug = form["Slug"]
        if slug in existing:
            row_id = existing[slug]["id"]
            update_row(row_id, form)
            print(f"  UPDATED  #{row_id:<4} {slug}")
        else:
            row = create_row(form)
            print(f"  CREATED  #{row.get('id'):<4} {slug}")
    print("Done.")


if __name__ == "__main__":
    main()
