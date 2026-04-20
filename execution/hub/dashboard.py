"""
Dashboard pages — login, hub overview, calendar, coming soon placeholders.
"""
import os

from .shared import _CSS, _page


# ──────────────────────────────────────────────────────────────────────────────
# LOGIN PAGE
# ──────────────────────────────────────────────────────────────────────────────
def _login_page(error: str = "") -> str:
    if error == "domain":
        err = '<p class="login-err">Access restricted to authorized staff accounts.</p>'
    elif error:
        err = '<p class="login-err">Sign-in failed. Please try again.</p>'
    else:
        err = ''
    return (
        '<!DOCTYPE html><html lang="en">'
        '<head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Login — Reform Hub</title>'
        f'<style>{_CSS}</style>'
        '</head>'
        '<body class="login-body">'
        '<div class="login-wrap"><div class="login-box">'
        '<h1>\u2726 Reform</h1>'
        '<p class="sub">Outreach Hub — Staff Access</p>'
        '<a href="/auth/google" class="google-btn">'
        '<img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" width="20" alt="">'
        'Sign in with Google'
        '</a>'
        f'{err}'
        '</div></div>'
        '</body></html>'
    )


# ──────────────────────────────────────────────────────────────────────────────
# HUB PAGE
# ──────────────────────────────────────────────────────────────────────────────
_HUB_BODY = """
<style>
@media(min-width:769px){.content{padding:32px 40px}}
.db-topbar{display:flex;gap:24px;align-items:baseline;margin-bottom:24px;padding-bottom:14px;border-bottom:1px solid var(--border)}
.db-kpi{display:flex;flex-direction:column}
.db-kpi-val{font-size:15px;font-weight:700;line-height:1}
.db-kpi-lbl{font-size:10px;color:var(--text3);margin-top:3px}
.db-main{display:grid;grid-template-columns:1fr 380px;gap:28px}
.db-sidebar{display:grid;grid-template-rows:1fr 1fr;gap:16px}
.db-tool-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:32px}
.db-pi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.db-ql-row{display:flex;gap:10px;flex-wrap:wrap}
@media(max-width:900px){.db-main{grid-template-columns:1fr}.db-sidebar{grid-template-rows:auto auto}}
@media(max-width:768px){
  .db-topbar{gap:10px;flex-wrap:wrap}
  .db-kpi{flex:1 1 calc(50% - 5px);min-width:0}
  .db-tool-grid{grid-template-columns:1fr;margin-bottom:20px}
  .db-pi-grid{grid-template-columns:repeat(2,1fr)}
  .db-card{padding:14px 16px}
  .db-card-row{gap:14px}
  .db-ql-row > a{flex:1 1 100%;min-width:0}
}
@media(max-width:500px){
  .db-kpi{flex-basis:100%}
  .db-pi-grid{grid-template-columns:1fr}
}
.db-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px 22px}
.db-card-hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px}
.db-card-title{font-size:13px;font-weight:700;color:var(--text)}
.db-card-pill{font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px}
.db-card-val{font-size:26px;font-weight:700;line-height:1}
.db-card-sub{font-size:11px;color:var(--text3);margin-top:6px}
.db-card-row{display:flex;gap:20px;margin-top:14px}
.db-card-mini{text-align:center}
.db-card-mini .n{font-size:15px;font-weight:700}
.db-card-mini .l{font-size:10px;color:var(--text3)}
.db-sect{font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text3);margin:0 0 14px;letter-spacing:0.6px}
.db-link{text-decoration:none;display:flex;align-items:center;gap:8px;padding:10px 14px;transition:border-color .12s;flex:1;min-width:0}
.db-link:hover{border-color:var(--text3) !important}
.db-link-icon{font-size:18px;flex-shrink:0}
.db-link-txt{font-size:12px;font-weight:600;color:var(--text)}
.db-link-sub{font-size:9px;color:var(--text3)}
</style>

<!-- Main 2-column layout -->
<div class="db-main">

  <!-- LEFT COLUMN -->
  <div>
    <!-- KPI bar -->
    <div class="db-topbar">
      <div class="db-kpi"><div class="db-kpi-val" id="s-total">--</div><div class="db-kpi-lbl">Total Venues</div></div>
      <div class="db-kpi"><div class="db-kpi-val" id="s-active" style="color:#059669">--</div><div class="db-kpi-lbl">Active Relationships</div></div>
      <div class="db-kpi"><div class="db-kpi-val" id="s-pipeline" style="color:#7c3aed">--</div><div class="db-kpi-lbl">PI Pipeline</div></div>
      <div class="db-kpi"><div class="db-kpi-val" id="s-attention" style="color:#ef4444">--</div><div class="db-kpi-lbl">Needs Attention</div></div>
    </div>

    <!-- Outreach tool cards -->
    <div class="db-sect">Outreach</div>
    <div class="db-tool-grid" id="tool-cards">
      <div class="db-card"><div class="loading">Loading\u2026</div></div>
      <div class="db-card"><div class="loading">Loading\u2026</div></div>
      <div class="db-card"><div class="loading">Loading\u2026</div></div>
    </div>

    <!-- PI Cases -->
    <div class="db-sect">PI Cases</div>
    <div class="db-pi-grid">
      <div class="db-card">
        <div class="db-card-hd"><span class="db-card-title">Active</span><span class="db-card-pill" style="background:#7c3aed22;color:#7c3aed">Treatment</span></div>
        <div class="db-card-val" id="pi-active" style="color:#7c3aed">--</div>
      </div>
      <div class="db-card">
        <div class="db-card-hd"><span class="db-card-title">Billed</span><span class="db-card-pill" style="background:#fbbf2422;color:#d97706">Pending</span></div>
        <div class="db-card-val" id="pi-billed" style="color:#d97706">--</div>
      </div>
      <div class="db-card">
        <div class="db-card-hd"><span class="db-card-title">Awaiting</span><span class="db-card-pill" style="background:#ea580c22;color:#ea580c">Negotiation</span></div>
        <div class="db-card-val" id="pi-awaiting" style="color:#ea580c">--</div>
      </div>
      <div class="db-card">
        <div class="db-card-hd"><span class="db-card-title">Closed</span><span class="db-card-pill" style="background:#05966922;color:#059669">Settled</span></div>
        <div class="db-card-val" id="pi-closed" style="color:#059669">--</div>
      </div>
    </div>
  </div>

  <!-- RIGHT COLUMN (sidebar) -->
  <div class="db-sidebar">
    <!-- Priority Alerts -->
    <div class="panel" style="margin:0;display:flex;flex-direction:column;overflow:hidden">
      <div class="panel-hd">
        <span class="panel-title">Priority Alerts</span>
        <span class="panel-ct" id="alerts-ct">\u2014</span>
      </div>
      <div class="panel-body" id="alerts-body" style="flex:1;overflow-y:auto"><div class="loading">Loading\u2026</div></div>
    </div>

    <!-- Upcoming -->
    <div class="panel" style="margin:0;display:flex;flex-direction:column;overflow:hidden">
      <div class="panel-hd">
        <span class="panel-title">Upcoming This Week</span>
        <span class="panel-ct" id="upcoming-ct">\u2014</span>
      </div>
      <div class="panel-body" id="upcoming-body" style="flex:1;overflow-y:auto"><div class="loading">Loading\u2026</div></div>
    </div>
  </div>

</div>

<!-- Quick Links — horizontal row -->
<div style="margin-top:24px">
  <div class="db-sect">Quick Links</div>
  <div class="db-ql-row">
    <a href="/outreach/planner" class="db-card db-link">
      <div class="db-link-icon">\U0001f5fa\ufe0f</div>
      <div><div class="db-link-txt">Route Planner</div><div class="db-link-sub">Plan outreach routes</div></div>
    </a>
    <a href="/outreach/list" class="db-card db-link">
      <div class="db-link-icon">\U0001f4cb</div>
      <div><div class="db-link-txt">Routes List</div><div class="db-link-sub">All venues by status</div></div>
    </a>
    <a href="/social/poster" class="db-card db-link">
      <div class="db-link-icon">\U0001f3a8</div>
      <div><div class="db-link-txt">Social Poster</div><div class="db-link-sub">Create content</div></div>
    </a>
    <a href="/social" class="db-card db-link">
      <div class="db-link-icon">\U0001f4c5</div>
      <div><div class="db-link-txt">Social Schedule</div><div class="db-link-sub">Content queue</div></div>
    </a>
    <a href="/contacts" class="db-card db-link">
      <div class="db-link-icon">\U0001f4e7</div>
      <div><div class="db-link-txt">Communications</div><div class="db-link-sub">Email contacts</div></div>
    </a>
  </div>
</div>

<!-- Calendar — full width bottom -->
<div style="margin-top:24px">
  <div class="db-sect">Calendar</div>
  <div class="db-card" style="padding:0;overflow:hidden;height:clamp(260px,55vh,440px)" id="db-cal-wrap">
    <div class="loading" style="padding:20px">Loading calendar\u2026</div>
  </div>
</div>
"""

# Shared calendar widget JS — used by both the dashboard (`_hub_page`) and the
# full `/calendar` page (`_calendar_page`). Expects a `<div id="db-cal-wrap">`
# somewhere in the body. Globals `esc` and `fetch` are the only dependencies.
_CAL_WIDGET_JS = """
// Calendar widget: mini month grid + upcoming events list
async function loadCalendarWidget() {
  var wrap = document.getElementById('db-cal-wrap');
  renderCalendarShell(wrap);
  try {
    var r = await fetch('/api/calendar/events');
    if (r.status === 401) {
      setCalendarError(wrap, 'Calendar access expired', 'Sign out to refresh \u2192');
      return;
    }
    if (!r.ok) {
      setCalendarError(wrap, "Couldn't load calendar", 'Sign out to re-authenticate \u2192');
      return;
    }
    var data = await r.json();
    populateCalendarEvents(wrap, data.items || []);
  } catch(e) {
    setCalendarError(wrap, 'Calendar unavailable', '');
  }
}

function renderCalendarShell(wrap) {
  var now = new Date();
  var year = now.getFullYear();
  var month = now.getMonth();
  var monthName = now.toLocaleDateString('en-US', {month:'long', year:'numeric'});
  var firstOfMonth = new Date(year, month, 1);
  var leadingBlanks = firstOfMonth.getDay();
  var daysInMonth   = new Date(year, month + 1, 0).getDate();
  var daysPrevMonth = new Date(year, month, 0).getDate();
  var todayKey = now.toISOString().substring(0, 10);

  var cells = '';
  for (var i = leadingBlanks - 1; i >= 0; i--) {
    var d = daysPrevMonth - i;
    cells += '<div class="cal-day-cell other-month">' + d + '</div>';
  }
  for (var d = 1; d <= daysInMonth; d++) {
    var dateKey = year + '-' + String(month + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
    var cls = 'cal-day-cell';
    if (dateKey === todayKey) cls += ' today';
    cells += '<div class="' + cls + '" data-date="' + dateKey + '">' + d + '</div>';
  }
  var totalCells = leadingBlanks + daysInMonth;
  var trailingBlanks = (7 - (totalCells % 7)) % 7;
  for (var d = 1; d <= trailingBlanks; d++) {
    cells += '<div class="cal-day-cell other-month">' + d + '</div>';
  }

  wrap.innerHTML = ''
    + '<div class="cal-wrap">'
    +   '<div class="cal-month">'
    +     '<div class="cal-month-hdr">'
    +       '<div class="cal-month-title">' + esc(monthName) + '</div>'
    +       '<a href="/calendar" class="cal-month-sub" style="text-decoration:none">Open \u2192</a>'
    +     '</div>'
    +     '<div class="cal-weekdays"><div>S</div><div>M</div><div>T</div><div>W</div><div>T</div><div>F</div><div>S</div></div>'
    +     '<div class="cal-days" id="cal-days">' + cells + '</div>'
    +   '</div>'
    +   '<div class="cal-upcoming" id="cal-upcoming">'
    +     '<div class="cal-empty-msg">Loading events\u2026</div>'
    +   '</div>'
    + '</div>';
}

function populateCalendarEvents(wrap, items) {
  var eventDays = new Set();
  items.forEach(function(ev) {
    var d;
    if (ev.allDay) d = (ev.start || '').substring(0, 10);
    else if (ev.start) d = new Date(ev.start).toISOString().substring(0, 10);
    else return;
    eventDays.add(d);
  });
  eventDays.forEach(function(dateKey) {
    var cell = wrap.querySelector('.cal-day-cell[data-date="' + dateKey + '"]');
    if (cell) cell.classList.add('has-events');
  });

  var upcoming = document.getElementById('cal-upcoming');
  if (!items.length) {
    upcoming.innerHTML = '<div class="cal-empty-msg">No upcoming events</div>';
    return;
  }
  var groups = {};
  var order  = [];
  items.slice(0, 10).forEach(function(ev) {
    var d;
    if (ev.allDay) d = (ev.start || '').substring(0, 10);
    else           d = new Date(ev.start).toISOString().substring(0, 10);
    if (!groups[d]) { groups[d] = []; order.push(d); }
    groups[d].push(ev);
  });
  var today = new Date();
  var todayKey = today.toISOString().substring(0, 10);
  var tomorrow = new Date(today.getTime() + 86400000).toISOString().substring(0, 10);

  var html = '<div class="cal-upcoming-hdr">Upcoming</div>';
  order.forEach(function(d) {
    var dateObj = new Date(d + 'T00:00:00');
    var label;
    if (d === todayKey)      label = 'Today';
    else if (d === tomorrow) label = 'Tomorrow';
    else label = dateObj.toLocaleDateString('en-US', {weekday:'short', month:'short', day:'numeric'});
    html += '<div class="cal-day"><div class="cal-day-hdr">' + esc(label) + '</div>';
    groups[d].forEach(function(ev) {
      var timeStr;
      if (ev.allDay) timeStr = 'all day';
      else {
        var t = new Date(ev.start);
        timeStr = t.toLocaleTimeString('en-US', {hour:'numeric', minute:'2-digit'});
      }
      html += '<div class="cal-evt">';
      html += '<div class="cal-evt-time">' + esc(timeStr) + '</div>';
      html += '<div class="cal-evt-title">';
      if (ev.link) html += '<a href="' + esc(ev.link) + '" target="_blank" style="color:inherit">' + esc(ev.summary) + '</a>';
      else         html += esc(ev.summary);
      if (ev.location) html += '<div class="cal-evt-loc">' + esc(ev.location) + '</div>';
      html += '</div></div>';
    });
    html += '</div>';
  });
  upcoming.innerHTML = html;
}

function setCalendarError(wrap, title, linkText) {
  var upcoming = document.getElementById('cal-upcoming');
  var linkHtml = linkText ? '<a href="/logout">' + esc(linkText) + '</a>' : '';
  if (upcoming) {
    upcoming.innerHTML = '<div class="cal-empty-msg">' + esc(title) + '<br>' + linkHtml + '</div>';
  } else {
    wrap.innerHTML = '<div class="cal-err"><div>' + esc(title) + '</div>' + linkHtml + '</div>';
  }
}

loadCalendarWidget();
"""


def _hub_page(br: str, bt: str, user: dict = None) -> str:
    header = (
        '<div class="header">'
        '<div class="header-left">'
        '<h1>Dashboard</h1>'
        '<div class="sub">Reform Chiropractic Operations Hub</div>'
        '</div>'
        '<div class="header-right"></div>'
        '</div>'
    )
    js = f"""
const TOOLS = [
  {{key: 'att', label: 'PI Attorney',  color: '#7c3aed', activeStatus: 'Active Relationship', badge: 'b-pi',  short: 'PI', href: '/attorney'}},
  {{key: 'gor', label: 'Guerilla Mktg', color: '#ea580c', activeStatus: 'Active Partner',      badge: 'b-gor', short: 'G',  href: '/guerilla'}},
  {{key: 'com', label: 'Community',      color: '#059669', activeStatus: 'Active Partner',      badge: 'b-com', short: 'C',  href: '/community'}},
];

async function load() {{
  var resp;
  for (var attempt = 0; attempt < 3; attempt++) {{
    try {{
      resp = await fetch('/api/dashboard');
      if (resp.ok) break;
    }} catch(e) {{}}
    if (attempt < 2) await new Promise(ok => setTimeout(ok, 1000 * (attempt + 1)));
  }}
  if (!resp || !resp.ok) return;
  const data = await resp.json();

  const stats = TOOLS.map(tool => {{
    const rows = data[tool.key] || [];
    let active = 0, overdue = 0, today = 0;
    const alerts = [], upcoming = [];
    for (const row of rows) {{
      const status = sv(row.cs);
      const du = daysUntil(row.fu);
      const name = esc(row.n || '(unnamed)');
      if (status === tool.activeStatus) active++;
      if (du !== null && du < 0)  {{ overdue++; alerts.push({{name, du, badge: tool.badge, short: tool.short}}); }}
      if (du === 0)                {{ today++;   alerts.push({{name, du, badge: tool.badge, short: tool.short}}); }}
      if (du !== null && du > 0 && du <= 7) {{ upcoming.push({{name, du, badge: tool.badge, short: tool.short, date: row.fu}}); }}
    }}
    return {{total: rows.length, active, overdue, today, alerts, upcoming, tool}};
  }});

  const totals = stats.reduce((a, s) => ({{
    total: a.total + s.total, active: a.active + s.active,
    overdue: a.overdue + s.overdue, today: a.today + s.today,
  }}), {{total:0, active:0, overdue:0, today:0}});

  // Box alerts
  let boxAlerts = 0;
  (data.boxes || []).forEach(b => {{
    if (sv(b.s) !== 'Active' || !b.d) return;
    const age = -(daysUntil(b.d) || 0);
    const pickupDays = parseInt(b.p) || 14;
    if (age >= pickupDays) boxAlerts++;
  }});

  document.getElementById('s-total').textContent = totals.total;
  document.getElementById('s-active').textContent = totals.active;
  document.getElementById('s-attention').textContent = totals.overdue + totals.today + boxAlerts;
  document.getElementById('s-pipeline').textContent = (data.pi.a || 0) + (data.pi.b || 0) + (data.pi.w || 0);

  // PI counts
  document.getElementById('pi-active').textContent   = data.pi.a || 0;
  document.getElementById('pi-billed').textContent   = data.pi.b || 0;
  document.getElementById('pi-awaiting').textContent = data.pi.w || 0;
  document.getElementById('pi-closed').textContent   = data.pi.c || 0;

  // Tool cards
  document.getElementById('tool-cards').innerHTML = stats.map(s => `
    <div class="db-card" style="border-left:3px solid ${{s.tool.color}}">
      <div class="db-card-hd">
        <span class="db-card-title">${{esc(s.tool.label)}}</span>
        <span class="db-card-pill" style="background:${{s.tool.color}}22;color:${{s.tool.color}}">${{s.active}} active</span>
      </div>
      <div class="db-card-row">
        <div class="db-card-mini"><div class="n">${{s.total}}</div><div class="l">Total</div></div>
        <div class="db-card-mini"><div class="n" style="color:#ef4444">${{s.overdue}}</div><div class="l">Overdue</div></div>
        <div class="db-card-mini"><div class="n" style="color:#f59e0b">${{s.today}}</div><div class="l">Today</div></div>
      </div>
      <a href="${{s.tool.href}}" style="display:block;text-align:center;margin-top:10px;font-size:11px;color:${{s.tool.color}};text-decoration:none;font-weight:600">Open Dashboard \u2192</a>
    </div>
  `).join('');

  // Alerts
  const allAlerts = stats.flatMap(s => s.alerts).sort((a,b) => a.du - b.du);
  document.getElementById('alerts-ct').textContent = allAlerts.length + ' items';
  document.getElementById('alerts-body').innerHTML = allAlerts.length ? allAlerts.slice(0,10).map(a => `
    <div class="a-row">
      <div class="dot ${{a.du < 0 ? 'dot-r' : 'dot-y'}}"></div>
      <span class="a-name">${{a.name}}</span>
      <span class="badge ${{a.badge}}">${{a.short}}</span>
      <span class="a-meta" style="color:${{a.du < 0 ? '#ef4444' : '#fbbf24'}}">${{a.du === 0 ? 'Today' : Math.abs(a.du) + 'd overdue'}}</span>
    </div>
  `).join('') : '<div class="empty">No overdue or due-today items \u2713</div>';

  // Upcoming
  const allUpcoming = stats.flatMap(s => s.upcoming).sort((a,b) => a.du - b.du);
  document.getElementById('upcoming-ct').textContent = allUpcoming.length + ' this week';
  document.getElementById('upcoming-body').innerHTML = allUpcoming.length ? allUpcoming.slice(0,10).map(a => `
    <div class="a-row">
      <div class="dot dot-g"></div>
      <span class="a-name">${{a.name}}</span>
      <span class="badge ${{a.badge}}">${{a.short}}</span>
      <span class="date-badge">${{fmt(a.date)}}</span>
    </div>
  `).join('') : '<div class="empty">Nothing due this week</div>';

  stampRefresh();
}}

load();

{_CAL_WIDGET_JS}
"""
    return _page('hub', 'Dashboard', header, _HUB_BODY, js, br, bt, user=user)


# ──────────────────────────────────────────────────────────────────────────────
# CALENDAR PAGE
# ──────────────────────────────────────────────────────────────────────────────
def _calendar_page(br: str, bt: str, user: dict = None) -> str:
    header = (
        '<div class="header"><div class="header-left">'
        '<h1>\U0001f4c5 Calendar</h1>'
        '<div class="sub">Follow-up and scheduling calendar</div>'
        '</div></div>'
    )
    body = (
        '<div class="cal-full">'
        '<div class="db-card" id="db-cal-wrap">'
        '<div class="loading" style="padding:20px">Loading calendar\u2026</div>'
        '</div>'
        '</div>'
    )
    return _page('calendar', 'Calendar', header, body, _CAL_WIDGET_JS, br, bt, user=user)


# ──────────────────────────────────────────────────────────────────────────────
# COMING SOON PLACEHOLDER
# ──────────────────────────────────────────────────────────────────────────────
def _coming_soon_page(active_key: str, title: str, br: str, bt: str, user: dict = None) -> str:
    header = (
        f'<div class="header"><div class="header-left">'
        f'<h1>{title}</h1><div class="sub">Coming soon</div>'
        f'</div></div>'
    )
    body = '<div class="empty" style="padding:60px;font-size:15px">\U0001f6a7 This section is under construction</div>'
    return _page(active_key, title, header, body, '', br, bt, user=user)
