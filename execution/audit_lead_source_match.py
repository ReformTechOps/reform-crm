"""Audit how well T_LEADS.Source matches T_COMPANIES.Name.

The route stop sheet (execution/field_rep/pages/route.py) and the company
detail page (execution/field_rep/pages/company.py) both surface "leads from
this business" by string-equality on the lead's `Source` field against the
business name. This is a fuzzy match by design — when a rep captures a
lead via the in-stop modal, Source is pre-filled with the business name,
but reps can edit it, and over time variants accumulate ("Starbucks" vs
"Starbucks Coffee" vs "Starbucks Downey").

This script reports how often that match cleanly resolves vs falls back
to free-text. The decision criterion: if clean-match rate is high
(>~80%), the current approach is fine; if it's mid (60-80%) we can
ignore for now; if it's low (<60%) we should add a real `Company` link
field on T_LEADS and update the capture form to write it.

Read-only. Safe to run anytime. Uses BASEROW_URL + BASEROW_API_TOKEN
from .env.

Usage:
    python execution/audit_lead_source_match.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter

import requests
from dotenv import load_dotenv

load_dotenv()

BR = os.environ.get("BASEROW_URL")
BT = os.environ.get("BASEROW_API_TOKEN")

if not BR or not BT:
    print("Missing BASEROW_URL / BASEROW_API_TOKEN in .env", file=sys.stderr)
    sys.exit(1)

T_LEADS = 817
T_COMPANIES = 820

H = {"Authorization": f"Token {BT}"}

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fetch_all(tid: int) -> list[dict]:
    """Page through every row in a Baserow table. Page size 200, capped at
    50 pages (10k rows) which is well above what either of these tables
    will hit anytime soon."""
    rows: list[dict] = []
    page = 1
    while page <= 50:
        r = requests.get(
            f"{BR}/api/database/rows/table/{tid}/"
            f"?size=200&user_field_names=true&page={page}",
            headers=H,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        rows.extend(data.get("results") or [])
        if not data.get("next"):
            break
        page += 1
    return rows


def normalize(s: str | None) -> str:
    return (s or "").strip().lower()


def main() -> None:
    print("Fetching T_LEADS (817) and T_COMPANIES (820) ...")
    leads = fetch_all(T_LEADS)
    companies = fetch_all(T_COMPANIES)
    print(f"  {len(leads)} leads, {len(companies)} companies")

    # Build the set of normalized company names. Multiple companies can
    # share a name (rare but possible) — a set is fine since we only
    # check membership.
    company_keys = {normalize(c.get("Name")) for c in companies if c.get("Name")}

    empty = 0
    matched = 0
    freetext_counts: Counter[str] = Counter()

    for lead in leads:
        src_raw = (lead.get("Source") or "").strip()
        if not src_raw:
            empty += 1
            continue
        if normalize(src_raw) in company_keys:
            matched += 1
        else:
            freetext_counts[src_raw] += 1

    freetext = sum(freetext_counts.values())
    total = len(leads)
    nonempty = total - empty

    def pct(n: int, d: int) -> str:
        return f"{(100.0 * n / d):.1f}%" if d else "—"

    # ---- Report -----------------------------------------------------------
    print()
    print("=" * 68)
    print("T_LEADS.Source vs T_COMPANIES.Name match audit")
    print("=" * 68)
    print(f"Total leads:           {total}")
    print(f"  Empty Source:        {empty:>5}  ({pct(empty, total)} of all)")
    print(f"  Source set:          {nonempty:>5}  ({pct(nonempty, total)} of all)")
    print(f"     ~ matched:        {matched:>5}  ({pct(matched, nonempty)} of nonempty)")
    print(f"     ~ free-text:      {freetext:>5}  ({pct(freetext, nonempty)} of nonempty)")
    print()

    if freetext_counts:
        print("Top 10 free-text Source values (potential near-misses):")
        for src, ct in freetext_counts.most_common(10):
            print(f"  {ct:>4}  {src!r}")
    else:
        print("No free-text Source values — every nonempty Source matched a Company.Name.")
    print()

    # ---- Decision hint ---------------------------------------------------
    if nonempty == 0:
        verdict = "INCONCLUSIVE — no leads with Source set yet."
    else:
        clean_rate = 100.0 * matched / nonempty
        if clean_rate >= 80:
            verdict = (
                f"KEEP CURRENT APPROACH — clean-match rate {clean_rate:.1f}%. "
                "Fuzzy Source-string match is good enough."
            )
        elif clean_rate >= 60:
            verdict = (
                f"BORDERLINE — clean-match rate {clean_rate:.1f}%. "
                "Adding a Company link field on T_LEADS would help but isn't urgent. "
                "Consider after other priorities."
            )
        else:
            verdict = (
                f"LOW MATCH RATE — {clean_rate:.1f}%. "
                "Recommend adding a real `Company` link field on T_LEADS and updating "
                "the Capture Lead form (execution/hub/lead_capture_ui.py + "
                "execution/hub/guerilla_api.py capture_lead) to write the company id "
                "instead of relying on Source string match."
            )
    print("Verdict:")
    print(f"  {verdict}")
    print()


if __name__ == "__main__":
    main()
