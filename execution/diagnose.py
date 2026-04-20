#!/usr/bin/env python3
"""
Reform Workspace Diagnostic Tool
Runs fast, local-first checks to surface root causes without burning context.

Usage:
  python execution/diagnose.py            # all checks
  python execution/diagnose.py --js       # JS syntax + function inventory only
  python execution/diagnose.py --env      # env vars only
  python execution/diagnose.py --live     # live endpoint + Baserow checks only
"""

import os, sys, re, asyncio, time, ast
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent

def _ok(msg):    print(f"  \033[32mPASS\033[0m {msg}")
def _fail(msg):  print(f"  \033[31mFAIL\033[0m {msg}")
def _warn(msg):  print(f"  \033[33mWARN\033[0m {msg}")
def _info(msg):  print(f"  .... {msg}")
def _head(msg):  print(f"\n\033[1m{msg}\033[0m")

# ─────────────────────────────────────────────────────────────────────────────
# Source discovery — walk the hub package + entry point
# ─────────────────────────────────────────────────────────────────────────────

def _js_source_files() -> list[Path]:
    """Every Python file that may contain JS blocks.

    Post-refactor, page HTML/JS lives in execution/hub/*.py while the entry
    point (modal_outreach_hub.py) still hosts OAuth + a few inline scripts.
    """
    files = []
    entry = ROOT / "execution" / "modal_outreach_hub.py"
    if entry.exists():
        files.append(entry)
    hub_dir = ROOT / "execution" / "hub"
    if hub_dir.is_dir():
        files.extend(sorted(
            p for p in hub_dir.glob("*.py")
            if p.name != "__init__.py"
        ))
    return files


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


# ─────────────────────────────────────────────────────────────────────────────
# JS block extraction — handles plain, raw, and f-string triple-quoted blocks
# ─────────────────────────────────────────────────────────────────────────────

def _decode_pystr(text: str) -> str:
    """Apply Python string-literal escape processing (\\\\ → \\, \\' → ', \\n → LF,
    \\uXXXX → unicode, etc.) via ast.literal_eval. Returns text unchanged if
    escape processing would fail (e.g. trailing backslash)."""
    try:
        return ast.literal_eval('"""' + text + '"""')
    except Exception:
        return text


def _flatten_fstring(body: str, raw: bool = False) -> str:
    """Turn an f-string body into plain JS source:
      - {{  → literal {
      - }}  → literal }
      - {expr} → `null`, with expr's newline count preserved so any esprima
                 line numbers map back to the true source-file line.
      - Python escapes on literal segments are processed (\\\\ → \\, \\' → ',
        \\n → LF, \\uXXXX → unicode) so esprima sees the same text the
        browser receives — unless `raw=True`, in which case the literal
        segments are passed through unchanged (matches r\"\"\"...\"\"\" source).
    Known limitation: a closing `}` inside a string literal inside an
    expression will confuse the naive depth counter. Rare in practice.
    """
    segments = []           # list of ('lit', raw_text) | ('sub', 'null' + '\\n'*N)
    lit_buf: list[str] = []
    i, n = 0, len(body)

    def flush_lit():
        if lit_buf:
            segments.append(('lit', ''.join(lit_buf)))
            lit_buf.clear()

    while i < n:
        c = body[i]
        if c == '{':
            if i + 1 < n and body[i + 1] == '{':
                lit_buf.append('{')
                i += 2
                continue
            flush_lit()
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if body[j] == '{':
                    depth += 1
                elif body[j] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            expr = body[i + 1:j]
            segments.append(('sub', 'null' + '\n' * expr.count('\n')))
            i = j + 1
        elif c == '}':
            if i + 1 < n and body[i + 1] == '}':
                lit_buf.append('}')
                i += 2
                continue
            lit_buf.append('}')
            i += 1
        else:
            lit_buf.append(c)
            i += 1
    flush_lit()

    out = []
    for kind, text in segments:
        if kind == 'lit':
            out.append(text if raw else _decode_pystr(text))
        else:
            out.append(text)
    return ''.join(out)


# Single triple-quoted assignment. We keep every match and filter below; this
# avoids backtracking through huge HTML/CSS blocks.
_TRIPLE_RE = re.compile(
    r'(\b\w+)\s*=\s*([rRfF]{0,2})"""(.*?)"""',
    re.DOTALL,
)

# Matches `js` as a name-component (case-insensitive): js, route_js, map_js,
# _COMPOSE_JS, _JS_SHARED, _GFR_FORMS345_JS, etc.
_JS_NAME_RE = re.compile(r'(?:^|_)js(?:_|$)', re.IGNORECASE)

# Content sniff: lines that begin with unmistakably JS syntax. Catches named
# helper snippets (firm_counts_load, prev_rel_badge, etc.) that get
# interpolated into larger blocks — we need to syntax-check them directly
# because the outer block's f-string substitution wipes them out.
_JS_HINT_RE = re.compile(
    r'(?m)^\s*(?:function\s+\w|const\s+\w|let\s+\w|var\s+\w|async\s+function|if\s*\(|for\s*\(|Promise\.)'
)


def _is_js_block(name: str, body: str) -> bool:
    if _JS_NAME_RE.search(name):
        return True
    if _JS_HINT_RE.search(body):
        return True
    return False


_FORMAT_CALL_RE = re.compile(r'\b(\w+)\.format\s*\(')


def _find_format_targets(files: list[Path]) -> set[str]:
    """Return variable names that are used as `.format()` template strings
    anywhere in the given files. Those names' triple-quoted bodies need the
    same {{/}}/{name} flattening as f-strings.
    """
    targets = set()
    for p in files:
        try:
            targets.update(_FORMAT_CALL_RE.findall(p.read_text(encoding='utf-8')))
        except Exception:
            continue
    return targets


def _extract_js_blocks_from_file(path: Path, format_targets: set[str]) -> list[dict]:
    """Return one dict per JS block in the file.

    Dict shape:
      file         Path
      label        variable name (e.g. '_COMPOSE_JS', 'js')
      kind         'plain' | 'raw' | 'f-string' | 'format'
      start_line   1-based file line where the block body begins (line of
                   the opening \"\"\"). esprima line N → file line
                   start_line + N - 1.
      code         JS source fed to esprima
    """
    try:
        source = path.read_text(encoding='utf-8')
    except Exception:
        return []

    blocks = []
    for m in _TRIPLE_RE.finditer(source):
        name = m.group(1)
        prefix = m.group(2).lower()
        body = m.group(3)
        if not _is_js_block(name, body):
            continue
        start_line = source[:m.start(3)].count('\n') + 1

        if 'f' in prefix:
            code = _flatten_fstring(body, raw=False)
            kind = 'f-string'
        elif name in format_targets:
            # String fed to .format() elsewhere — uses the same {{/}}/{name}
            # placeholder grammar as an f-string. Raw + format is valid and
            # common (raw avoids doubling backslashes inside the template).
            code = _flatten_fstring(body, raw=('r' in prefix))
            kind = 'format'
        elif 'r' in prefix:
            code = body
            kind = 'raw'
        else:
            code = _decode_pystr(body)
            kind = 'plain'

        blocks.append({
            'file': path,
            'label': name,
            'kind': kind,
            'start_line': start_line,
            'code': code,
        })
    return blocks


def _extract_all_js_blocks() -> list[dict]:
    files = _js_source_files()
    format_targets = _find_format_targets(files)
    blocks = []
    for p in files:
        blocks.extend(_extract_js_blocks_from_file(p, format_targets))
    return blocks


# ─────────────────────────────────────────────────────────────────────────────
# 1. JS Syntax Check
# ─────────────────────────────────────────────────────────────────────────────

def check_js_syntax(blocks: list[dict]) -> bool:
    _head("[1] JS Syntax Check")

    try:
        import esprima
    except ImportError:
        _warn("esprima not installed — run: pip install esprima")
        return True

    if not blocks:
        _warn("No JS blocks found in source")
        return True

    by_kind = {}
    for b in blocks:
        by_kind[b['kind']] = by_kind.get(b['kind'], 0) + 1
    kind_summary = ", ".join(f"{k}: {v}" for k, v in sorted(by_kind.items()))
    files = {b['file'] for b in blocks}
    _info(f"Checking {len(blocks)} JS block(s) across {len(files)} file(s) ({kind_summary})")

    failures = []
    for b in blocks:
        try:
            esprima.parseScript(b['code'], tolerant=False)
        except Exception as e:
            failures.append((b, e))

    if not failures:
        _ok(f"All {len(blocks)} blocks parsed cleanly")
        return True

    for b, e in failures:
        line_no = getattr(e, 'lineNumber', None)
        desc = getattr(e, 'description', str(e))
        file_line = (b['start_line'] + line_no - 1) if line_no else None
        loc = f"{_rel(b['file'])}:{file_line}" if file_line else _rel(b['file'])
        _fail(f"{loc} — {b['label']} ({b['kind']}): {desc}")
        if line_no:
            code_lines = b['code'].splitlines()
            start = max(0, line_no - 3)
            end = min(len(code_lines), line_no + 2)
            for i, ln in enumerate(code_lines[start:end], start=start + 1):
                marker = ">>>" if i == line_no else "   "
                color = "\033[31m" if i == line_no else "\033[90m"
                abs_line = b['start_line'] + i - 1
                print(f"       {color}{marker} {abs_line:5d} | {ln}\033[0m")

    return False


# ─────────────────────────────────────────────────────────────────────────────
# 2. JS Function Inventory
# ─────────────────────────────────────────────────────────────────────────────

_FN_DEF_RE = re.compile(r'\bfunction\s+(\w+)\s*\(')
_ARROW_RE = re.compile(r'\b(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(')
_HTML_CALL_RE = re.compile(r'\bon\w+=["\']([a-zA-Z_]\w*)\s*\(')


def check_js_functions(blocks: list[dict]) -> bool:
    _head("[2] JS Function Inventory")

    defined = set()
    referenced = set()

    # Definitions: scan both flattened JS code *and* raw source (to catch
    # functions defined inside single-quoted string concatenations — e.g.
    # 'function openDrawer(){...}' in shells.py's _topnav).
    for b in blocks:
        defined.update(_FN_DEF_RE.findall(b['code']))
        defined.update(_ARROW_RE.findall(b['code']))

    for p in _js_source_files():
        try:
            src = p.read_text(encoding='utf-8')
        except Exception:
            continue
        defined.update(_FN_DEF_RE.findall(src))
        defined.update(_ARROW_RE.findall(src))
        referenced.update(_HTML_CALL_RE.findall(src))

    _info(f"{len(defined)} functions defined, {len(referenced)} referenced in HTML event attrs")

    builtins = {
        'alert', 'confirm', 'fetch', 'JSON', 'parseInt', 'parseFloat',
        'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
        'console', 'document', 'window', 'event', 'Promise', 'FormData',
        'Object', 'Array', 'if', 'return', 'this', 'getElementById',
        'querySelector', 'classList', 'addEventListener',
    }
    missing = referenced - defined - builtins

    if missing:
        for fn in sorted(missing):
            _warn(f"Referenced but not found in JS: {fn}()")
        return True  # warn-only; could be browser APIs or scripts injected elsewhere
    _ok("All HTML-referenced functions found in JS blocks")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 3. f-string JS Escape Check
# ─────────────────────────────────────────────────────────────────────────────

def check_fstring_escapes() -> bool:
    """Bare `\\'` inside an f-string JS block gets collapsed to `'` by Python,
    breaking any JS string literal that expected an escaped quote.

    Correct form: `\\\\'` in the Python source → `\\'` in the JS output.
    """
    _head("[3] f-string JS Escape Check")

    issues = []
    total_blocks = 0

    for p in _js_source_files():
        try:
            source = p.read_text(encoding='utf-8')
        except Exception:
            continue
        for m in _TRIPLE_RE.finditer(source):
            name = m.group(1)
            prefix = m.group(2).lower()
            if not _is_js_block(name, m.group(3)) or 'f' not in prefix:
                continue
            total_blocks += 1
            body = m.group(3)
            block_start = source[:m.start(3)].count('\n') + 1
            for i, line in enumerate(body.splitlines(), start=0):
                abs_line = block_start + i
                # Bare \' (bad) but not \\' (ok — produces \' in JS output)
                if re.search(r"(?<!\\)\\(?!\\)'", line):
                    issues.append((p, abs_line, line.strip()))

    if not total_blocks:
        _info("No f-string JS blocks found — skipping")
        return True

    _info(f"Scanned {total_blocks} f-string JS block(s)")

    if issues:
        for path, line_no, line_text in issues:
            _warn(f"{_rel(path)}:{line_no} — bare \\' in f-string JS (use \\\\\\\\' to emit \\' in JS)")
            print(f"         \033[90m{line_text[:100]}\033[0m")
        return False
    _ok("No bare \\' found in f-string JS blocks")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 5. Environment Variables
# ─────────────────────────────────────────────────────────────────────────────

def check_env() -> bool:
    _head("[5] Environment Variables")

    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    REQUIRED = {
        "Hub": [
            "BASEROW_URL",
            "BASEROW_API_TOKEN",
            "BUNNY_STORAGE_API_KEY",
            "BUNNY_STORAGE_ZONE",
            "BUNNY_CDN_BASE",
            "BUNNY_ACCOUNT_API_KEY",
        ],
        "Shotstack Worker": [
            "SHOTSTACK_SANDBOX_API_KEY",
            "BUNNY_STORAGE_API_KEY",
            "N8N_WEBHOOK_URL",
            "N8N_WEBHOOK_TOKEN",
        ],
    }

    OPTIONAL = [
        "SHOTSTACK_PRODUCTION_API_KEY",
        "GOOGLE_MAPS_API_KEY",
        "HUB_CLIENT_ID",
        "HUB_CLIENT_SECRET",
        "HUB_ALLOWED_DOMAIN",
        "SLACK_WEBHOOK_URL",
        "BUNNY_STORAGE_REGION",
    ]

    all_ok = True
    for group, keys in REQUIRED.items():
        _info(f"--- {group} ---")
        for k in keys:
            v = os.environ.get(k, "")
            if v:
                masked = v[:4] + "****" if len(v) > 4 else "****"
                _ok(f"{k} = {masked}")
            else:
                _fail(f"{k} MISSING")
                all_ok = False

    _info("--- Optional ---")
    for k in OPTIONAL:
        v = os.environ.get(k, "")
        if v:
            _ok(f"{k} set")
        else:
            _warn(f"{k} not set")

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# 6. Live Endpoint & Baserow Checks
# ─────────────────────────────────────────────────────────────────────────────

async def check_live() -> bool:
    _head("[6] Live Endpoint & Baserow Checks")

    try:
        import httpx
    except ImportError:
        _warn("httpx not installed — skipping live checks (pip install httpx)")
        return True

    all_ok = True
    HUB = "https://reformtechops--outreach-hub-web.modal.run"
    br = os.environ.get("BASEROW_URL", "")
    bt = os.environ.get("BASEROW_API_TOKEN", "")

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        # Hub ping
        try:
            r = await client.get(f"{HUB}/login")
            if r.status_code == 200:
                _ok(f"Hub /login → {r.status_code} ({r.elapsed.total_seconds():.2f}s)")
            else:
                _fail(f"Hub /login → {r.status_code}")
                all_ok = False
        except Exception as e:
            _fail(f"Hub unreachable: {e}")
            all_ok = False

        # Baserow auth + key tables
        if br and bt:
            KEY_TABLES = [
                ("T_ATT_VENUES", 768),
                ("T_ATT_ACTS",   784),
                ("T_GOR_VENUES", 790),
                ("T_GOR_ACTS",   791),
                ("T_COM_VENUES", 797),
                ("T_COM_ACTS",   798),
                ("T_GOR_BOXES",  800),
                ("T_GOR_ROUTES", 801),
                ("T_GOR_STOPS",  802),
                ("T_PI_ACTIVE",  775),
                ("T_PI_BILLED",  773),
                ("T_PI_AWAITING", 776),
                ("T_PI_CLOSED",  772),
                ("T_PI_FINANCE", 781),
            ]
            first = True
            for name, tid in KEY_TABLES:
                try:
                    r = await client.get(
                        f"{br}/api/database/rows/table/{tid}/",
                        params={"size": 1, "user_field_names": "true"},
                        headers={"Authorization": f"Token {bt}"}
                    )
                    if r.status_code == 200:
                        ct = r.json().get("count", "?")
                        prefix = "Baserow auth OK — " if first else ""
                        _ok(f"{prefix}{name} ({tid}): {ct} rows")
                        first = False
                    elif r.status_code == 401:
                        _fail(f"Baserow token invalid (401)")
                        all_ok = False
                        break
                    else:
                        _fail(f"Baserow {name}: {r.status_code}")
                        all_ok = False
                except Exception as e:
                    _fail(f"Baserow {name}: {e}")
                    all_ok = False
        else:
            _warn("Skipping Baserow checks — BASEROW_URL or BASEROW_API_TOKEN not set")

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    from datetime import datetime
    print(f"\033[1mReform Workspace Diagnostics\033[0m — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    args = set(sys.argv[1:])
    run_js   = not args or '--js'   in args or '--all' in args
    run_env  = not args or '--env'  in args or '--all' in args
    run_live = not args or '--live' in args or '--all' in args

    results: dict[str, bool] = {}
    t0 = time.time()

    if run_js:
        blocks = _extract_all_js_blocks()
        results["js_syntax"]       = check_js_syntax(blocks)
        results["js_functions"]    = check_js_functions(blocks)
        results["fstring_escapes"] = check_fstring_escapes()

    if run_env:
        results["env"] = check_env()

    if run_live:
        results["live"] = await check_live()

    elapsed = time.time() - t0

    print(f"\n{'=' * 60}")
    print(f"\033[1mSummary\033[0m  ({elapsed:.1f}s)")
    any_fail = False
    for k, v in results.items():
        icon = "\033[32mPASS\033[0m" if v else "\033[31mFAIL\033[0m"
        print(f"  {k:<20} {icon}")
        if not v:
            any_fail = True

    if any_fail:
        print("\n\033[31mIssues found — see above for details.\033[0m")
    else:
        print("\n\033[32mAll checks passed.\033[0m")

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    asyncio.run(main())
