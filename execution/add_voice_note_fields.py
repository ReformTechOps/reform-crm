"""
Add voice-note fields to T_ACTIVITIES (822):
  - Audio URL   (long_text) — Bunny CDN link to the recording (.webm)
  - Transcript  (long_text) — raw Whisper transcript (rep edits Summary,
                              Transcript preserves the original)

Phase 2.1 voice-notes feature: rep records up to 90s in the activity composer,
audio uploaded to Bunny under `{zone}/activities/audio/{uuid}.webm`, transcribed
via OpenAI Whisper, both URL + transcript stored on the activity row alongside
the (editable) Summary.

JWT auth (email/password from .env). Idempotent.
"""
import os, requests, sys
from dotenv import load_dotenv

load_dotenv()
BR = os.environ["BASEROW_URL"]
EMAIL = os.environ["BASEROW_EMAIL"]
PASSWORD = os.environ["BASEROW_PASSWORD"]

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TID = 822

FIELDS = [
    {"name": "Audio URL",  "type": "long_text"},
    {"name": "Transcript", "type": "long_text"},
]


def jwt():
    r = requests.post(f"{BR}/api/user/token-auth/", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    d = r.json()
    return d.get("access_token") or d.get("token")


def main():
    token = jwt()
    h = {"Authorization": f"JWT {token}", "Content-Type": "application/json"}

    existing = {f["name"] for f in requests.get(f"{BR}/api/database/fields/table/{TID}/", headers=h).json()}

    for spec in FIELDS:
        if spec["name"] in existing:
            print(f"  SKIP {spec['name']} — exists")
            continue
        r = requests.post(f"{BR}/api/database/fields/table/{TID}/", headers=h, json=spec)
        if r.status_code in (200, 201):
            print(f"  OK   {spec['name']} ({spec['type']})")
        else:
            print(f"  FAIL {spec['name']} — {r.status_code}: {r.text[:200]}")


if __name__ == "__main__":
    main()
