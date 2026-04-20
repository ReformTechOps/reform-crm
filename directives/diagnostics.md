# Diagnostics — Directive

## What This Is

`execution/diagnose.py` is a fast, local-first diagnostic tool for the Reform workspace. Run it whenever something is broken or after a significant deploy to confirm everything is healthy. It surfaces root causes in seconds instead of burning session context on iterative debugging.

---

## When to Run It

- **Before starting a bug investigation** — run this first, not last
- **After any deploy** — confirm nothing is broken
- **When something "stops working"** — run before reading any code
- **After rotating API keys or updating Modal secrets** — verify env vars propagated

---

## Usage

```bash
cd "c:\Users\crazy\Reform Workspace"

# All checks (default)
python execution/diagnose.py

# JS only (fastest — catches syntax errors and missing function errors)
python execution/diagnose.py --js

# Environment variables only
python execution/diagnose.py --env

# Live endpoint + Baserow connectivity only
python execution/diagnose.py --live
```

---

## What It Checks

### [1] JS Syntax Check
Walks `execution/modal_outreach_hub.py` and every `.py` in `execution/hub/` (except `__init__.py`), extracts every triple-quoted JS block, and runs each through **esprima**. Reports the exact file, line, and block label on any parse error. esprima line numbers are mapped back to file lines using each block's start offset.

**Block kinds it understands:**
- **f-string** (`js = f"""..."""`): `{{` / `}}` decoded to literal braces; `{expr}` replaced with `null` (with newline padding so line numbers stay stable); Python string escapes (`\\\\`, `\\'`, `\\n`, `\\uXXXX`) applied to literal segments so esprima sees the same text the browser receives.
- **format** (plain `_JS_SHARED = """..."""` consumed via `.format(...)` — detected automatically by scanning for `<name>.format(` in the source): handled like an f-string.
- **raw** (`_TEMPLATES_JS = r"""..."""`): passed through unchanged.
- **plain** (`js = """..."""` with no format placeholders): only Python escape processing.

Block discovery is by name — any variable whose name contains `js` as a word component (case-insensitive: `js`, `route_js`, `_COMPOSE_JS`, `_JS_SHARED`, etc.) — plus a content sniff that picks up helper snippets (`firm_counts_load`, `prev_rel_badge`, …) which get interpolated into larger blocks. Those helpers are wiped to `null` when their host block is flattened, so they need direct syntax-checking.

**Catches:**
- String escaping bugs (e.g. `\\'Enter\\'` collapsing to `'Enter'` and terminating the outer `'...'` JS string)
- Unclosed brackets, malformed function bodies
- Any error that would cause `SyntaxError` in the browser and silently prevent the block's JS from running

**Requires:** `pip install esprima` (pure-Python parser; no Node dependency).

### [2] JS Function Inventory
Collects defined function names by scanning both the flattened JS code *and* the raw Python source across all files in scope — this catches functions defined inside single-quoted string concatenations (e.g. `'function openDrawer(){...}'` in `hub/shells.py`) that would otherwise be missed. Cross-references against names called from HTML `onclick`/`oninput`/etc. attributes anywhere in the source.

**Catches:**
- `ReferenceError: X is not defined` class of errors
- Functions removed or renamed without updating HTML

### [3] Environment Variables
Reads `.env` and checks that all required keys are present for both the hub and the Shotstack worker. Masks values (shows first 4 chars only).

**Required for hub:** `BASEROW_URL`, `BASEROW_API_TOKEN`, `BUNNY_STORAGE_API_KEY`, `BUNNY_STORAGE_ZONE`, `BUNNY_CDN_BASE`, `BUNNY_ACCOUNT_API_KEY`

**Required for Shotstack worker:** `SHOTSTACK_SANDBOX_API_KEY`, `BUNNY_STORAGE_API_KEY`, `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_TOKEN`

**Catches:**
- Missing keys that cause silent failures (e.g., Bunny upload silently skipping, n8n callback missing fields)
- Modal secrets not propagated (secret exists but var is missing)

### [4] Live Endpoint & Baserow Checks
- GETs the hub `/login` page and verifies it returns 200
- Authenticates to Baserow with `BASEROW_API_TOKEN` and verifies the token is valid
- Checks row counts on key tables (T_GOR_VENUES 790, T_GOR_ACTS 791) to confirm access

**Catches:**
- Hub not deployed or crashed
- Expired/rotated Baserow token
- Table access permission issues

---

## Adding New Checks

When you add a new feature, update this script:

**New env vars:** Add to the `REQUIRED` dict under the appropriate group in `check_env()`.

**New Baserow tables:** Add to `KEY_TABLES` in `check_live()`.

**New API endpoints:** Add to the `check_live()` function. Pattern: make a request, check status code and response shape.

**New JS blocks:** Auto-discovered. Any `.py` file in `execution/hub/` or `execution/modal_outreach_hub.py` is scanned. Any variable whose name contains `js` as a word component, or whose body is used with `.format()` elsewhere, or which starts with unmistakably-JS content (`function …`, `const …`, `async function`, etc.) gets picked up.

**New hub source directory:** If the hub is refactored again, update `_js_source_files()` in `diagnose.py`.

---

## Known Limitations

- JS f-string blocks have `{expr}` substitutions replaced with `null` — this catches structural errors but not value-dependent errors.
- The f-string flattener tracks `{` / `}` depth by character; a closing `}` that only appears inside a string literal inside an expression (e.g. `{x if cond else "}"}`) will confuse the counter. Rare in practice.
- Live checks require the hub to be deployed and reachable.
- Function inventory only catches functions referenced in HTML `onclick`-style attributes within the Python source — it won't catch calls made from pure JS.

## Known Escape Pitfalls

Writing JS inside a Python f-string has sharp edges. These are the ones that have bitten us (pre-2026-04-17):

- **`\\'` collapses to `'`** in a non-raw f-string. If the outer JS string is `'...'`, any `\\'X\\'` inside collapses to `'X'` and terminates the string. Write `\\\\\\'X\\\\\\'` in the Python source → emits `\\'X\\'` in JS → valid escape.
- **`\\"` collapses to `"`** likewise in a Python `"..."` literal. Write `\\\\\\"` to emit `\\"` in JS.
- **`'none'`, `Didn\\'t`, and friends** inside a plain (non-f) triple-quoted JS block need the same treatment: use `\\\\'` to emit `\\'` in JS.

The `[3] f-string JS Escape Check` stage flags bare `\\'` patterns specifically, and the `[1] JS Syntax Check` will catch the downstream syntax error whether the block is f-string, plain, or raw.

---

## Root Cause Map

| Symptom | Most likely check to run | What to look for |
|---------|--------------------------|------------------|
| Button does nothing, no error in console | `--js` | SyntaxError in JS Syntax Check |
| `X is not defined` in console | `--js` | Warning in JS Function Inventory |
| API returns 401 or missing field | `--env` | Missing API key |
| Feature worked, then stopped | `--env` then `--live` | Rotated secret or Baserow token |
| Bunny upload silently fails | `--env` | `BUNNY_STORAGE_API_KEY` missing |
| n8n callback missing field | `--env` | `N8N_WEBHOOK_TOKEN` or Bunny keys missing |
| Hub not loading at all | `--live` | Hub endpoint check |

---

## File Reference

| File | Purpose |
|------|---------|
| `execution/diagnose.py` | The diagnostic script |
| `execution/modal_outreach_hub.py` | Hub source (JS extracted from here) |
| `.env` | Environment variables checked |
