"""Shared V3 visual primitives for the field-rep app.

These classes were originally inlined in pages/home.py for the V3 redesign and
are now extracted so every routes-app page can use the same look. Import
``V3_CSS`` and concatenate it into the page body once per page.

Class names match what home.py's JS already emits, so other pages can reuse
the look by emitting the same markup. New primitives added for cross-page use
are clearly marked.
"""

V3_CSS = """
<style>
/* ── KPI strip (was #kpi-strip in home.py) ───────────────────────── */
.kpi-strip { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:18px }
.kpi-strip.cols-2 { grid-template-columns:repeat(2,1fr) }
.kpi-strip.cols-4 { grid-template-columns:repeat(4,1fr) }
.kpi-card { background:var(--card); border:1px solid var(--border); border-radius:12px;
            padding:12px 8px; text-align:center; text-decoration:none; color:inherit;
            display:block }
.kpi-card:active { background:rgba(0,74,198,.06) }
.kpi-label { font-size:10px; font-weight:600; color:var(--text3);
             letter-spacing:.6px; margin-bottom:4px; text-transform:uppercase }
.kpi-val { font-size:22px; font-weight:700; color:var(--text); line-height:1 }
.kpi-val.ok     { color:#059669 }
.kpi-val.warn   { color:#d97706 }
.kpi-val.bad    { color:#ef4444 }
.kpi-val.accent { color:#004ac6 }

/* ── Section / strip header ──────────────────────────────────────── */
.strip-hdr, .section-hdr {
  display:flex; align-items:baseline; justify-content:space-between;
  margin-bottom:8px;
}
.strip-link, .section-hdr-link {
  font-size:11px; color:var(--text3); text-decoration:none;
}

/* ── Worklist / count badge (was #wl-ct in home.py) ─────────────── */
.count-badge { background:#fee2e2; color:#b91c1c; padding:2px 9px;
               border-radius:999px; font-size:11px; font-weight:600 }
.count-badge:empty { display:none }
.count-badge.blue  { background:#dbeafe; color:#1d4ed8 }
.count-badge.green { background:#d1fae5; color:#047857 }
.count-badge.gray  { background:var(--border); color:var(--text3) }

/* ── Horizontal scroll rail — generic + the events-rail name ────── */
.rail, #events-rail {
  display:flex; gap:10px; overflow-x:auto;
  -webkit-overflow-scrolling:touch; scrollbar-width:none;
  padding-bottom:4px;
}
.rail::-webkit-scrollbar, #events-rail::-webkit-scrollbar { display:none }

/* The .rail-card / .event-card pair so old + new pages can reuse. */
.rail-card, .event-card {
  min-width:180px; padding:12px; border-radius:10px;
  border:1px solid var(--border); background:var(--card);
  text-decoration:none; color:inherit; flex-shrink:0;
  display:flex; flex-direction:column; gap:2px;
}
.rail-when, .event-when {
  font-size:10px; font-weight:700; color:#004ac6;
  letter-spacing:.4px; margin-bottom:2px; text-transform:uppercase;
}
.rail-name, .event-name {
  font-size:13px; font-weight:600; color:var(--text);
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
  overflow:hidden;
}
.rail-where, .event-where {
  font-size:11px; color:var(--text3);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.rail-empty, .event-empty {
  color:var(--text3); font-size:12px; padding:14px;
  border:1px dashed var(--border); border-radius:10px;
  width:100%; text-align:center; flex-shrink:0;
}

/* ── Leaderboard / list-row card ─────────────────────────────────── */
.lb-card, #leaderboard-card {
  background:var(--card); border:1px solid var(--border);
  border-radius:12px; padding:12px 14px; margin-bottom:18px;
}
.lb-hdr { display:flex; align-items:baseline; justify-content:space-between;
          margin-bottom:8px }
.lb-metric { font-size:11px; color:var(--text3) }
.lb-row { display:grid; grid-template-columns:24px 1fr auto; gap:10px;
          align-items:center; padding:6px 0; font-size:13px }
.lb-row[data-self="1"] { background:rgba(0,74,198,.08); border-radius:6px;
                         padding:6px 8px; margin:0 -8px }
.lb-rank { color:var(--text3); font-weight:600; text-align:center }
.lb-name { color:var(--text); font-weight:500;
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis }
.lb-val { color:#004ac6; font-weight:700 }
.lb-divider { height:1px; background:var(--border); margin:6px 0 }

/* ── Soft card primitive (12px radius, 1px border) ──────────────── */
.card-soft { background:var(--card); border:1px solid var(--border);
             border-radius:12px; padding:14px; text-decoration:none; color:inherit;
             display:block }
.card-soft:active { background:rgba(0,74,198,.04) }
.card-soft + .card-soft { margin-top:10px }
.card-soft-title { font-size:14px; font-weight:700; color:var(--text);
                   margin-bottom:4px }
.card-soft-sub { font-size:11px; color:var(--text3) }
.card-row { display:flex; align-items:center; justify-content:space-between; gap:10px }

/* ── Pill / status chip (consistent across pages) ───────────────── */
.pill { display:inline-block; font-size:10px; font-weight:600; padding:2px 7px;
        border-radius:4px }
.pill-blue   { background:#dbeafe; color:#1d4ed8 }
.pill-green  { background:#d1fae5; color:#047857 }
.pill-orange { background:#fed7aa; color:#c2410c }
.pill-red    { background:#fee2e2; color:#b91c1c }
.pill-gray   { background:var(--border); color:var(--text3) }
.pill-amber  { background:#fef3c7; color:#92400e }

/* ── Hero gradient (was .hero-c — kept for backwards compat) ────── */
.hero-grad, .hero-c {
  padding:18px 20px; color:#fff;
  background:linear-gradient(135deg,#004ac6,#0066ee);
  border-radius:12px; border:none; margin-bottom:18px;
}
.hero-grad .label-caps, .hero-c .label-caps { color:rgba(255,255,255,.78) }
.hero-grad-title { font-size:20px; font-weight:700; line-height:1.2; margin-bottom:4px }
.hero-grad-sub   { font-size:13px; color:rgba(255,255,255,.85) }
.hero-grad-actions, .hero-c .h-actions {
  display:flex; gap:8px; margin-top:14px;
}
.hero-grad-actions button, .hero-grad-actions a,
.hero-c .h-actions button {
  flex:1; border:none; border-radius:8px; padding:11px 10px;
  font-size:13px; font-weight:700; cursor:pointer; font-family:inherit;
  text-align:center; text-decoration:none; display:inline-block;
}
.hero-grad-primary,   .hero-c .h-primary   { background:#fff; color:#004ac6 }
.hero-grad-secondary, .hero-c .h-secondary { background:rgba(255,255,255,.18); color:#fff }

/* ── Tab strip ───────────────────────────────────────────────────── */
.tab-strip { display:flex; gap:4px; border-bottom:1px solid var(--border);
             margin-bottom:14px; overflow-x:auto; scrollbar-width:none }
.tab-strip::-webkit-scrollbar { display:none }
.tab-strip .tab { padding:10px 14px; font-size:13px; font-weight:600;
                  color:var(--text3); cursor:pointer; white-space:nowrap;
                  border-bottom:2px solid transparent; margin-bottom:-1px;
                  background:none; border-top:none; border-left:none; border-right:none;
                  font-family:inherit }
.tab-strip .tab.active { color:#004ac6; border-bottom-color:#004ac6 }
.tab-strip .tab:hover  { color:var(--text) }

/* ── V3 input look ───────────────────────────────────────────────── */
.v3-input { width:100%; background:var(--bg); border:1px solid var(--border);
            color:var(--text); border-radius:8px; padding:10px 12px;
            font-size:14px; font-family:inherit; box-sizing:border-box }
.v3-input:focus { outline:none; border-color:#004ac6;
                  box-shadow:0 0 0 3px rgba(0,74,198,.12) }

/* ── Buttons ─────────────────────────────────────────────────────── */
.btn-primary { background:#004ac6; color:#fff; border:none; border-radius:10px;
               padding:14px; font-size:15px; font-weight:700; cursor:pointer;
               font-family:inherit; width:100%; min-height:48px }
.btn-primary:active { background:#003ba0 }
.btn-secondary { background:var(--card); color:var(--text); border:1px solid var(--border);
                 border-radius:10px; padding:14px; font-size:15px; font-weight:600;
                 cursor:pointer; font-family:inherit; width:100%; min-height:48px }

/* ── Search pill (matches existing map filter bar look) ────────── */
.search-pill { padding:8px 14px; border-radius:20px; font-size:13px; border:none;
               background:var(--card); color:var(--text);
               box-shadow:0 1px 4px rgba(0,0,0,.1); width:100%;
               font-family:inherit; box-sizing:border-box }

/* ── Desktop width cap (lifted from V3 home so every page caps) ── */
@media (min-width: 720px) {
  .mobile-body { max-width:520px; margin-left:auto; margin-right:auto }
}

/* ── Label-caps utility (was inline span in home.py) ────────────── */
.label-caps { font-size:11px; font-weight:700; color:var(--text3);
              letter-spacing:.6px; text-transform:uppercase }

/* ── Page-header brand mark (small Reform logo, left of title) ─── */
.mobile-hdr-brand { display:flex; align-items:center; padding-right:10px;
                    flex-shrink:0 }
.mobile-hdr-brand img { height:18px; width:auto; display:block }

/* ── Expandable stops list inside My Routes cards ───────────────── */
.route-stops-toggle { background:none; border:none; padding:6px 0;
                      margin-top:8px; color:#004ac6; font-size:12px;
                      font-weight:600; cursor:pointer; font-family:inherit;
                      display:inline-flex; align-items:center; gap:4px }
.route-stops-toggle:active { color:#003ba0 }
.route-stops-caret { display:inline-block; line-height:1 }
.route-stops-list { margin-top:6px; border-top:1px solid var(--border);
                    padding-top:8px }
.route-stop-row { display:flex; align-items:center; gap:10px;
                  padding:8px 0; border-bottom:1px solid var(--border);
                  font-size:13px }
.route-stop-row:last-child { border-bottom:none }
.route-stop-num { width:22px; height:22px; border-radius:50%;
                  color:#fff; font-size:11px; font-weight:700;
                  display:flex; align-items:center; justify-content:center;
                  flex-shrink:0 }
.route-stop-name { flex:1; min-width:0; white-space:nowrap;
                   overflow:hidden; text-overflow:ellipsis;
                   color:#004ac6; text-decoration:none; font-weight:500 }
.route-stop-name:active { color:#003ba0 }
.route-stop-name--plain { color:var(--text); cursor:default }
.route-stop-status { font-size:11px; font-weight:600; flex-shrink:0 }
</style>
"""
