"""Lead capture form + legacy log redirect."""

from hub.shared import (
    _mobile_page,
    T_GOR_VENUES, T_EVENTS, T_COMPANIES,
)
from hub.guerilla import GFR_EXTRA_HTML, GFR_EXTRA_JS


def _mobile_lead_capture_page(br: str, bt: str, user: dict = None) -> str:
    user = user or {}
    user_name = user.get('name', '')
    user_email = (user.get('email', '') or '').strip()
    body = (
        '<div class="mobile-hdr">'
        '<div><div class="mobile-hdr-title">Capture Lead</div>'
        '<div class="mobile-hdr-sub">Log a new potential patient</div></div>'
        '<button class="m-hamburger" onclick="openMDrawer()" aria-label="Menu">☰</button>'
        '</div>'
        '<div class="mobile-body">'
        '<div id="lead-form" style="padding:4px 0">'
        # Name
        '<div style="margin-bottom:14px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Name *</label>'
        '<input type="text" id="lf-name" placeholder="Full name" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box">'
        '</div>'
        # Phone
        '<div style="margin-bottom:14px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Phone *</label>'
        '<input type="tel" id="lf-phone" placeholder="(555) 123-4567" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box">'
        '</div>'
        # Email
        '<div style="margin-bottom:14px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Email</label>'
        '<input type="email" id="lf-email" placeholder="email@example.com" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box">'
        '</div>'
        # Service Interested
        '<div style="margin-bottom:14px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Service Interested *</label>'
        '<select id="lf-service" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box;appearance:auto">'
        '<option value="">Select a service\u2026</option>'
        '<option value="Chiropractic Care">Chiropractic Care</option>'
        '<option value="Massage Therapy">Massage Therapy</option>'
        '<option value="Health Screening">Health Screening</option>'
        '<option value="Injury Rehab">Injury Rehab</option>'
        '<option value="Other">Other</option>'
        '</select>'
        '</div>'
        # Event (dropdown loaded from API)
        '<div style="margin-bottom:14px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Event / Source</label>'
        '<select id="lf-event" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box;appearance:auto">'
        '<option value="">No event (walk-in / field)</option>'
        '</select>'
        '</div>'
        # Referred from company — autocompletes from T_COMPANIES. If a match is
        # picked, the backend marks that company as "Contacted" + logs activity.
        '<div style="margin-bottom:14px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Referred from company (optional)</label>'
        '<input type="text" id="lf-company" list="lf-company-list" placeholder="Type to search…" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box">'
        '<datalist id="lf-company-list"></datalist>'
        '<div id="lf-company-hint" style="font-size:11px;color:var(--text3);margin-top:4px;min-height:14px"></div>'
        '</div>'
        # Notes
        '<div style="margin-bottom:18px">'
        '<label style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;display:block;margin-bottom:4px">Notes</label>'
        '<textarea id="lf-notes" rows="3" placeholder="Additional details\u2026" '
        'style="width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);'
        'border-radius:8px;padding:10px 12px;font-size:14px;box-sizing:border-box;resize:vertical;font-family:inherit"></textarea>'
        '</div>'
        # Submit
        '<button id="lf-submit" onclick="submitLead()" '
        'style="width:100%;background:#ea580c;color:#fff;border:none;border-radius:8px;'
        'padding:14px;font-size:15px;font-weight:700;cursor:pointer">'
        'Submit Lead</button>'
        '<div id="lf-status" style="text-align:center;margin-top:10px;font-size:13px;min-height:20px"></div>'
        '</div>'
        # Success view (hidden initially)
        '<div id="lead-success" style="display:none;text-align:center;padding:40px 0">'
        '<div style="font-size:40px;margin-bottom:12px">\u2705</div>'
        '<div style="font-size:18px;font-weight:700;color:var(--text);margin-bottom:6px">Lead Captured!</div>'
        '<div style="font-size:13px;color:var(--text3);margin-bottom:20px">The lead has been saved successfully.</div>'
        '<button onclick="resetForm()" '
        'style="background:#ea580c;color:#fff;border:none;border-radius:8px;'
        'padding:12px 24px;font-size:14px;font-weight:600;cursor:pointer">'
        'Capture Another</button>'
        '</div>'
        '</div>'
    )
    js = f"""
var _events = [];

async function loadEvents() {{
  _events = await fetchAll({T_EVENTS});
  // Sort by date descending, show recent first
  _events.sort(function(a,b) {{ return (b['Event Date']||'').localeCompare(a['Event Date']||''); }});
  var sel = document.getElementById('lf-event');
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

// Referred-company autocomplete — populates the datalist + enables
// resolveCompanyId() lookup on submit (Feature #6).
var _COMPANIES_LOOKUP = {{}};  // lower-cased name -> id
async function loadCompanies() {{
  try {{
    var rows = await fetchAll({T_COMPANIES});
    var dl = document.getElementById('lf-company-list');
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
    st.style.color = '#ef4444';
    st.textContent = 'Name and phone are required';
    return;
  }}
  if (!service) {{
    st.style.color = '#ef4444';
    st.textContent = 'Please select a service';
    return;
  }}

  btn.disabled = true;
  btn.textContent = 'Saving\u2026';
  st.textContent = '';

  var companyName = (document.getElementById('lf-company').value || '').trim();
  var companyId   = resolveCompanyId(companyName);
  try {{
    var r = await fetch('/api/leads/capture', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        name: name,
        phone: phone,
        email: email,
        service: service,
        event_id: eventId ? parseInt(eventId) : null,
        notes: notes,
        company_id: companyId || null,
      }})
    }});
    var d = await r.json();
    if (d.ok) {{
      document.getElementById('lead-form').style.display = 'none';
      document.getElementById('lead-success').style.display = 'block';
    }} else {{
      st.style.color = '#ef4444';
      st.textContent = 'Failed: ' + (d.error || 'unknown');
    }}
  }} catch(e) {{
    st.style.color = '#ef4444';
    st.textContent = 'Error: ' + e.message;
  }}
  btn.disabled = false;
  btn.textContent = 'Submit Lead';
}}

function resetForm() {{
  document.getElementById('lf-name').value = '';
  document.getElementById('lf-phone').value = '';
  document.getElementById('lf-email').value = '';
  document.getElementById('lf-service').value = '';
  document.getElementById('lf-event').value = '';
  document.getElementById('lf-notes').value = '';
  document.getElementById('lf-status').textContent = '';
  document.getElementById('lead-form').style.display = 'block';
  document.getElementById('lead-success').style.display = 'none';
  document.getElementById('lf-name').focus();
}}

loadEvents();
loadCompanies();
"""
    return _mobile_page('m_lead', 'Capture Lead', body, js, br, bt, user=user)




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
        '<div class="gfr-card-cta">Open \u2192</div></div>'
        '<div class="gfr-card" onclick="openGFRForm(\'External Event\')">'
        '<div class="gfr-card-icon">\U0001f3aa</div>'
        '<div class="gfr-card-name">External Event</div>'
        '<div class="gfr-card-desc">Pre-event planning and community event demographic intel</div>'
        '<div class="gfr-card-cta">Open \u2192</div></div>'
        '<div class="gfr-card" onclick="openGFRForm(\'Mobile Massage Service\')">'
        '<div class="gfr-card-icon">\U0001f486</div>'
        '<div class="gfr-card-name">Mobile Massage Service</div>'
        '<div class="gfr-card-desc">Book a mobile chair or table massage at a company or event</div>'
        '<div class="gfr-card-cta">Open \u2192</div></div>'
        '<div class="gfr-card" onclick="openGFRForm(\'Lunch and Learn\')">'
        '<div class="gfr-card-icon">\U0001f37d\ufe0f</div>'
        '<div class="gfr-card-name">Lunch and Learn</div>'
        '<div class="gfr-card-desc">Schedule a chiropractic L&amp;L presentation for company staff</div>'
        '<div class="gfr-card-cta">Open \u2192</div></div>'
        '<div class="gfr-card" onclick="openGFRForm(\'Health Assessment Screening\')">'
        '<div class="gfr-card-icon">\U0001fa7a</div>'
        '<div class="gfr-card-name">Health Assessment Screening</div>'
        '<div class="gfr-card-desc">Book a chiropractic health screening event for staff</div>'
        '<div class="gfr-card-cta">Open \u2192</div></div>'
        '</div>'
        '</div>'
    )
    script_js = f"const GFR_USER={repr(user_name)};\nconst TOOL = {{venuesT: {T_GOR_VENUES}}};\n"
    return _mobile_page('m_log', 'Log Activity', body, script_js, br, bt, user=user,
                         extra_html=GFR_EXTRA_HTML, extra_js=GFR_EXTRA_JS)
