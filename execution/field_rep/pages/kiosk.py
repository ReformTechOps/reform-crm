"""Kiosk-mode pages.

  /kiosk/setup           — staff-auth; pick event + consents + PIN, then start
  /kiosk/run/{kiosk_id}  — public; locked-down lead capture + consent walkthrough

The setup page reuses _mobile_page (drawer included). The run page uses its own
minimal shell (no drawer, no hamburger, no auth UI) so the device handed to the
public can't navigate away. PIN modal in the corner is the only escape hatch.
"""

from hub.shared import (
    _mobile_page,
    T_EVENTS, T_CONSENT_FORMS,
)
from hub.styles import _CSS, _JS_SHARED


def _mobile_kiosk_setup_page(br: str, bt: str, user: dict | None = None) -> str:
    user = user or {}
    body = (
        '<div class="mobile-hdr">'
        '<div><div class="mobile-hdr-title">Start kiosk</div>'
        '<div class="mobile-hdr-sub">Hand the device to leads</div></div>'
        '<button class="m-hamburger" onclick="openMDrawer()" aria-label="Menu">☰</button>'
        '</div>'
        '<div class="mobile-body">'
        '<div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;'
        'margin-bottom:14px;font-size:13px;color:var(--text2);line-height:1.45">'
        'Pick the event, choose which consents the lead should sign, and set a 4-digit PIN. '
        'You will need the PIN to exit kiosk mode.'
        '</div>'
        # Event picker
        '<label style="display:block;font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;'
        'margin-bottom:4px">Event</label>'
        '<select id="ks-event" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;margin-bottom:14px">'
        '<option value="">Loading events…</option></select>'
        # Consent picker (loaded async)
        '<label style="display:block;font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;'
        'margin-bottom:4px">Consent forms to collect</label>'
        '<div id="ks-consents" style="background:var(--card);border:1px solid var(--border);border-radius:8px;'
        'padding:8px 12px;font-size:13px;color:var(--text3);min-height:60px;margin-bottom:14px">'
        'Loading consent forms…</div>'
        # PIN
        '<label style="display:block;font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;'
        'margin-bottom:4px">Exit PIN (4 digits)</label>'
        '<input id="ks-pin" type="tel" inputmode="numeric" pattern="[0-9]*" maxlength="4" '
        'placeholder="0000" autocomplete="off" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:18px;letter-spacing:6px;text-align:center;'
        'margin-bottom:14px;font-family:monospace">'
        '<button id="ks-start" onclick="startKiosk()" '
        'style="width:100%;background:#004ac6;color:#fff;border:none;border-radius:8px;'
        'padding:14px;font-size:15px;font-weight:700;cursor:pointer;min-height:48px">'
        'Start kiosk</button>'
        '<div id="ks-msg" style="margin-top:10px;font-size:13px;text-align:center;min-height:18px"></div>'
        '</div>'
    )

    js = f"""
const T_EVENTS = {T_EVENTS};
const T_CONSENT_FORMS = {T_CONSENT_FORMS};
const _ACTIVE_ST = ['Prospective','Maybe','Approved','Scheduled'];

function esc(s) {{
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}}

async function loadEvents() {{
  var sel = document.getElementById('ks-event');
  try {{
    var rows = await fetchAll(T_EVENTS);
    var today = new Date().toISOString().slice(0, 10);
    rows = rows.filter(function(e) {{
      var d = e['Event Date'] || '';
      var st = (e['Event Status'] && e['Event Status'].value) || e['Event Status'] || '';
      var futureOrToday = !d || d >= today;
      var activeStatus = !st || _ACTIVE_ST.indexOf(st) >= 0;
      return futureOrToday && activeStatus;
    }});
    rows.sort(function(a, b) {{ return (a['Event Date']||'').localeCompare(b['Event Date']||''); }});
    if (!rows.length) {{
      sel.innerHTML = '<option value="">No active events</option>';
      return;
    }}
    var html = '<option value="">— pick an event —</option>';
    rows.forEach(function(e) {{
      var nm = e['Name'] || '(unnamed)';
      var dt = e['Event Date'] || '';
      html += '<option value="'+e.id+'" data-name="'+esc(nm)+'">'+esc(nm)+(dt?' ('+esc(dt)+')':'')+'</option>';
    }});
    sel.innerHTML = html;
  }} catch (e) {{
    sel.innerHTML = '<option value="">Failed to load events</option>';
  }}
}}

async function loadConsents() {{
  var box = document.getElementById('ks-consents');
  try {{
    var rows = await fetchAll(T_CONSENT_FORMS);
    rows = rows.filter(function(f) {{ return f['Active'] !== false && f['Slug']; }});
    if (!rows.length) {{
      box.innerHTML = '<div style="color:var(--text3);font-size:12px;padding:6px 0">No active consent forms in the catalog.</div>';
      return;
    }}
    rows.sort(function(a, b) {{ return (a['Display Name']||'').localeCompare(b['Display Name']||''); }});
    var html = '';
    rows.forEach(function(f) {{
      var slug = f['Slug'];
      var nm = f['Display Name'] || slug;
      html += '<label style="display:flex;align-items:center;gap:8px;padding:6px 0;font-size:14px;color:var(--text);cursor:pointer">'
           + '<input type="checkbox" data-consent-slug="'+esc(slug)+'" '
           + 'style="width:18px;height:18px;accent-color:#004ac6">'
           + esc(nm) + '</label>';
    }});
    box.innerHTML = html;
  }} catch (e) {{
    box.innerHTML = '<div style="color:#ef4444;font-size:12px">Failed to load consent forms.</div>';
  }}
}}

async function startKiosk() {{
  var msg = document.getElementById('ks-msg');
  var btn = document.getElementById('ks-start');
  msg.textContent = '';
  var sel = document.getElementById('ks-event');
  var eventId = parseInt(sel.value || '0', 10);
  var eventName = sel.options[sel.selectedIndex] && sel.options[sel.selectedIndex].getAttribute('data-name') || '';
  var pin = (document.getElementById('ks-pin').value || '').replace(/\\D/g, '');
  var slugs = [];
  document.querySelectorAll('[data-consent-slug]').forEach(function(el) {{
    if (el.checked) slugs.push(el.getAttribute('data-consent-slug'));
  }});
  if (!eventId) {{ msg.style.color = '#ef4444'; msg.textContent = 'Pick an event.'; return; }}
  if (pin.length < 4 || pin.length > 6) {{
    msg.style.color = '#ef4444'; msg.textContent = 'PIN must be 4-6 digits.'; return;
  }}
  btn.disabled = true; btn.textContent = 'Starting…';
  try {{
    var r = await fetch('/api/kiosk/start', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        event_id: eventId,
        event_name: eventName,
        consent_slugs: slugs,
        pin: pin,
      }}),
    }});
    var data = await r.json().catch(function(){{return{{}};}});
    if (!r.ok || !data.ok) {{
      msg.style.color = '#ef4444';
      msg.textContent = data.error || ('HTTP ' + r.status);
      btn.disabled = false; btn.textContent = 'Start kiosk';
      return;
    }}
    window.location.href = '/kiosk/run/' + encodeURIComponent(data.kiosk_id);
  }} catch (e) {{
    msg.style.color = '#ef4444';
    msg.textContent = 'Network error.';
    btn.disabled = false; btn.textContent = 'Start kiosk';
  }}
}}

loadEvents();
loadConsents();
"""
    return _mobile_page('m_kiosk', 'Start kiosk', body, js, br, bt, user=user)


# ─── Public kiosk-run page ──────────────────────────────────────────────────
# Uses a stripped shell. No drawer, no hamburger, no PWA install nag — just
# the lead form + consent walkthrough. The PIN exit modal is the only nav.

def _kiosk_run_page(br: str, bt: str, kiosk_id: str) -> str:
    """Public-facing kiosk page. The kiosk_id IS the bearer token; anyone
    with the URL gets the public state but nothing destructive without PIN."""
    shared_js = _JS_SHARED.format(br=br, bt=bt)

    body = f"""
<div class="kiosk-frame">
  <div class="kiosk-topbar">
    <div class="kiosk-event" id="ks-event-name">Loading…</div>
    <button class="kiosk-exit" onclick="openExitModal()" aria-label="Exit kiosk">Exit</button>
  </div>

  <!-- Lead capture card -->
  <div id="ks-step-lead" class="kiosk-step">
    <h2>Welcome — tell us about you</h2>
    <p class="kiosk-help">Your information goes straight to the office. Required fields marked *.</p>
    <label>Full name *</label>
    <input id="kl-name" type="text" autocomplete="name" required>
    <label>Phone *</label>
    <input id="kl-phone" type="tel" inputmode="tel" autocomplete="tel" required>
    <label>Email</label>
    <input id="kl-email" type="email" inputmode="email" autocomplete="email">
    <label>What can we help with?</label>
    <input id="kl-reason" type="text" placeholder="Massage, back pain, free chair massage, etc.">
    <label>Anything else?</label>
    <textarea id="kl-notes" rows="2"></textarea>
    <button id="kl-submit" class="kiosk-btn-primary" onclick="submitKioskLead()">Continue &rarr;</button>
    <div id="kl-msg" class="kiosk-msg"></div>
  </div>

  <!-- Consent steps (rendered dynamically) -->
  <div id="ks-step-consent" class="kiosk-step" style="display:none"></div>

  <!-- Done -->
  <div id="ks-step-done" class="kiosk-step kiosk-done" style="display:none">
    <div class="kiosk-check">&#10003;</div>
    <h2>Thanks!</h2>
    <p>You're all set. Someone from Reform Chiropractic will be in touch shortly.</p>
    <p class="kiosk-help" id="ks-done-sub">Resetting in <span id="ks-done-cd">3</span>s…</p>
  </div>

  <!-- Exit PIN modal -->
  <div id="ks-exit-bg" class="kiosk-modal-bg" style="display:none" onclick="if(event.target===this)closeExitModal()">
    <div class="kiosk-modal">
      <h3>Enter exit PIN</h3>
      <input id="ks-exit-pin" type="tel" inputmode="numeric" pattern="[0-9]*" maxlength="6"
             placeholder="0000" autocomplete="off">
      <div class="kiosk-modal-actions">
        <button class="kiosk-btn-secondary" onclick="closeExitModal()">Cancel</button>
        <button class="kiosk-btn-primary" onclick="confirmExit()">Exit kiosk</button>
      </div>
      <div id="ks-exit-msg" class="kiosk-msg"></div>
    </div>
  </div>
</div>
"""

    css_extra = """
html, body { margin:0; padding:0; background:#0f172a; min-height:100vh; -webkit-text-size-adjust:100%; }
* { box-sizing:border-box; }
.kiosk-frame {
  min-height:100vh; max-width:720px; margin:0 auto; padding:0 0 24px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  color:#e5e7eb;
}
.kiosk-topbar {
  display:flex; align-items:center; gap:12px; padding:14px 18px;
  background:#1e293b; border-bottom:1px solid #334155; position:sticky; top:0; z-index:5;
}
.kiosk-event { flex:1; font-size:15px; font-weight:700; color:#fff; min-width:0;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.kiosk-exit {
  background:transparent; color:#94a3b8; border:1px solid #475569; border-radius:6px;
  padding:6px 10px; font-size:12px; cursor:pointer; font-family:inherit;
}
.kiosk-step { padding:20px 18px; }
.kiosk-step h2 { font-size:22px; margin:0 0 10px; color:#fff; }
.kiosk-help { font-size:14px; color:#94a3b8; margin:0 0 18px; line-height:1.5; }
.kiosk-step label {
  display:block; font-size:12px; font-weight:700; text-transform:uppercase;
  letter-spacing:.5px; color:#94a3b8; margin:14px 0 6px;
}
.kiosk-step input, .kiosk-step textarea {
  width:100%; padding:14px 16px; background:#1e293b; border:1px solid #334155;
  color:#fff; border-radius:10px; font-size:18px; font-family:inherit; outline:none;
}
.kiosk-step input:focus, .kiosk-step textarea:focus { border-color:#ea580c; }
.kiosk-step textarea { resize:vertical; min-height:60px; }
.kiosk-btn-primary {
  width:100%; margin-top:24px; background:#ea580c; color:#fff; border:none;
  border-radius:10px; padding:18px; font-size:18px; font-weight:700; cursor:pointer;
  min-height:56px; font-family:inherit;
}
.kiosk-btn-primary:disabled { opacity:.5; cursor:not-allowed; }
.kiosk-btn-secondary {
  background:transparent; color:#cbd5e1; border:1px solid #475569; border-radius:10px;
  padding:14px 18px; font-size:15px; font-weight:600; cursor:pointer; font-family:inherit;
}
.kiosk-msg { margin-top:12px; font-size:14px; min-height:18px; text-align:center; }
.kiosk-consent-body {
  background:#1e293b; border:1px solid #334155; border-radius:10px;
  padding:16px 18px; max-height:50vh; overflow-y:auto; font-size:15px;
  line-height:1.55; color:#e5e7eb; margin-bottom:18px; white-space:pre-wrap;
  -webkit-overflow-scrolling:touch;
}
.kiosk-consent-body h1, .kiosk-consent-body h2, .kiosk-consent-body h3 {
  margin-top:0; color:#fff;
}
.kiosk-sig-wrap {
  background:#fff; border:2px solid #334155; border-radius:10px;
  height:160px; touch-action:none; position:relative; margin-top:8px;
}
.kiosk-sig-wrap canvas { width:100%; height:100%; display:block; cursor:crosshair; }
.kiosk-sig-clear {
  position:absolute; top:6px; right:6px; background:#ef4444; color:#fff;
  border:none; border-radius:6px; padding:4px 10px; font-size:11px; cursor:pointer;
  font-family:inherit;
}
.kiosk-done { text-align:center; padding-top:60px; }
.kiosk-check {
  display:inline-flex; align-items:center; justify-content:center;
  width:72px; height:72px; border-radius:50%; background:#22c55e; color:#fff;
  font-size:42px; margin-bottom:18px; font-weight:700;
}
.kiosk-modal-bg {
  position:fixed; inset:0; background:rgba(0,0,0,.7); display:flex;
  align-items:center; justify-content:center; padding:20px; z-index:50;
}
.kiosk-modal {
  background:#1e293b; border:1px solid #334155; border-radius:14px;
  padding:24px; width:100%; max-width:360px;
}
.kiosk-modal h3 { margin:0 0 14px; color:#fff; font-size:18px; }
.kiosk-modal input {
  width:100%; padding:14px; background:#0f172a; border:1px solid #475569;
  color:#fff; border-radius:8px; font-size:24px; text-align:center;
  letter-spacing:8px; font-family:monospace; outline:none;
}
.kiosk-modal-actions {
  display:flex; gap:10px; margin-top:16px; justify-content:flex-end;
}
"""

    page_js = f"""
const KIOSK_ID = {kiosk_id!r};
let _consentForms = [];
let _currentIdx = 0;
let _capturedLeadId = null;

function esc(s) {{
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}}

function showStep(name) {{
  ['lead','consent','done'].forEach(function(s) {{
    var el = document.getElementById('ks-step-' + s);
    if (el) el.style.display = (s === name) ? '' : 'none';
  }});
}}

async function loadKiosk() {{
  try {{
    var r = await fetch('/api/kiosk/' + encodeURIComponent(KIOSK_ID));
    if (!r.ok) {{
      document.getElementById('ks-event-name').textContent = 'Kiosk session not found';
      document.body.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#fff;font-family:system-ui">'
        + '<h2>This kiosk session is no longer active.</h2>'
        + '<p style="color:#94a3b8;margin-top:10px">Ask a Reform staff member to start a new one.</p></div>';
      return;
    }}
    var data = await r.json();
    document.getElementById('ks-event-name').textContent = data.event_name || 'Reform Chiropractic';
    _consentForms = data.consent_forms || [];
    resetForm();
  }} catch (e) {{
    document.getElementById('ks-event-name').textContent = 'Connection error';
  }}
}}

function resetForm() {{
  ['kl-name','kl-phone','kl-email','kl-reason','kl-notes'].forEach(function(id) {{
    var el = document.getElementById(id); if (el) el.value = '';
  }});
  _capturedLeadId = null;
  _currentIdx = 0;
  document.getElementById('kl-msg').textContent = '';
  var btn = document.getElementById('kl-submit');
  btn.disabled = false; btn.textContent = 'Continue →';
  showStep('lead');
}}

async function submitKioskLead() {{
  var msg = document.getElementById('kl-msg');
  var btn = document.getElementById('kl-submit');
  msg.textContent = '';
  var get = function(id) {{ return (document.getElementById(id).value || '').trim(); }};
  var name = get('kl-name'), phone = get('kl-phone'), email = get('kl-email');
  if (!name || !phone) {{
    msg.style.color = '#ef4444'; msg.textContent = 'Name and phone are required.';
    return;
  }}
  btn.disabled = true; btn.textContent = 'Saving…';
  try {{
    var r = await fetch('/api/kiosk/' + encodeURIComponent(KIOSK_ID) + '/lead', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        name: name, phone: phone, email: email,
        reason: get('kl-reason'), notes: get('kl-notes'),
      }}),
    }});
    var data = await r.json().catch(function(){{return{{}};}});
    if (!r.ok || !data.ok) {{
      msg.style.color = '#ef4444';
      msg.textContent = data.error || ('HTTP ' + r.status);
      btn.disabled = false; btn.textContent = 'Continue →';
      return;
    }}
    _capturedLeadId = data.row && data.row.id;
    if (!_consentForms.length) {{
      finishKiosk();
    }} else {{
      _currentIdx = 0;
      renderConsent();
    }}
  }} catch (e) {{
    msg.style.color = '#ef4444';
    msg.textContent = 'Network error.';
    btn.disabled = false; btn.textContent = 'Continue →';
  }}
}}

function renderConsent() {{
  var form = _consentForms[_currentIdx];
  if (!form) {{ finishKiosk(); return; }}
  var box = document.getElementById('ks-step-consent');
  var stepStr = '(' + (_currentIdx + 1) + ' of ' + _consentForms.length + ')';
  box.innerHTML =
    '<h2>' + esc(form.name) + ' <span style="font-size:14px;color:#94a3b8;font-weight:400">' + esc(stepStr) + '</span></h2>'
    + '<div class="kiosk-consent-body">' + esc(form.body) + '</div>'
    + '<label>Type your full name to sign</label>'
    + '<input id="kc-name" type="text" placeholder="Your full legal name" autocomplete="name">'
    + '<label>Sign below</label>'
    + '<div class="kiosk-sig-wrap"><canvas id="kc-sig"></canvas>'
    + '<button class="kiosk-sig-clear" onclick="clearSig()">Clear</button></div>'
    + '<button class="kiosk-btn-primary" id="kc-submit" onclick="submitConsent()">I agree &amp; sign</button>'
    + '<div id="kc-msg" class="kiosk-msg"></div>';
  showStep('consent');
  initSignaturePad();
}}

let _sigCtx = null, _sigCanvas = null, _sigDrawing = false, _sigHasInk = false;
function initSignaturePad() {{
  _sigCanvas = document.getElementById('kc-sig');
  if (!_sigCanvas) return;
  // Match canvas pixel size to its rendered size for crisp lines.
  var dpr = window.devicePixelRatio || 1;
  var rect = _sigCanvas.getBoundingClientRect();
  _sigCanvas.width = Math.floor(rect.width * dpr);
  _sigCanvas.height = Math.floor(rect.height * dpr);
  _sigCtx = _sigCanvas.getContext('2d');
  _sigCtx.scale(dpr, dpr);
  _sigCtx.lineWidth = 2.2;
  _sigCtx.lineCap = 'round';
  _sigCtx.strokeStyle = '#000';
  _sigHasInk = false;

  function pos(e) {{
    var r = _sigCanvas.getBoundingClientRect();
    var t = e.touches ? e.touches[0] : e;
    return {{ x: t.clientX - r.left, y: t.clientY - r.top }};
  }}
  function start(e) {{ e.preventDefault(); _sigDrawing = true; var p = pos(e); _sigCtx.beginPath(); _sigCtx.moveTo(p.x, p.y); }}
  function move(e) {{ if (!_sigDrawing) return; e.preventDefault(); var p = pos(e); _sigCtx.lineTo(p.x, p.y); _sigCtx.stroke(); _sigHasInk = true; }}
  function end(e) {{ if (e) e.preventDefault(); _sigDrawing = false; }}

  _sigCanvas.addEventListener('pointerdown', start);
  _sigCanvas.addEventListener('pointermove', move);
  _sigCanvas.addEventListener('pointerup', end);
  _sigCanvas.addEventListener('pointerleave', end);
}}

function clearSig() {{
  if (!_sigCtx || !_sigCanvas) return;
  var dpr = window.devicePixelRatio || 1;
  _sigCtx.clearRect(0, 0, _sigCanvas.width / dpr, _sigCanvas.height / dpr);
  _sigHasInk = false;
}}

async function submitConsent() {{
  var msg = document.getElementById('kc-msg');
  var btn = document.getElementById('kc-submit');
  msg.textContent = '';
  var name = (document.getElementById('kc-name').value || '').trim();
  if (!name) {{ msg.style.color = '#ef4444'; msg.textContent = 'Please type your name.'; return; }}
  if (!_sigHasInk) {{ msg.style.color = '#ef4444'; msg.textContent = 'Please sign in the box above.'; return; }}
  var dataUrl = _sigCanvas.toDataURL('image/png');
  var form = _consentForms[_currentIdx];
  btn.disabled = true; btn.textContent = 'Submitting…';
  try {{
    var r = await fetch('/api/kiosk/' + encodeURIComponent(KIOSK_ID) + '/consent', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        lead_id: _capturedLeadId,
        consent_form_id: form.id,
        form_slug: form.slug,
        form_version: form.version,
        signed_name: name,
        signature_data_url: dataUrl,
        payload: {{ typed_name: name, kiosk_id: KIOSK_ID }},
      }}),
    }});
    var data = await r.json().catch(function(){{return{{}};}});
    if (!r.ok || !data.ok) {{
      msg.style.color = '#ef4444';
      msg.textContent = data.error || ('HTTP ' + r.status);
      btn.disabled = false; btn.textContent = 'I agree & sign';
      return;
    }}
    _currentIdx += 1;
    if (_currentIdx >= _consentForms.length) {{
      finishKiosk();
    }} else {{
      renderConsent();
    }}
  }} catch (e) {{
    msg.style.color = '#ef4444';
    msg.textContent = 'Network error.';
    btn.disabled = false; btn.textContent = 'I agree & sign';
  }}
}}

function finishKiosk() {{
  showStep('done');
  var cd = 3;
  var cdEl = document.getElementById('ks-done-cd');
  if (cdEl) cdEl.textContent = String(cd);
  var iv = setInterval(function() {{
    cd -= 1;
    if (cdEl) cdEl.textContent = String(Math.max(0, cd));
    if (cd <= 0) {{ clearInterval(iv); resetForm(); }}
  }}, 1000);
}}

// ── Exit modal ────────────────────────────────────────────────────────────
function openExitModal() {{
  var bg = document.getElementById('ks-exit-bg');
  document.getElementById('ks-exit-pin').value = '';
  document.getElementById('ks-exit-msg').textContent = '';
  bg.style.display = 'flex';
  setTimeout(function(){{
    var el = document.getElementById('ks-exit-pin'); if (el) el.focus();
  }}, 50);
}}
function closeExitModal() {{
  document.getElementById('ks-exit-bg').style.display = 'none';
}}
async function confirmExit() {{
  var msg = document.getElementById('ks-exit-msg');
  var pin = (document.getElementById('ks-exit-pin').value || '').replace(/\\D/g, '');
  if (!pin) {{ msg.style.color = '#ef4444'; msg.textContent = 'Enter the PIN.'; return; }}
  try {{
    var r = await fetch('/api/kiosk/exit', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ kiosk_id: KIOSK_ID, pin: pin }}),
    }});
    if (!r.ok) {{
      msg.style.color = '#ef4444'; msg.textContent = 'Wrong PIN.';
      return;
    }}
    window.location.href = '/';
  }} catch (e) {{
    msg.style.color = '#ef4444'; msg.textContent = 'Network error.';
  }}
}}

// Phone auto-format on the lead capture phone input (replicated from
// _mobile_page since this page bypasses that shell).
document.addEventListener('input', function(e) {{
  var t = e.target;
  if (!t || t.tagName !== 'INPUT' || t.type !== 'tel') return;
  if (t.id === 'ks-exit-pin') return;  // PIN: digits only, no formatting
  var d = (t.value || '').replace(/\\D/g, '').slice(0, 10);
  var f = d;
  if (d.length > 6) f = '(' + d.slice(0,3) + ')' + d.slice(3,6) + '-' + d.slice(6);
  else if (d.length > 3) f = '(' + d.slice(0,3) + ')' + d.slice(3);
  else if (d.length > 0) f = '(' + d;
  t.value = f;
}}, true);

loadKiosk();
"""

    return (
        '<!DOCTYPE html><html lang="en">'
        '<head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover">'
        '<title>Reform Kiosk</title>'
        f'<style>{_CSS}</style>'
        f'<style>{css_extra}</style>'
        '</head><body>'
        + body
        + f'<script>{shared_js}\n{page_js}</script>'
        '</body></html>'
    )
