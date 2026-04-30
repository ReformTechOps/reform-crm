"""Leads list + capture/detail modals + legacy log redirect."""

from hub.shared import (
    _mobile_page,
    T_GOR_VENUES, T_EVENTS, T_COMPANIES, T_LEADS,
    LEAD_MODAL_HTML, LEAD_MODAL_JS,
)
from hub.guerilla import GFR_EXTRA_HTML, GFR_EXTRA_JS


def _mobile_lead_capture_page(br: str, bt: str, user: dict = None) -> str:
    user = user or {}
    user_name = user.get('name', '')
    user_email = (user.get('email', '') or '').strip().lower()
    body = (
        '<div class="mobile-hdr">'
        '<div><div class="mobile-hdr-title">Leads</div>'
        '<div class="mobile-hdr-sub">All captured leads</div></div>'
        '<button class="m-hamburger" onclick="openMDrawer()" aria-label="Menu">☰</button>'
        '</div>'
        '<div class="mobile-body">'
        # ── Toolbar ──────────────────────────────────────────────────
        # "+ New Lead" lives in a FAB (bottom-right) — see end of body.
        '<input type="text" id="leads-search" placeholder="Search name, phone, email, source…" '
        'oninput="onSearchInput()" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:9px 12px;font-size:14px;box-sizing:border-box;margin-bottom:8px">'
        # Status filter chips
        '<div id="leads-status-chips" style="display:flex;gap:6px;overflow-x:auto;padding-bottom:6px;margin-bottom:8px;'
        '-webkit-overflow-scrolling:touch"></div>'
        # Mine/All toggle
        '<div style="display:flex;gap:0;margin-bottom:14px;border:1px solid var(--border);border-radius:8px;overflow:hidden">'
        '<button id="scope-all" onclick="setScope(\'all\')" '
        'style="flex:1;background:#004ac6;color:#fff;border:none;padding:8px;font-size:13px;font-weight:600;cursor:pointer">'
        'All</button>'
        '<button id="scope-mine" onclick="setScope(\'mine\')" '
        'style="flex:1;background:none;color:var(--text2);border:none;padding:8px;font-size:13px;font-weight:600;cursor:pointer">'
        'Mine only</button>'
        '</div>'
        # ── List container ───────────────────────────────────────────
        '<div id="leads-list" style="font-size:13px">'
        '<div style="color:var(--text3);padding:20px;text-align:center">Loading…</div>'
        '</div>'
        '</div>'
        # ── New Lead FAB (replaces the full-width toolbar button) ────
        '<button class="fab" onclick="openCaptureModal()" aria-label="New lead">'
        '<span class="material-symbols-outlined">add</span></button>'
        # ── Capture lead modal ──────────────────────────────────────
        '<div id="capture-modal-bg" onclick="if(event.target===this)closeCaptureModal()" '
        'style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:1100;'
        'align-items:flex-start;justify-content:center;padding:30px 14px;overflow-y:auto">'
        '<div style="background:var(--bg2);border:1px solid var(--border);border-radius:14px;'
        'width:100%;max-width:480px;padding:18px 20px calc(20px + env(safe-area-inset-bottom))">'
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">'
        '<h3 style="margin:0;color:var(--text);font-size:16px;flex:1">Capture Lead</h3>'
        '<button onclick="closeCaptureModal()" style="background:none;border:none;color:var(--text3);'
        'font-size:18px;cursor:pointer;padding:4px 8px">×</button>'
        '</div>'
        '<div id="capture-modal-body">'
        '<div id="lead-form">'
        # Name
        '<div style="margin-bottom:12px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Name *</label>'
        '<input type="text" id="lf-name" placeholder="Full name" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box">'
        '</div>'
        # Phone
        '<div style="margin-bottom:12px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Phone *</label>'
        '<input type="tel" id="lf-phone" placeholder="(555) 123-4567" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box">'
        '</div>'
        # Email
        '<div style="margin-bottom:12px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Email</label>'
        '<input type="email" id="lf-email" placeholder="email@example.com" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box">'
        '</div>'
        # Service Interested
        '<div style="margin-bottom:12px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Service Interested *</label>'
        '<select id="lf-service" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box;appearance:auto">'
        '<option value="">Select a service…</option>'
        '<option value="Chiropractic Care">Chiropractic Care</option>'
        '<option value="Massage Therapy">Massage Therapy</option>'
        '<option value="Health Screening">Health Screening</option>'
        '<option value="Injury Rehab">Injury Rehab</option>'
        '<option value="Other">Other</option>'
        '</select>'
        '</div>'
        # Event (dropdown loaded from API)
        '<div style="margin-bottom:12px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Event / Source</label>'
        '<select id="lf-event" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box;appearance:auto">'
        '<option value="">No event (walk-in / field)</option>'
        '</select>'
        '</div>'
        # Referred from company
        '<div style="margin-bottom:12px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Referred from company (optional)</label>'
        '<input type="text" id="lf-company" list="lf-company-list" placeholder="Type to search…" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box">'
        '<datalist id="lf-company-list"></datalist>'
        '<div id="lf-company-hint" style="font-size:11px;color:var(--text3);margin-top:4px;min-height:14px"></div>'
        '</div>'
        # Notes
        '<div style="margin-bottom:14px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Notes</label>'
        '<textarea id="lf-notes" rows="3" placeholder="Additional details…" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box;resize:vertical;font-family:inherit"></textarea>'
        '</div>'
        # Submit
        '<button id="lf-submit" onclick="submitLead()" '
        'style="width:100%;background:#004ac6;color:#fff;border:none;border-radius:8px;'
        'padding:13px;font-size:15px;font-weight:700;cursor:pointer">'
        'Submit Lead</button>'
        '<div id="lf-status" style="text-align:center;margin-top:10px;font-size:13px;min-height:20px"></div>'
        '</div>'
        '</div>'
        '</div>'
        '</div>'
        # ── Detail modal (shared) ────────────────────────────────────
        + LEAD_MODAL_HTML
    )
    js = f"""
const USER_EMAIL = {repr(user_email)};
const _STATUSES = ['New','Contacted','Appointment Set','Patient Seen','Converted','Dropped'];
const _STATUS_COLORS = {{'New':'#3b82f6','Contacted':'#ea580c','Appointment Set':'#7c3aed','Patient Seen':'#0891b2','Converted':'#059669','Dropped':'#9ca3af'}};

var _leads = [];        // full cache from fetchAll
var _events = [];
var _COMPANIES_LOOKUP = {{}};
var _filterStatus = 'All';
var _filterScope = 'all';   // 'all' | 'mine'
var _searchQuery = '';
var _searchTimer = null;

function esc(s) {{
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}}

function svJS(v) {{
  if (!v) return '';
  if (typeof v === 'object' && !Array.isArray(v)) return v.value || '';
  return String(v);
}}

// ── Status chip strip ───────────────────────────────────────────────
function renderStatusChips() {{
  var box = document.getElementById('leads-status-chips');
  if (!box) return;
  var labels = ['All'].concat(_STATUSES);
  box.innerHTML = labels.map(function(s) {{
    var active = (s === _filterStatus);
    var color = (s === 'All') ? '#004ac6' : (_STATUS_COLORS[s] || '#6b7280');
    var bg = active ? color : 'var(--bg)';
    var fg = active ? '#fff' : 'var(--text2)';
    return '<button onclick="setStatusFilter(\\''+ esc(s) +'\\')" '
         + 'style="flex:0 0 auto;background:'+bg+';color:'+fg+';border:1px solid '+color+';'
         + 'border-radius:14px;padding:5px 12px;font-size:12px;font-weight:600;cursor:pointer;'
         + 'white-space:nowrap;font-family:inherit">'+esc(s)+'</button>';
  }}).join('');
}}

function setStatusFilter(s) {{
  _filterStatus = s;
  renderStatusChips();
  applyFilters();
}}

function setScope(scope) {{
  _filterScope = scope;
  // Toggle button styling
  var allBtn = document.getElementById('scope-all');
  var mineBtn = document.getElementById('scope-mine');
  if (scope === 'all') {{
    allBtn.style.background = '#004ac6'; allBtn.style.color = '#fff';
    mineBtn.style.background = 'none'; mineBtn.style.color = 'var(--text2)';
  }} else {{
    mineBtn.style.background = '#004ac6'; mineBtn.style.color = '#fff';
    allBtn.style.background = 'none'; allBtn.style.color = 'var(--text2)';
  }}
  applyFilters();
}}

function onSearchInput() {{
  if (_searchTimer) clearTimeout(_searchTimer);
  _searchTimer = setTimeout(function() {{
    var el = document.getElementById('leads-search');
    _searchQuery = (el ? el.value : '').trim().toLowerCase();
    applyFilters();
  }}, 150);
}}

function clearAllFilters() {{
  _filterStatus = 'All';
  _filterScope = 'all';
  _searchQuery = '';
  var el = document.getElementById('leads-search');
  if (el) el.value = '';
  renderStatusChips();
  setScope('all');  // also re-applies filters
}}

// ── Filter + render ─────────────────────────────────────────────────
function applyFilters() {{
  var rows = _leads.slice();
  if (_filterStatus !== 'All') {{
    rows = rows.filter(function(L) {{ return svJS(L.Status) === _filterStatus; }});
  }}
  if (_filterScope === 'mine' && USER_EMAIL) {{
    rows = rows.filter(function(L) {{
      return (L.Owner || '').trim().toLowerCase() === USER_EMAIL;
    }});
  }}
  if (_searchQuery) {{
    var q = _searchQuery;
    rows = rows.filter(function(L) {{
      return (L.Name || '').toLowerCase().indexOf(q) >= 0
          || (L.Phone || '').toLowerCase().indexOf(q) >= 0
          || (L.Email || '').toLowerCase().indexOf(q) >= 0
          || (L.Source || '').toLowerCase().indexOf(q) >= 0;
    }});
  }}
  renderLeads(rows);
}}

function renderLeads(rows) {{
  var box = document.getElementById('leads-list');
  if (!box) return;
  if (!_leads.length) {{
    box.innerHTML = '<div style="color:var(--text3);padding:30px 10px;text-align:center">'
                  + '<div style="font-size:14px;margin-bottom:10px">No leads yet.</div>'
                  + '<button onclick="openCaptureModal()" style="background:#004ac6;color:#fff;border:none;'
                  + 'border-radius:8px;padding:10px 18px;font-size:13px;font-weight:600;cursor:pointer">'
                  + '+ Capture your first lead</button></div>';
    return;
  }}
  if (!rows.length) {{
    box.innerHTML = '<div style="color:var(--text3);padding:30px 10px;text-align:center">'
                  + '<div style="font-size:14px;margin-bottom:8px">No leads match your filters.</div>'
                  + '<a href="javascript:clearAllFilters()" style="color:#3b82f6;font-size:13px">Clear filters</a></div>';
    return;
  }}
  box.innerHTML = rows.map(function(L) {{
    var nm = L['Name'] || '(no name)';
    var ph = L['Phone'] || '';
    var rs = svJS(L['Reason']);
    var st = svJS(L['Status']) || 'New';
    var src = L['Source'] || '';
    var dt = (L['Created'] || '').slice(0, 10);
    var col = _STATUS_COLORS[st] || '#6b7280';
    var line2 = '';
    if (ph) line2 += esc(ph);
    if (rs) line2 += (line2 ? ' • ' : '') + esc(rs);
    var line3parts = [];
    if (dt) line3parts.push(esc(dt));
    if (src) line3parts.push(esc(src));
    var line3 = line3parts.join(' · ');
    return '<div onclick="openLeadModal('+L.id+')" '
         + 'style="padding:10px 0;border-bottom:1px solid var(--border);cursor:pointer">'
         + '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">'
         + '<span style="font-weight:600">'+esc(nm)+'</span>'
         + '<span style="background:'+col+'22;color:'+col+';font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600;white-space:nowrap">'+esc(st)+'</span>'
         + '</div>'
         + (line2 ? '<div style="color:var(--text2);font-size:12px;margin-top:2px">'+line2+'</div>' : '')
         + (line3 ? '<div style="color:var(--text3);font-size:11px;margin-top:2px">'+line3+'</div>' : '')
         + '</div>';
  }}).join('');
}}

// ── Data load ────────────────────────────────────────────────────────
async function loadLeads() {{
  try {{
    var rows = await fetchAll({T_LEADS});
    rows.sort(function(a, b) {{ return (b.Created || '').localeCompare(a.Created || ''); }});
    _leads = rows;
    applyFilters();
  }} catch (e) {{
    var box = document.getElementById('leads-list');
    if (box) {{
      box.innerHTML = '<div style="color:#ef4444;padding:20px;text-align:center">'
                    + 'Failed to load leads. '
                    + '<button onclick="loadLeads()" style="margin-left:8px;background:none;color:#3b82f6;'
                    + 'border:1px solid var(--border);border-radius:6px;padding:4px 10px;cursor:pointer">Retry</button></div>';
    }}
  }}
}}

async function loadEvents() {{
  _events = await fetchAll({T_EVENTS});
  _events.sort(function(a, b) {{ return (b['Event Date']||'').localeCompare(a['Event Date']||''); }});
  var sel = document.getElementById('lf-event');
  if (!sel) return;
  // Clear any prior options past index 0 (the placeholder)
  while (sel.options.length > 1) sel.remove(1);
  _events.forEach(function(e) {{
    var name = e['Name'] || '(unnamed)';
    var date = e['Event Date'] || '';
    var status = e['Event Status'];
    if (typeof status === 'object' && status) status = status.value || '';
    var opt = document.createElement('option');
    opt.value = e.id;
    opt.textContent = name + (date ? ' (' + date + ')' : '') + (status ? ' - ' + status : '');
    sel.appendChild(opt);
  }});
}}

async function loadCompanies() {{
  try {{
    var rows = await fetchAll({T_COMPANIES});
    var dl = document.getElementById('lf-company-list');
    if (!dl) return;
    dl.innerHTML = '';
    rows.sort(function(a, b) {{ return (a.Name || '').localeCompare(b.Name || ''); }});
    rows.forEach(function(c) {{
      if (!c.Name) return;
      _COMPANIES_LOOKUP[c.Name.trim().toLowerCase()] = c.id;
      var opt = document.createElement('option');
      opt.value = c.Name;
      dl.appendChild(opt);
    }});
  }} catch (e) {{
    // Non-fatal: form still works without company linking
  }}
}}

function resolveCompanyId(input) {{
  var name = (input || '').trim().toLowerCase();
  if (!name) return null;
  return _COMPANIES_LOOKUP[name] || null;
}}

// Wire the company-autocomplete hint once at init.
(function() {{
  var inp = document.getElementById('lf-company');
  var hint = document.getElementById('lf-company-hint');
  if (!inp || !hint) return;
  inp.addEventListener('input', function() {{
    var v = inp.value.trim();
    if (!v) {{ hint.textContent = ''; hint.style.color = 'var(--text3)'; return; }}
    var id = resolveCompanyId(v);
    if (id) {{
      hint.style.color = '#059669';
      hint.textContent = '✓ Match found — this lead will be linked to the company.';
    }} else {{
      hint.style.color = 'var(--text3)';
      hint.textContent = 'No exact match (will be saved as free-text source).';
    }}
  }});
}})();

// ── Capture modal open/close + submit ───────────────────────────────
function openCaptureModal() {{
  resetCaptureForm();
  document.getElementById('capture-modal-bg').style.display = 'flex';
  document.body.style.overflow = 'hidden';
  setTimeout(function() {{
    var nm = document.getElementById('lf-name');
    if (nm) nm.focus();
  }}, 50);
}}

function closeCaptureModal() {{
  document.getElementById('capture-modal-bg').style.display = 'none';
  document.body.style.overflow = '';
}}

function resetCaptureForm() {{
  ['lf-name','lf-phone','lf-email','lf-service','lf-event','lf-company','lf-notes'].forEach(function(id) {{
    var el = document.getElementById(id);
    if (el) el.value = '';
  }});
  var st = document.getElementById('lf-status'); if (st) st.textContent = '';
  var hint = document.getElementById('lf-company-hint'); if (hint) hint.textContent = '';
  var btn = document.getElementById('lf-submit');
  if (btn) {{ btn.disabled = false; btn.textContent = 'Submit Lead'; }}
}}

async function submitLead() {{
  var name = (document.getElementById('lf-name').value || '').trim();
  var phone = (document.getElementById('lf-phone').value || '').trim();
  var email = (document.getElementById('lf-email').value || '').trim();
  var service = document.getElementById('lf-service').value;
  var eventId = document.getElementById('lf-event').value;
  var notes = (document.getElementById('lf-notes').value || '').trim();
  var st = document.getElementById('lf-status');
  var btn = document.getElementById('lf-submit');

  if (!name || !phone) {{
    st.style.color = '#ef4444'; st.textContent = 'Name and phone are required'; return;
  }}
  if (!service) {{
    st.style.color = '#ef4444'; st.textContent = 'Please select a service'; return;
  }}

  btn.disabled = true; btn.textContent = 'Saving…';
  st.textContent = '';

  var companyName = (document.getElementById('lf-company').value || '').trim();
  var companyId   = resolveCompanyId(companyName);
  try {{
    var r = await fetch('/api/leads/capture', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        name: name, phone: phone, email: email, service: service,
        event_id: eventId ? parseInt(eventId) : null,
        notes: notes,
        company_id: companyId || null,
      }})
    }});
    var d = await r.json();
    if (d.ok) {{
      closeCaptureModal();
      // Briefly flash a success message at the top of the list
      var box = document.getElementById('leads-list');
      if (box) {{
        var toast = document.createElement('div');
        toast.textContent = '✅ Lead captured';
        toast.style.cssText = 'background:#05966922;color:#059669;padding:10px;border-radius:8px;'
                            + 'text-align:center;font-weight:600;margin-bottom:10px;font-size:13px';
        box.parentNode.insertBefore(toast, box);
        setTimeout(function() {{ toast.remove(); }}, 2500);
      }}
      await loadLeads();
    }} else {{
      st.style.color = '#ef4444';
      st.textContent = 'Failed: ' + (d.error || 'unknown');
      btn.disabled = false; btn.textContent = 'Submit Lead';
    }}
  }} catch (e) {{
    st.style.color = '#ef4444';
    st.textContent = 'Error: ' + e.message;
    btn.disabled = false; btn.textContent = 'Submit Lead';
  }}
}}

// After a detail-modal save, refresh the list so edits show.
window._afterLeadSave = loadLeads;

// ── Init ────────────────────────────────────────────────────────────
renderStatusChips();
loadLeads();
loadEvents();
loadCompanies();
"""
    script_js = js + LEAD_MODAL_JS
    return _mobile_page('m_lead', 'Leads', body, script_js, br, bt, user=user)




def _mobile_log_page(br: str, bt: str, user: dict = None) -> str:
    user = user or {}
    user_name = user.get('name', '')
    body = (
        '<div class="mobile-hdr">'
        '<div><div class="mobile-hdr-title">Log Activity</div>'
        '<div class="mobile-hdr-sub">Select a form to get started</div></div>'
        '<button class="m-hamburger" onclick="openMDrawer()" aria-label="Menu">☰</button>'
        '</div>'
        '<div class="mobile-body">'
        # Cards (single-column on mobile via CSS)
        '<div class="gfr-grid" style="margin-top:4px">'
        '<div class="gfr-card" onclick="openGFRForm(\'Business Outreach Log\')">'
        '<div class="gfr-card-icon">\U0001f3e2</div>'
        '<div class="gfr-card-name">Business Outreach Log</div>'
        '<div class="gfr-card-desc">Door-to-door visit, massage box placement, and program interest</div>'
        '<div class="gfr-card-cta">Open →</div></div>'
        '<div class="gfr-card" onclick="openGFRForm(\'External Event\')">'
        '<div class="gfr-card-icon">\U0001f3aa</div>'
        '<div class="gfr-card-name">External Event</div>'
        '<div class="gfr-card-desc">Pre-event planning and community event demographic intel</div>'
        '<div class="gfr-card-cta">Open →</div></div>'
        '<div class="gfr-card" onclick="openGFRForm(\'Mobile Massage Service\')">'
        '<div class="gfr-card-icon">\U0001f486</div>'
        '<div class="gfr-card-name">Mobile Massage Service</div>'
        '<div class="gfr-card-desc">Book a mobile chair or table massage at a company or event</div>'
        '<div class="gfr-card-cta">Open →</div></div>'
        '<div class="gfr-card" onclick="openGFRForm(\'Lunch and Learn\')">'
        '<div class="gfr-card-icon">\U0001f37d️</div>'
        '<div class="gfr-card-name">Lunch and Learn</div>'
        '<div class="gfr-card-desc">Schedule a chiropractic L&amp;L presentation for company staff</div>'
        '<div class="gfr-card-cta">Open →</div></div>'
        '<div class="gfr-card" onclick="openGFRForm(\'Health Assessment Screening\')">'
        '<div class="gfr-card-icon">\U0001fa7a</div>'
        '<div class="gfr-card-name">Health Assessment Screening</div>'
        '<div class="gfr-card-desc">Book a chiropractic health screening event for staff</div>'
        '<div class="gfr-card-cta">Open →</div></div>'
        '</div>'
        '</div>'
    )
    script_js = f"const GFR_USER={repr(user_name)};\nconst TOOL = {{venuesT: {T_GOR_VENUES}}};\n"
    return _mobile_page('m_log', 'Log Activity', body, script_js, br, bt, user=user,
                         extra_html=GFR_EXTRA_HTML, extra_js=GFR_EXTRA_JS)
