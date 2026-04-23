"""Recent activity feed."""

from hub.shared import (
    _mobile_page,
    T_GOR_VENUES, T_GOR_ACTS,
)
from hub.guerilla import GFR_EXTRA_HTML, GFR_EXTRA_JS


def _mobile_recent_page(br: str, bt: str, user: dict = None) -> str:
    user = user or {}
    user_name = user.get('name', '')
    body = (
        '<div class="mobile-hdr">'
        '<div><div class="mobile-hdr-title">Recent Activity</div>'
        '<div class="mobile-hdr-sub">Your last 20 field logs</div></div>'
        '<button class="m-hamburger" onclick="openMDrawer()" aria-label="Menu">☰</button>'
        '</div>'
        '<div class="mobile-body">'
        '<div class="stats-row" style="margin-bottom:14px">'
        '<div class="stat-chip c-blue"><div class="label">Today</div><div class="value" id="rec-kpi-today">\u2014</div></div>'
        '<div class="stat-chip c-green"><div class="label">This Week</div><div class="value" id="rec-kpi-week">\u2014</div></div>'
        '<div class="stat-chip c-orange"><div class="label">By You</div><div class="value" id="rec-kpi-mine">\u2014</div></div>'
        '</div>'
        '<div id="recent-body">'
        '<div class="loading">Loading\u2026</div>'
        '</div>'
        '</div>'
    )
    recent_js = f"""
const MY_NAME = {repr(user_name)};
const GFR_TYPES = ['Business Outreach Log','External Event','Mobile Massage Service','Lunch and Learn','Health Assessment Screening'];

async function loadRecent() {{
  var acts = await fetchAll({T_GOR_ACTS});
  // Filter to GFR types, sort newest first
  var mine = acts.filter(function(r) {{
    var t = r['Type'] ? (r['Type'].value || r['Type']) : '';
    return GFR_TYPES.indexOf(t) >= 0;
  }});
  // KPI computation before sort/slice
  var today = new Date().toISOString().slice(0,10);
  var weekAgo = new Date(Date.now() - 7*86400000).toISOString().slice(0,10);
  var kToday = 0, kWeek = 0, kMine = 0;
  var lowMine = (MY_NAME || '').toLowerCase();
  mine.forEach(function(r) {{
    var d = (r['Date']||'').slice(0,10);
    if (d === today) kToday++;
    if (d >= weekAgo) kWeek++;
    var who = r['Recorded By'] || r['Author'] || '';
    if (who && typeof who === 'string' && lowMine && who.toLowerCase().indexOf(lowMine) !== -1) kMine++;
  }});
  document.getElementById('rec-kpi-today').textContent = kToday;
  document.getElementById('rec-kpi-week').textContent = kWeek;
  document.getElementById('rec-kpi-mine').textContent = kMine;

  mine.sort(function(a,b){{return (b['Date']||'').localeCompare(a['Date']||'');}});
  mine = mine.slice(0,20);
  var body = document.getElementById('recent-body');
  if (!mine.length) {{
    body.innerHTML = '<div class="empty">No field activity logged yet.</div>';
    return;
  }}
  body.innerHTML = mine.map(function(r) {{
    var t = r['Type'] ? (r['Type'].value || r['Type']) : 'Activity';
    var biz = r['Business'] && r['Business'].length ? esc(r['Business'][0].value||'\u2014') : '\u2014';
    var contact = esc(r['Contact Person']||'');
    var outcome = r['Outcome'] ? (r['Outcome'].value || r['Outcome']) : '';
    return '<div class="mobile-act-item">'
      + '<span class="mobile-act-type">' + esc(t) + '</span>'
      + '<div class="mobile-act-biz">' + biz + '</div>'
      + '<div class="mobile-act-meta">'
      + (contact ? contact + ' \u00b7 ' : '')
      + esc(fmt(r['Date']||''))
      + (outcome ? ' \u00b7 ' + esc(outcome) : '')
      + '</div></div>';
  }}).join('');
}}

loadRecent();
"""
    script_js = f"const GFR_USER={repr(user_name)};\nconst TOOL = {{venuesT: {T_GOR_VENUES}}};\n" + recent_js
    return _mobile_page('m_recent', 'Recent Activity', body, script_js, br, bt, user=user,
                         extra_html=GFR_EXTRA_HTML, extra_js=GFR_EXTRA_JS)
