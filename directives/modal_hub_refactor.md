# Modal Hub Refactor — APIRouter Split

## When to Use This

Read this before splitting [execution/modal_outreach_hub.py](../execution/modal_outreach_hub.py). Do NOT execute until the user explicitly asks to start the refactor. This is a deferred plan, parked by decision of the user until after the first CRM demo.

## Why

The file is 2685 LOC and the pain is concentrated, not diffuse:

1. **355-LOC Guerilla Log handler** (`@fapp.post("/api/guerilla/log")`) at lines ~923-1277 is a single endpoint the size of an entire `hub/` module. Any edit requires scrolling past it.
2. **512-LOC local-dev duplicate** in the `if __name__ == "__main__":` block at the bottom. This re-implements a subset of routes for `python execution/modal_outreach_hub.py`. It's already caused drift bugs — see the route-stop PATCH incident documented in [Reform_CRM.md](Reform_CRM.md) ("silently dropped because the fields didn't exist").

Raw LOC isn't the problem. The real costs are the big handler and the duplicate code path. The refactor targets both at once.

## Target Architecture

Convert route registration to FastAPI `APIRouter` modules under `execution/hub/api/`. The main file becomes a thin composition layer that instantiates `FastAPI()`, resolves deps, and calls `fapp.include_router(...)` for each module. The local-dev `__main__` block does the exact same thing against its own `FastAPI()` — **one source of truth per route, no duplication**.

### New layout

```
execution/
├── modal_outreach_hub.py     ← Modal app, warm_cache, OAuth endpoints, FastAPI composition
└── hub/
    ├── deps.py               ← _env(), _guard(), _refresh_if_needed(), session helpers
    │                            as FastAPI Depends() injectables
    └── api/
        ├── __init__.py
        ├── data.py           ← /api/data/{tid}, /api/dashboard, /api/contacts/autocomplete
        ├── patients.py       ← /api/patients/{stage}/{row_id}/firm, /api/contacts (POST)
        ├── gmail.py          ← /api/gmail/send, /api/gmail/threads, /api/gmail/thread/{id}
        ├── guerilla_log.py   ← /api/guerilla/log  (biggest win — 355 LOC out)
        ├── guerilla_boxes.py ← /api/guerilla/boxes/*, /api/guerilla/venues/{id}
        ├── guerilla_routes.py← /api/guerilla/routes/*  (5 endpoints)
        ├── social.py         ← /api/social/queue, /api/social/posted
        ├── events.py         ← /api/events/*, /api/leads/*
        └── pages.py          ← all page HTML routes (most are 3-line forwarders)
```

### Line-range map (source → target)

These ranges are from the state at the time of planning; re-verify with `grep -n "@fapp" execution/modal_outreach_hub.py` before starting.

| Current lines | Current location | New module |
|---|---|---|
| 210-326 | Login / OAuth | **Keep in** modal_outreach_hub.py (entry-point concern) |
| 329-342 | `/api/data/{tid}` | `api/data.py` |
| 345-424 | `/api/patients/{stage}/{row_id}/firm` | `api/patients.py` |
| 425-453 | `/api/contacts/autocomplete` | `api/data.py` |
| 454-509 | `/api/dashboard` | `api/data.py` |
| 510-653 | Gmail endpoints | `api/gmail.py` |
| 655-880 | Page handlers (dashboard, attorney, guerilla, community, planner, directories, PI, firms, billing, comms, contacts) | `api/pages.py` |
| 882-921 | `/api/contacts` (POST) | `api/patients.py` |
| 923-1277 | `/api/guerilla/log` | `api/guerilla_log.py` |
| 1278-1438 | Guerilla boxes & venue PATCH | `api/guerilla_boxes.py` |
| 1440-1803 | Guerilla routes CRUD (5 endpoints) | `api/guerilla_routes.py` |
| 1805-1895 | Social pages + queue/posted APIs | `api/social.py` |
| 1897-1939 | Mobile page redirects | `api/pages.py` |
| 1941-2168 | Events detail pages + leads API | `api/events.py` |
| 2173-2685 | LOCAL DEV duplicate | **delete** — replaced by `include_router` calls in `__main__` |

## Dependency Injection Pattern

The closure-captured helpers (`_env`, `_guard`, `_refresh_if_needed`, `httpx.AsyncClient`) become FastAPI `Depends()` injectables in `hub/deps.py`.

### Sketch for `hub/deps.py`

```python
import os, time
from typing import Annotated
from fastapi import Request, HTTPException, Depends
import httpx
import modal

SESSION_COOKIE = "hub_session"
hub_sessions = modal.Dict.from_name("hub-sessions", create_if_missing=True)

def _env() -> dict:
    return {
        "br":     os.environ.get("BASEROW_URL",        "https://baserow.reformchiropractic.app"),
        "bt":     os.environ.get("BASEROW_API_TOKEN",  ""),
        "gid":    os.environ.get("GOOGLE_CLIENT_ID",   ""),
        "gsec":   os.environ.get("GOOGLE_CLIENT_SECRET",""),
        "domain": os.environ.get("ALLOWED_DOMAIN",     ""),
    }

def _get_session(req: Request) -> dict | None:
    sid = req.cookies.get(SESSION_COOKIE)
    return hub_sessions.get(sid) if sid else None

async def require_session(request: Request) -> dict:
    s = _get_session(request)
    if not s:
        raise HTTPException(status_code=401, detail="unauthenticated")
    return s

Env = Annotated[dict, Depends(_env)]
Session = Annotated[dict, Depends(require_session)]
```

### Sketch for `hub/api/guerilla_routes.py`

```python
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from hub.deps import Env, Session
from hub.access import _has_hub_access, _is_admin
from hub.constants import T_GOR_ROUTES, T_GOR_ROUTE_STOPS

router = APIRouter(prefix="/api/guerilla/routes", tags=["guerilla-routes"])

@router.get("/today")
async def routes_today(session: Session, env: Env):
    if not _has_hub_access(session, "guerilla"):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    # ... existing logic, using env["br"], env["bt"]
```

### Composition in `modal_outreach_hub.py`

```python
from hub.api import data, patients, gmail, guerilla_log, guerilla_boxes, guerilla_routes, social, events, pages

@modal.asgi_app()
def web():
    fapp = FastAPI()
    # Login/OAuth stays inline — tightly coupled to oauth state dict
    _register_oauth(fapp)
    fapp.include_router(data.router)
    fapp.include_router(patients.router)
    fapp.include_router(gmail.router)
    fapp.include_router(guerilla_log.router)
    fapp.include_router(guerilla_boxes.router)
    fapp.include_router(guerilla_routes.router)
    fapp.include_router(social.router)
    fapp.include_router(events.router)
    fapp.include_router(pages.router)
    return fapp
```

Local dev becomes:

```python
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    local = FastAPI()
    _register_oauth(local)
    for m in (data, patients, gmail, guerilla_log, guerilla_boxes, guerilla_routes, social, events, pages):
        local.include_router(m.router)
    import uvicorn; uvicorn.run(local, host="0.0.0.0", port=8000)
```

That's the whole point — **one router module, two hosts**.

## Concrete Order of Operations

Do these **one router at a time**, deploying and running `python execution/diagnose.py` between each step. Don't batch — the whole gain is being able to verify incrementally.

1. **Create `hub/deps.py`** with the injectables above. Verify by importing in a Python REPL under `PYTHONUTF8=1`.
2. **Pick the smallest safe first target: `api/social.py`** (90 LOC, 2 endpoints). Move, verify, deploy. Confirm social page still loads.
3. **`api/gmail.py`** (143 LOC). Move, verify, deploy. Test compose + thread view.
4. **`api/events.py`** (227 LOC). Move, verify, deploy. Test lead form + events dashboard.
5. **`api/guerilla_boxes.py`** (160 LOC). Deploy, test box placement + pickup.
6. **`api/guerilla_routes.py`** (363 LOC — bigger risk). Deploy, test route creation, stop marking, both admin and field-rep paths.
7. **`api/guerilla_log.py`** (355 LOC — largest and highest risk because of the multipart flyer path). Deploy, test all 5 GFR forms from mobile, including one with a flyer photo.
8. **`api/data.py`, `api/patients.py`, `api/pages.py`** (lighter, collapse as one batch if steps 1-7 went clean).
9. **Delete the `__main__` duplicate** and replace with the `include_router` loop. Run `python execution/modal_outreach_hub.py` locally, confirm OAuth + one end-to-end flow works.
10. **Run full `python execution/diagnose.py`** — JS + env + live — after every step above. The JS checks catch template/HTML breakage; the live checks catch a dead endpoint.

## What Not to Move

- **Login / OAuth handlers** (lines 210-326) — inherently entry-point-level and tightly tied to `hub_oauth_states`. Keep inline or extract to a single `_register_oauth(fapp)` helper still in the main file.
- **`warm_cache` function** and `_WARM_TABLES` — Modal scheduled function, must live at module scope with `@app.function(schedule=...)`. Not a route.
- **`_fetch_table_all` / `_cached_table` / `hub_cache`** — infrastructure. Expose via `hub/deps.py` if routers need them; otherwise keep where they are.
- **Modal `app`, `image`, `Modal.Dict` declarations** — entry-point only.

## Gotchas

- `httpx.AsyncClient` was instantiated inside route handlers in the current code. When moving to APIRouter modules, either keep that pattern (one client per request) or introduce a shared client via lifespan + `Depends`. The former is simpler and matches current behavior — don't bundle the switch to shared clients into this refactor.
- `_refresh_if_needed` needs `hub_sessions` (for write-back of refreshed tokens). Expose from `hub/deps.py`.
- The `@fapp.patch("/api/patients/{stage}/{row_id}/firm")` endpoint uses `hub_cache.pop(...)` to invalidate cache on write. Same pattern repeats in several handlers — when moving to routers, make sure the cache dict is importable from `hub/deps.py` or `hub/cache.py`.
- URL path prefixes: the current routes use full paths (e.g. `/api/guerilla/routes/today`). `APIRouter(prefix="/api/guerilla/routes")` then `@router.get("/today")` composes to the same URL. Verify by `grep -n "@fapp\\." execution/modal_outreach_hub.py` before and then `grep -n "@router\\." execution/hub/api/*.py` after — the route set must match exactly.
- **Don't change response shapes during this refactor.** The frontend expects exact JSON keys; this is a move, not a rewrite.

## Verification After Each Step

```bash
cd "c:\\Users\\crazy\\Reform Workspace"

# Local import check
python -c "from execution.hub.api import social, gmail, events, guerilla_log"

# JS + function + env + live
python execution/diagnose.py

# Deploy
$env:PYTHONUTF8="1"; modal deploy execution/modal_outreach_hub.py

# Re-run live check against deployed hub
python execution/diagnose.py --live
```

Then walk the feature area you just moved in a browser. If anything 500s or a JSON shape changed, revert the single router and redo — do NOT try to patch forward when a batch move broke something.

## Rollback

Each step is one `APIRouter` module plus its include line. If a step breaks prod: delete the include_router line, delete the new module, and the original route (still in `modal_outreach_hub.py` because you didn't remove it yet) reactivates. **Only remove the original handler after the new one has been live for one deploy cycle and the live diagnostic passes.**

## Done-State Signals

The refactor is complete when:

- `wc -l execution/modal_outreach_hub.py` is under 500.
- `execution/hub/api/` exists and contains at least the routers listed above.
- The `if __name__ == "__main__":` block in `modal_outreach_hub.py` has no `@local_app.get/post/patch/delete` handlers — it only calls `include_router` against the same modules the Modal app uses.
- `python execution/diagnose.py` passes.
- Spot-check: one full flow per refactored area (guerilla log submission, route stop check-in, settlement add, lead form submission, gmail compose).
