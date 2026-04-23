"""
Events & Lead Capture pages.
- Event detail page (auth required)
- Public lead capture form (no auth)
- Leads hub dashboard (auth required)
"""
from .shared import (
    _CSS, _page,
    T_EVENTS, T_LEADS, T_GOR_VENUES, T_GOR_ACTS,
)


# ──────────────────────────────────────────────────────────────────────────────
# EVENT DETAIL PAGE
# ──────────────────────────────────────────────────────────────────────────────
def _event_detail_page(event_id: int, br: str, bt: str, user: dict = None) -> str:
    header = (
        '<div class="header"><div class="header-left">'
        '<h1>Event Detail</h1>'
        '<div class="sub">Event management and lead capture</div>'
        '</div></div>'
    )
    body = '<div id="ev-content"><div class="loading" style="padding:40px">Loading event…</div></div>'
    js = f"""
const EV_ID = {event_id};
const T_EVENTS = {T_EVENTS};
const T_LEADS  = {T_LEADS};

const SC = {{
  'Prospective':'#475569','Maybe':'#d97706','Approved':'#2563eb',
  'Declined':'#ef4444','Scheduled':'#ea580c','Completed':'#059669'
}};
const STATUSES = ['Prospective','Maybe','Approved','Declined','Scheduled','Completed'];
const POST_APPROVAL = new Set(['Approved','Scheduled','Completed']);

var _ev = null;

async function load() {{
  const evRows = await fetchAll(T_EVENTS);
  const ev = evRows.find(r => r.id === EV_ID);
  if (!ev) {{
    document.getElementById('ev-content').innerHTML = '<div class="empty" style="padding:40px">Event not found</div>';
    return;
  }}
  _ev = ev;

  const name = esc(ev['Name'] || '(unnamed)');
  const status = sv(ev['Event Status']) || 'Prospective';
  const type = sv(ev['Event Type']) || '';
  const date = ev['Event Date'] || '';
  const organizer = ev['Organizer'] || '';
  const address = ev['Venue Address'] || '';
  const slug = ev['Form Slug'] || '';
  const checkedIn = ev['Checked In'] || false;
  const leadCount = ev['Lead Count'] || 0;
  const sc = SC[status] || '#475569';

  var html = '<div style="display:grid;grid-template-columns:1fr 380px;gap:24px">';

  // Left column - event info
  html += '<div>';
  html += '<div class="db-card" style="margin-bottom:16px">';
  html += '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px">';
  html += '<div><div style="font-size:20px;font-weight:700;color:var(--text);margin-bottom:4px">' + name + '</div>';
  html += '<div style="font-size:13px;color:var(--text3)">' + esc(type) + '</div></div>';
  html += '<div style="display:flex;gap:8px;align-items:center">';
  html += '<span style="background:'+sc+'22;color:'+sc+';font-size:11px;font-weight:600;padding:4px 10px;border-radius:6px">' + esc(status) + '</span>';
  html += '</div></div>';

  // Event details grid
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:13px">';
  if (date) html += '<div><div style="color:var(--text3);font-size:11px;margin-bottom:2px">Date</div><div style="font-weight:600">' + esc(fmt(date)) + '</div></div>';
  if (organizer) html += '<div><div style="color:var(--text3);font-size:11px;margin-bottom:2px">Organizer</div><div style="font-weight:600">' + esc(organizer) + '</div></div>';
  if (address) html += '<div style="grid-column:span 2"><div style="color:var(--text3);font-size:11px;margin-bottom:2px">Venue</div><div style="font-weight:600">' + esc(address) + '</div></div>';
  if (ev['Cost']) html += '<div><div style="color:var(--text3);font-size:11px;margin-bottom:2px">Cost</div><div style="font-weight:600">' + esc(ev['Cost']) + '</div></div>';
  html += '</div></div>';

  // Status controls
  html += '<div class="db-card" style="margin-bottom:16px">';
  html += '<div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text3);margin-bottom:10px">Decision</div>';
  html += '<div style="display:flex;gap:8px;flex-wrap:wrap">';
  STATUSES.forEach(function(s) {{
    var active = s === status;
    var c = SC[s];
    html += '<button onclick="setEventStatus(\\''+s+'\\')" style="padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;border:'+(active?'2px solid '+c:'1px solid var(--border)')+';background:'+(active?c+'22':'transparent')+';color:'+(active?c:'var(--text3)')+'">' + s + '</button>';
  }});
  html += '</div>';

  // Check-in button
  html += '<div style="margin-top:12px;display:flex;gap:8px;align-items:center">';
  if (checkedIn) {{
    html += '<span style="color:#059669;font-size:13px;font-weight:600">✓ Checked In</span>';
  }} else {{
    html += '<button onclick="checkInEvent()" style="background:#ea580c;color:#fff;border:none;border-radius:6px;padding:8px 18px;font-size:13px;font-weight:600;cursor:pointer">Check In</button>';
  }}
  html += '</div></div>';

  // Evaluation section (always visible)
  html += '<div class="db-card" style="margin-bottom:16px">';
  html += '<div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text3);margin-bottom:12px">Evaluation</div>';
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">';
  html += _numField('ev-attendees', 'Expected Attendees', ev['Anticipated Count']);
  html += _numField('ev-insurance', 'Est. % on Accepted Insurance', ev['Est Insurance Pct'], '35–40% is our go/no-go threshold');
  html += '</div>';
  html += '<div style="margin-top:14px">';
  html += '<div style="font-size:11px;color:var(--text3);text-transform:uppercase;font-weight:600;margin-bottom:6px">Other Chiropractor Present?</div>';
  html += _radioRow('ev-chiro', ['Yes','No','Unknown'], sv(ev['Other Chiropractor']) || 'Unknown');
  html += '</div>';
  html += _textArea('ev-decision-notes', 'Decision Notes', ev['Decision Notes'] || '', 60);
  html += '</div>';

  // Logistics & Staffing (only once decided yes)
  if (POST_APPROVAL.has(status)) {{
    html += '<div class="db-card" style="margin-bottom:16px">';
    html += '<div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text3);margin-bottom:12px">Staffing</div>';
    html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px">';
    html += _numField('ev-doctors', '# Doctors', ev['Doctors Needed']);
    html += _numField('ev-frontdesk', '# Front Desk', ev['Front Desk Needed']);
    html += _numField('ev-therapists', '# Therapists', ev['Therapists Needed']);
    html += '</div></div>';

    html += '<div class="db-card" style="margin-bottom:16px">';
    html += '<div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text3);margin-bottom:12px">Logistics</div>';
    html += '<div style="display:flex;gap:18px;flex-wrap:wrap">';
    html += _checkbox('ev-generator', 'Generator',  ev['Generator Needed']);
    html += _checkbox('ev-table',     'Table',      ev['Table Needed']);
    html += _checkbox('ev-ezup',      'EZ Up',      ev['EZ Up Needed']);
    html += '</div></div>';

    html += '<div class="db-card" style="margin-bottom:16px">';
    html += '<div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text3);margin-bottom:12px">Promotion &amp; Services</div>';
    html += _textArea('ev-promotion', 'Promotion',        ev['Promotion'] || '',         60);
    html += _textArea('ev-services',  'Services Rendered', ev['Services Rendered'] || '', 60);
    html += _textArea('ev-materials', 'Materials Needed',  ev['Materials Needed'] || '',  60);
    html += '</div>';
  }}

  // Save button
  html += '<div style="display:flex;gap:10px;margin-bottom:16px">';
  html += '<button onclick="saveEvent()" id="ev-save" style="background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:10px 22px;font-size:13px;font-weight:700;cursor:pointer">Save Changes</button>';
  html += '<span id="ev-save-msg" style="align-self:center;font-size:12px;color:var(--text3)"></span>';
  html += '</div>';

  // Lead capture form link
  if (slug) {{
    var formUrl = window.location.origin + '/form/' + slug;
    html += '<div class="db-card" style="margin-bottom:16px">';
    html += '<div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--text3);margin-bottom:10px">Lead Capture Form</div>';
    html += '<div style="display:flex;gap:8px;align-items:center">';
    html += '<input type="text" id="form-url" value="'+esc(formUrl)+'" readonly style="flex:1;padding:8px 12px;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:6px;font-size:12px">';
    html += '<button onclick="copyFormUrl()" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:8px 14px;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap">Copy Link</button>';
    html += '</div>';
    html += '<a href="'+esc(formUrl)+'" target="_blank" style="display:inline-block;margin-top:8px;font-size:12px;color:#3b82f6;font-weight:600;text-decoration:none">Open form →</a>';
    html += '</div>';
  }}

  html += '</div>';

  // Right column - leads
  html += '<div>';
  html += '<div class="panel" style="margin:0">';
  html += '<div class="panel-hd"><span class="panel-title">Captured Leads</span><span class="panel-ct" id="lead-ct">' + leadCount + '</span></div>';
  html += '<div class="panel-body" id="leads-list" style="max-height:500px;overflow-y:auto"><div class="loading">Loading…</div></div>';
  html += '</div>';
  html += '</div></div>';

  document.getElementById('ev-content').innerHTML = html;

  // Load leads for this event
  loadLeads();
}}

function _numField(id, label, value, hint) {{
  var v = (value === null || value === undefined) ? '' : value;
  var h = hint ? '<div style="font-size:10px;color:var(--text3);margin-top:3px">'+esc(hint)+'</div>' : '';
  return '<div>'
    + '<div style="font-size:11px;color:var(--text3);text-transform:uppercase;font-weight:600;margin-bottom:6px">'+esc(label)+'</div>'
    + '<input type="number" id="'+id+'" value="'+v+'" style="width:100%;padding:8px 10px;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:6px;font-size:13px">'
    + h
    + '</div>';
}}

function _textArea(id, label, value, minHeight) {{
  return '<div style="margin-top:12px">'
    + '<div style="font-size:11px;color:var(--text3);text-transform:uppercase;font-weight:600;margin-bottom:6px">'+esc(label)+'</div>'
    + '<textarea id="'+id+'" style="width:100%;min-height:'+(minHeight||60)+'px;padding:8px 10px;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:6px;font-size:13px;font-family:inherit;resize:vertical">'+esc(value||'')+'</textarea>'
    + '</div>';
}}

function _radioRow(name, options, current) {{
  return '<div style="display:flex;gap:14px">' + options.map(function(o) {{
    var checked = (o === current) ? ' checked' : '';
    return '<label style="display:flex;align-items:center;gap:5px;font-size:13px;cursor:pointer">'
      + '<input type="radio" name="'+name+'" value="'+o+'"'+checked+'> ' + esc(o)
      + '</label>';
  }}).join('') + '</div>';
}}

function _checkbox(id, label, value) {{
  var checked = value ? ' checked' : '';
  return '<label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">'
    + '<input type="checkbox" id="'+id+'"'+checked+'> ' + esc(label)
    + '</label>';
}}

function _readRadio(name) {{
  var el = document.querySelector('input[name="'+name+'"]:checked');
  return el ? el.value : '';
}}

function _readInt(id) {{
  var el = document.getElementById(id);
  if (!el) return null;
  var v = el.value.trim();
  return v === '' ? null : parseInt(v);
}}

function _readText(id) {{
  var el = document.getElementById(id);
  return el ? el.value : '';
}}

function _readBool(id) {{
  var el = document.getElementById(id);
  return el ? !!el.checked : false;
}}

async function saveEvent() {{
  if (!_ev) return;
  var btn = document.getElementById('ev-save');
  var msg = document.getElementById('ev-save-msg');
  btn.disabled = true; btn.textContent = 'Saving…';
  msg.textContent = '';

  var patch = {{
    'Anticipated Count':    _readInt('ev-attendees'),
    'Est Insurance Pct':    _readInt('ev-insurance'),
    'Other Chiropractor':   _readRadio('ev-chiro'),
    'Decision Notes':       _readText('ev-decision-notes'),
  }};
  if (document.getElementById('ev-doctors')) {{
    patch['Doctors Needed']    = _readInt('ev-doctors');
    patch['Front Desk Needed'] = _readInt('ev-frontdesk');
    patch['Therapists Needed'] = _readInt('ev-therapists');
    patch['Generator Needed']  = _readBool('ev-generator');
    patch['Table Needed']      = _readBool('ev-table');
    patch['EZ Up Needed']      = _readBool('ev-ezup');
    patch['Promotion']         = _readText('ev-promotion');
    patch['Services Rendered'] = _readText('ev-services');
    patch['Materials Needed']  = _readText('ev-materials');
  }}

  if (!patch['Other Chiropractor']) delete patch['Other Chiropractor'];

  try {{
    var r = await fetch('/api/events/' + EV_ID, {{
      method:'PATCH', headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify(patch)
    }});
    var d = await r.json();
    if (d.ok) {{
      msg.style.color = '#059669'; msg.textContent = 'Saved';
      setTimeout(function() {{ msg.textContent = ''; }}, 2000);
      load();
    }} else {{
      msg.style.color = '#ef4444'; msg.textContent = d.error || 'Save failed';
    }}
  }} catch(e) {{
    msg.style.color = '#ef4444'; msg.textContent = 'Network error';
  }}
  btn.disabled = false; btn.textContent = 'Save Changes';
}}

async function setEventStatus(newStatus) {{
  await fetch('/api/events/' + EV_ID + '/status', {{
    method:'PATCH', headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{status:newStatus}})
  }});
  load();
}}

async function checkInEvent() {{
  await fetch('/api/events/' + EV_ID + '/checkin', {{
    method:'PATCH', headers:{{'Content-Type':'application/json'}},
    body:'{{}}'
  }});
  load();
}}

async function markLead(leadId, status) {{
  await fetch('/api/leads/' + leadId, {{
    method:'PATCH', headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{status:status}})
  }});
  loadLeads();
}}

function copyFormUrl() {{
  var inp = document.getElementById('form-url');
  inp.select();
  document.execCommand('copy');
  var btn = inp.nextElementSibling;
  btn.textContent = 'Copied!';
  setTimeout(function(){{ btn.textContent = 'Copy Link'; }}, 2000);
}}

load();
"""
    return _page('gorilla_events_ext', 'Event Detail', header, body, js, br, bt, user=user)


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC LEAD CAPTURE FORM (no auth)
# ──────────────────────────────────────────────────────────────────────────────
def _lead_form_page(event_name: str, slug: str) -> str:
    """Standalone branded lead capture form. No auth required."""
    return f'''<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{event_name} — Reform Chiropractic</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#fff5eb 0%,#fff 50%,#f0f7ff 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}}
.form-card{{background:#fff;border-radius:20px;box-shadow:0 8px 40px rgba(0,0,0,0.08);max-width:480px;width:100%;overflow:hidden}}
.form-header{{background:linear-gradient(135deg,#ea580c,#dc2626);padding:32px 28px;text-align:center;color:#fff}}
.form-header h1{{font-size:14px;font-weight:600;letter-spacing:1px;text-transform:uppercase;opacity:0.9;margin-bottom:6px}}
.form-header h2{{font-size:22px;font-weight:700;line-height:1.3}}
.form-body{{padding:28px}}
.form-group{{margin-bottom:18px}}
.form-label{{font-size:12px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;display:block}}
.form-input{{width:100%;padding:12px 16px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:15px;color:#1e293b;outline:none;transition:border-color 0.15s}}
.form-input:focus{{border-color:#ea580c}}
.form-input::placeholder{{color:#94a3b8}}
textarea.form-input{{min-height:80px;resize:vertical;font-family:inherit}}
.form-submit{{width:100%;padding:14px;background:#ea580c;color:#fff;border:none;border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;transition:background 0.15s;margin-top:8px}}
.form-submit:hover{{background:#dc2626}}
.form-submit:disabled{{opacity:0.5;cursor:not-allowed}}
.form-msg{{text-align:center;font-size:13px;margin-top:10px;min-height:18px}}
.form-footer{{text-align:center;padding:0 28px 24px;font-size:11px;color:#94a3b8}}
.form-success{{text-align:center;padding:48px 28px}}
.form-success-icon{{font-size:48px;margin-bottom:12px}}
.form-success h3{{font-size:20px;font-weight:700;color:#1e293b;margin-bottom:8px}}
.form-success p{{font-size:14px;color:#64748b;line-height:1.6}}
</style></head>
<body>
<div class="form-card">
  <div class="form-header">
    <h1>\u2726 Reform Chiropractic</h1>
    <h2 id="ev-title">{event_name}</h2>
  </div>
  <div id="form-body" class="form-body">
    <div class="form-group">
      <label class="form-label">Full Name *</label>
      <input type="text" id="lf-name" class="form-input" placeholder="Your full name" required>
    </div>
    <div class="form-group">
      <label class="form-label">Phone Number *</label>
      <input type="tel" id="lf-phone" class="form-input" placeholder="(555) 555-5555">
    </div>
    <div class="form-group">
      <label class="form-label">Email</label>
      <input type="email" id="lf-email" class="form-input" placeholder="you@example.com">
    </div>
    <div class="form-group">
      <label class="form-label">What brings you in today?</label>
      <textarea id="lf-reason" class="form-input" placeholder="Pain, wellness check, curious about chiropractic\u2026"></textarea>
    </div>
    <button class="form-submit" id="lf-submit" onclick="submitLead()">Submit</button>
    <div class="form-msg" id="lf-msg"></div>
  </div>
  <div id="form-success" class="form-success" style="display:none">
    <div class="form-success-icon">\u2705</div>
    <h3>Thank you!</h3>
    <p>We\u2019ve received your information and a member of our team will be in touch shortly.</p>
  </div>
  <div class="form-footer">\u00a9 Reform Chiropractic \u2022 (832) 699-3148 \u2022 reformchiropractic.com</div>
</div>
<script>
var SLUG = '{slug}';
async function submitLead() {{
  var name = document.getElementById('lf-name').value.trim();
  var phone = document.getElementById('lf-phone').value.trim();
  var email = document.getElementById('lf-email').value.trim();
  var reason = document.getElementById('lf-reason').value.trim();
  var msg = document.getElementById('lf-msg');
  if (!name || !phone) {{
    msg.style.color='#ef4444'; msg.textContent='Please enter your name and phone number.';
    return;
  }}
  var btn = document.getElementById('lf-submit');
  btn.disabled=true; btn.textContent='Submitting\u2026';
  msg.textContent='';
  try {{
    var r = await fetch('/api/leads', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{slug:SLUG,name:name,phone:phone,email:email,reason:reason}})
    }});
    var d = await r.json();
    if (d.ok) {{
      document.getElementById('form-body').style.display='none';
      document.getElementById('form-success').style.display='block';
    }} else {{
      msg.style.color='#ef4444'; msg.textContent=d.error||'Something went wrong.';
      btn.disabled=false; btn.textContent='Submit';
    }}
  }} catch(e) {{
    msg.style.color='#ef4444'; msg.textContent='Network error. Please try again.';
    btn.disabled=false; btn.textContent='Submit';
  }}
}}
</script>
</body></html>'''


# ──────────────────────────────────────────────────────────────────────────────
# LEADS HUB DASHBOARD
# ──────────────────────────────────────────────────────────────────────────────
def _leads_dashboard_page(br: str, bt: str, user: dict = None) -> str:
    header = (
        '<div class="header"><div class="header-left">'
        '<h1>Lead Capture Hub</h1>'
        '<div class="sub">Event leads and contact tracking</div>'
        '</div></div>'
    )
    body = f"""
<style>
.leads-stats{{display:flex;gap:14px;margin-bottom:20px}}
.leads-stat{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px 20px;flex:1;text-align:center}}
.leads-stat .val{{font-size:24px;font-weight:700;line-height:1}}
.leads-stat .lbl{{font-size:10px;color:var(--text3);margin-top:4px;text-transform:uppercase}}
.leads-toolbar{{display:flex;gap:10px;margin-bottom:16px;align-items:center}}
.leads-toolbar input,.leads-toolbar select{{padding:8px 12px;background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:8px;font-size:13px;outline:none}}
.leads-toolbar input{{flex:1}}
.lead-row{{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid var(--border)}}
.lead-row:hover{{background:rgba(255,255,255,0.02)}}
.lead-check{{width:16px;height:16px;cursor:pointer;accent-color:#3b82f6}}
.lead-name{{font-size:13px;font-weight:600;color:var(--text)}}
.lead-contact{{font-size:11px;color:var(--text3)}}
.lead-event{{font-size:10px;background:var(--bg);color:var(--text3);padding:2px 7px;border-radius:4px;white-space:nowrap}}
</style>

<div class="leads-stats">
  <div class="leads-stat"><div class="val" id="ls-total">--</div><div class="lbl">Total Leads</div></div>
  <div class="leads-stat"><div class="val" id="ls-new" style="color:#3b82f6">--</div><div class="lbl">New</div></div>
  <div class="leads-stat"><div class="val" id="ls-contacted" style="color:#d97706">--</div><div class="lbl">Contacted</div></div>
  <div class="leads-stat"><div class="val" id="ls-events" style="color:#ea580c">--</div><div class="lbl">Events</div></div>
</div>

<div class="leads-toolbar">
  <input type="text" id="lead-search" placeholder="Search by name, phone, or email\u2026" oninput="filterLeads()">
  <select id="lead-status-filter" onchange="filterLeads()">
    <option value="">All Statuses</option>
    <option value="New">New</option>
    <option value="Contacted">Contacted</option>
    <option value="Scheduled">Scheduled</option>
    <option value="Converted">Converted</option>
    <option value="Lost">Lost</option>
  </select>
  <select id="lead-event-filter" onchange="filterLeads()"></select>
  <button onclick="bulkContact()" style="background:#2563eb;color:#fff;border:none;border-radius:8px;padding:8px 14px;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap">Mark Selected Contacted</button>
</div>

<div class="panel" style="margin:0">
  <div class="panel-hd">
    <span class="panel-title">All Leads</span>
    <span class="panel-ct" id="lead-ct">\u2014</span>
  </div>
  <div class="panel-body" id="leads-body" style="max-height:calc(100vh - 320px);overflow-y:auto">
    <div class="loading" style="padding:20px">Loading\u2026</div>
  </div>
</div>
"""
    js = f"""
var _allLeads = [], _allEvents = [];
var T_EVENTS = {T_EVENTS}, T_LEADS = {T_LEADS};

async function load() {{
  [_allEvents, _allLeads] = await Promise.all([
    fetchAll(T_EVENTS),
    fetchAll(T_LEADS),
  ]);

  // Stats
  document.getElementById('ls-total').textContent = _allLeads.length;
  document.getElementById('ls-new').textContent = _allLeads.filter(function(l){{return (sv(l['Status'])||'New')==='New';}}).length;
  document.getElementById('ls-contacted').textContent = _allLeads.filter(function(l){{return sv(l['Status'])==='Contacted';}}).length;
  document.getElementById('ls-events').textContent = _allEvents.length;

  // Event filter dropdown
  var evSel = document.getElementById('lead-event-filter');
  evSel.innerHTML = '<option value="">All Events</option>' + _allEvents.map(function(e){{
    return '<option value="'+e.id+'">'+esc(e['Name']||'(unnamed)')+'</option>';
  }}).join('');

  filterLeads();
}}

function _eventName(lead) {{
  var ev = lead['Event'];
  if (!Array.isArray(ev) || !ev.length) return '';
  var eid = ev[0].id;
  var found = _allEvents.find(function(e){{return e.id===eid;}});
  return found ? (found['Name']||'') : '';
}}

function _eventId(lead) {{
  var ev = lead['Event'];
  return (Array.isArray(ev) && ev.length) ? ev[0].id : 0;
}}

function filterLeads() {{
  var q = (document.getElementById('lead-search').value||'').toLowerCase();
  var sf = document.getElementById('lead-status-filter').value;
  var ef = parseInt(document.getElementById('lead-event-filter').value) || 0;

  var rows = _allLeads.filter(function(l) {{
    if (sf && sv(l['Status']) !== sf && !(sf==='New' && !sv(l['Status']))) return false;
    if (ef && _eventId(l) !== ef) return false;
    if (q) {{
      var haystack = ((l['Name']||'')+(l['Phone']||'')+(l['Email']||'')).toLowerCase();
      if (!haystack.includes(q)) return false;
    }}
    return true;
  }});

  document.getElementById('lead-ct').textContent = rows.length + ' leads';
  var SC = {{'New':'#3b82f6','Contacted':'#d97706','Scheduled':'#059669','Converted':'#16a34a','Lost':'#ef4444'}};
  var el = document.getElementById('leads-body');
  if (!rows.length) {{
    el.innerHTML = '<div class="empty" style="padding:20px">No leads found</div>';
    return;
  }}
  el.innerHTML = rows.map(function(l) {{
    var st = sv(l['Status']) || 'New';
    var c = SC[st] || '#475569';
    var evName = _eventName(l);
    var evId = _eventId(l);
    return '<div class="lead-row">'
      + '<input type="checkbox" class="lead-check" data-id="'+l.id+'">'
      + '<div style="flex:1;min-width:0">'
      + '<div class="lead-name">' + esc(l['Name']||'(no name)') + '</div>'
      + '<div class="lead-contact">' + esc(l['Phone']||'') + (l['Email']?' \u2022 '+esc(l['Email']):'') + '</div>'
      + (l['Reason'] ? '<div style="font-size:10px;margin-top:2px"><span style="background:#ea580c18;color:#ea580c;padding:1px 6px;border-radius:3px;font-weight:600">' + esc(l['Reason']) + '</span></div>' : '')
      + '</div>'
      + (evName ? '<a href="/events/'+evId+'" class="lead-event" style="text-decoration:none">' + esc(evName) + '</a>' : '')
      + '<span style="font-size:10px;background:'+c+'22;color:'+c+';padding:2px 7px;border-radius:4px;font-weight:600;white-space:nowrap">' + esc(st) + '</span>'
      + '<button onclick="markSingleLead('+l.id+')" style="background:none;border:1px solid var(--border);color:var(--text2);border-radius:4px;padding:4px 8px;font-size:10px;cursor:pointer" title="Mark contacted">\u2713</button>'
      + '</div>';
  }}).join('');
}}

async function markSingleLead(id) {{
  await fetch('/api/leads/' + id, {{
    method:'PATCH', headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{status:'Contacted'}})
  }});
  load();
}}

async function bulkContact() {{
  var checks = document.querySelectorAll('.lead-check:checked');
  if (!checks.length) {{ alert('Select leads first.'); return; }}
  var ids = Array.from(checks).map(function(c){{return parseInt(c.dataset.id);}});
  await fetch('/api/leads/bulk-contact', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{ids:ids}})
  }});
  load();
}}

load();
"""
    return _page('leads', 'Lead Capture Hub', header, body, js, br, bt, user=user)


# ──────────────────────────────────────────────────────────────────────────────
# EVENTS INDEX PAGE (list + intake modal)
# ──────────────────────────────────────────────────────────────────────────────
def _events_index_page(br: str, bt: str, user: dict = None) -> str:
    header = (
        '<div class="header"><div class="header-left">'
        '<h1>Events</h1>'
        '<div class="sub">Event pipeline and intake</div>'
        '</div></div>'
    )
    body = f"""
<style>
.ev-stats{{display:flex;gap:14px;margin-bottom:20px;flex-wrap:wrap}}
.ev-stat{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 18px;flex:1;min-width:140px;text-align:center}}
.ev-stat .val{{font-size:22px;font-weight:700;line-height:1}}
.ev-stat .lbl{{font-size:10px;color:var(--text3);margin-top:4px;text-transform:uppercase;letter-spacing:0.3px}}
.ev-toolbar{{display:flex;gap:10px;margin-bottom:16px;align-items:center;flex-wrap:wrap}}
.ev-toolbar input,.ev-toolbar select{{padding:8px 12px;background:var(--card);border:1px solid var(--border);color:var(--text);border-radius:8px;font-size:13px;outline:none}}
.ev-toolbar input[type=text]{{flex:1;min-width:200px}}
.ev-row{{display:flex;align-items:center;gap:14px;padding:12px 16px;border-bottom:1px solid var(--border);text-decoration:none;color:inherit}}
.ev-row:hover{{background:rgba(255,255,255,0.02)}}
.ev-row .ev-name{{font-size:13px;font-weight:600;color:var(--text)}}
.ev-row .ev-meta{{font-size:11px;color:var(--text3);margin-top:2px}}
.ev-pill{{font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;white-space:nowrap}}
.ev-badge-pending{{background:#d9770622;color:#d97706;font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;margin-left:6px}}
.ev-new-btn{{background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:8px 16px;font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap}}
.ev-modal{{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.55);display:none;align-items:center;justify-content:center;z-index:1000}}
.ev-modal.open{{display:flex}}
.ev-modal-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px;max-width:440px;width:90%}}
.ev-modal h2{{font-size:16px;font-weight:700;margin-bottom:16px}}
.ev-modal label{{display:block;font-size:11px;color:var(--text3);text-transform:uppercase;font-weight:600;margin-bottom:6px;margin-top:12px}}
.ev-modal input,.ev-modal select{{width:100%;padding:10px 12px;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:8px;font-size:14px;outline:none}}
.ev-modal-actions{{display:flex;gap:10px;margin-top:20px;justify-content:flex-end}}
.ev-modal-actions button{{padding:9px 18px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:none}}
.ev-modal-cancel{{background:transparent;color:var(--text3);border:1px solid var(--border) !important}}
.ev-modal-save{{background:#3b82f6;color:#fff}}
</style>

<div class="ev-stats">
  <div class="ev-stat"><div class="val" id="evs-total">--</div><div class="lbl">Total</div></div>
  <div class="ev-stat"><div class="val" id="evs-maybe"     style="color:#d97706">--</div><div class="lbl">Pending Decision</div></div>
  <div class="ev-stat"><div class="val" id="evs-approved"  style="color:#2563eb">--</div><div class="lbl">Approved</div></div>
  <div class="ev-stat"><div class="val" id="evs-scheduled" style="color:#ea580c">--</div><div class="lbl">Scheduled</div></div>
  <div class="ev-stat"><div class="val" id="evs-completed" style="color:#059669">--</div><div class="lbl">Completed</div></div>
</div>

<div class="ev-toolbar">
  <input type="text" id="ev-search" placeholder="Search by name, organizer, venue…" oninput="renderList()">
  <select id="ev-status-filter" onchange="renderList()">
    <option value="">All Statuses</option>
    <option value="Prospective">Prospective</option>
    <option value="Maybe">Maybe</option>
    <option value="Approved">Approved</option>
    <option value="Declined">Declined</option>
    <option value="Scheduled">Scheduled</option>
    <option value="Completed">Completed</option>
  </select>
  <select id="ev-date-filter" onchange="renderList()">
    <option value="upcoming">Upcoming</option>
    <option value="past">Past</option>
    <option value="all">All Dates</option>
  </select>
  <button class="ev-new-btn" onclick="openNewEvent()">+ New Event</button>
</div>

<div class="panel" style="margin:0">
  <div class="panel-hd">
    <span class="panel-title">Events</span>
    <span class="panel-ct" id="ev-ct">—</span>
  </div>
  <div class="panel-body" id="ev-body" style="max-height:calc(100vh - 320px);overflow-y:auto">
    <div class="loading" style="padding:20px">Loading…</div>
  </div>
</div>

<div class="ev-modal" id="ev-modal">
  <div class="ev-modal-card">
    <h2>New Event</h2>
    <label>Event Name *</label>
    <input type="text" id="new-ev-name" placeholder="e.g. Cypress Spring Health Fair">
    <label>Event Type *</label>
    <select id="new-ev-type">
      <option value="External Event">External Event</option>
      <option value="Mobile Massage Service">Mobile Massage Service</option>
      <option value="Lunch and Learn">Lunch and Learn</option>
      <option value="Health Assessment Screening">Health Assessment Screening</option>
    </select>
    <label>Event Date *</label>
    <input type="date" id="new-ev-date">
    <div style="font-size:11px;color:var(--text3);margin-top:6px">Everything else fills in on the detail page after you save.</div>
    <div id="new-ev-msg" style="font-size:12px;color:#ef4444;min-height:16px;margin-top:8px"></div>
    <div class="ev-modal-actions">
      <button class="ev-modal-cancel" onclick="closeNewEvent()">Cancel</button>
      <button class="ev-modal-save" id="new-ev-save" onclick="saveNewEvent()">Create Event</button>
    </div>
  </div>
</div>
"""
    js = f"""
var T_EVENTS = {T_EVENTS};
var _allEvents = [];

const SC = {{
  'Prospective':'#475569','Maybe':'#d97706','Approved':'#2563eb',
  'Declined':'#ef4444','Scheduled':'#ea580c','Completed':'#059669'
}};

async function load() {{
  _allEvents = await fetchAll(T_EVENTS);
  // Stats from the full set (not the filtered view)
  document.getElementById('evs-total').textContent     = _allEvents.length;
  document.getElementById('evs-maybe').textContent     = _allEvents.filter(function(e){{ var s=sv(e['Event Status']); return s==='Prospective'||s==='Maybe'; }}).length;
  document.getElementById('evs-approved').textContent  = _allEvents.filter(function(e){{ return sv(e['Event Status'])==='Approved'; }}).length;
  document.getElementById('evs-scheduled').textContent = _allEvents.filter(function(e){{ return sv(e['Event Status'])==='Scheduled'; }}).length;
  document.getElementById('evs-completed').textContent = _allEvents.filter(function(e){{ return sv(e['Event Status'])==='Completed'; }}).length;
  renderList();
}}

function renderList() {{
  var q = (document.getElementById('ev-search').value || '').toLowerCase();
  var sf = document.getElementById('ev-status-filter').value;
  var df = document.getElementById('ev-date-filter').value;
  var today = new Date(); today.setHours(0,0,0,0);

  var rows = _allEvents.filter(function(e) {{
    var status = sv(e['Event Status']) || 'Prospective';
    if (sf && status !== sf) return false;
    var d = e['Event Date'];
    if (df !== 'all') {{
      if (!d) return df === 'upcoming'; // no date = keep in upcoming
      var dt = new Date(d); dt.setHours(0,0,0,0);
      if (df === 'upcoming' && dt < today) return false;
      if (df === 'past' && dt >= today) return false;
    }}
    if (q) {{
      var hay = ((e['Name']||'') + ' ' + (e['Organizer']||'') + ' ' + (e['Venue Address']||'')).toLowerCase();
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});

  // Sort: upcoming ascending by date, past descending
  rows.sort(function(a,b) {{
    var da = a['Event Date'] || '9999-12-31';
    var db = b['Event Date'] || '9999-12-31';
    if (df === 'past') return db.localeCompare(da);
    return da.localeCompare(db);
  }});

  document.getElementById('ev-ct').textContent = rows.length + ' events';
  var el = document.getElementById('ev-body');
  if (!rows.length) {{
    el.innerHTML = '<div class="empty" style="padding:20px">No events match</div>';
    return;
  }}
  el.innerHTML = rows.map(function(e) {{
    var status = sv(e['Event Status']) || 'Prospective';
    var type = sv(e['Event Type']) || '';
    var c = SC[status] || '#475569';
    var pending = (status === 'Prospective' || status === 'Maybe');
    var date = e['Event Date'] ? fmt(e['Event Date']) : 'No date set';
    var organizer = e['Organizer'] ? ' • ' + esc(e['Organizer']) : '';
    return '<a class="ev-row" href="/events/' + e.id + '">'
      + '<div style="flex:1;min-width:0">'
      + '<div class="ev-name">' + esc(e['Name']||'(unnamed)')
      + (pending ? '<span class="ev-badge-pending">Decision pending</span>' : '')
      + '</div>'
      + '<div class="ev-meta">' + esc(date) + ' • ' + esc(type) + organizer + '</div>'
      + '</div>'
      + '<span class="ev-pill" style="background:'+c+'22;color:'+c+'">' + esc(status) + '</span>'
      + '</a>';
  }}).join('');
}}

function openNewEvent() {{
  document.getElementById('ev-modal').classList.add('open');
  document.getElementById('new-ev-name').value = '';
  document.getElementById('new-ev-type').value = 'External Event';
  document.getElementById('new-ev-date').value = '';
  document.getElementById('new-ev-msg').textContent = '';
  document.getElementById('new-ev-name').focus();
}}

function closeNewEvent() {{
  document.getElementById('ev-modal').classList.remove('open');
}}

async function saveNewEvent() {{
  var name = document.getElementById('new-ev-name').value.trim();
  var type = document.getElementById('new-ev-type').value;
  var date = document.getElementById('new-ev-date').value;
  var msg = document.getElementById('new-ev-msg');
  if (!name || !type || !date) {{
    msg.textContent = 'All fields required';
    return;
  }}
  var btn = document.getElementById('new-ev-save');
  btn.disabled = true; btn.textContent = 'Creating…';
  msg.textContent = '';
  try {{
    var r = await fetch('/api/events', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{name:name, event_type:type, event_date:date}})
    }});
    var d = await r.json();
    if (d.ok && d.id) {{
      window.location.href = '/events/' + d.id;
    }} else {{
      msg.textContent = d.error || 'Create failed';
      btn.disabled = false; btn.textContent = 'Create Event';
    }}
  }} catch(e) {{
    msg.textContent = 'Network error';
    btn.disabled = false; btn.textContent = 'Create Event';
  }}
}}

// ESC closes modal
document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') closeNewEvent();
}});

load();
"""
    return _page('events', 'Events', header, body, js, br, bt, user=user)
