// Stats tab — a summary of the sites currently matched by the scope lens
// and filters.
//
// Computed from the features main.js passes on every refresh (the same
// rows the map draws), so it works in every tier: GeoJSON fallback or
// DuckDB-Wasm. The properties it reads — type, country, primary_sphere,
// established, ris, geri_harmonized — are written by both paths
// (scripts/export_parquet.py for the GeoJSON, query() in src/db.js for
// DuckDB); keep them in step. Sites without coordinates (ICOS ocean
// ships) are not map features and are not counted here.

import { TYPE_COLORS, SPHERE_COLORS } from '../map.js';

let _container = null;

const RI_LABELS = {
  neon: 'NEON', elter: 'eLTER', icos: 'ICOS', tern: 'TERN',
  saeon: 'SAEON', efteon: 'EFTEON', cern: 'CERN',
};

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmtInt = (n) => Number(n || 0).toLocaleString();

let _regionNames = null;
try { _regionNames = new Intl.DisplayNames(['en'], { type: 'region' }); } catch { /* old browser */ }
const countryName = (c) => { try { return _regionNames?.of(c) || c; } catch { return c; } };

// LIST columns arrive as Arrow vectors on the DuckDB path and as arrays
// (or, through MapLibre, JSON strings) on the GeoJSON path.
function asList(v) {
  if (v == null) return [];
  if (Array.isArray(v)) return v;
  if (typeof v === 'string') { try { const p = JSON.parse(v); return Array.isArray(p) ? p : []; } catch { return []; } }
  if (typeof v.toArray === 'function') return Array.from(v.toArray());
  return Array.from(v);
}

function countBy(features, keyFn) {
  const m = new Map();
  for (const f of features) {
    for (const k of keyFn(f.properties || {})) {
      if (k == null || k === '') continue;
      m.set(k, (m.get(k) || 0) + 1);
    }
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));
}

function bars(title, rows, labelFn = (k) => k, colorFn = () => null, limit = 12) {
  if (!rows.length) {
    return `<div class="cov-block"><h5>${esc(title)}</h5><p class="no-data">No sites.</p></div>`;
  }
  const max = Math.max(...rows.map((r) => r[1]));
  const items = rows.slice(0, limit).map(([k, n]) => {
    const color = colorFn(k);
    return `<li class="cov-row">
      <span class="cov-label">${esc(labelFn(k))}</span>
      <span class="cov-bar" style="width:${Math.max(2, Math.round(100 * n / max))}%${
        color ? `;background:${color}` : ''}"></span>
      <span class="cov-count">${fmtInt(n)}</span>
    </li>`;
  }).join('');
  const more = rows.length > limit ? `<p class="dash-sub">and ${rows.length - limit} more</p>` : '';
  return `<div class="cov-block"><h5>${esc(title)}</h5><ul class="cov-list">${items}</ul>${more}</div>`;
}

export function initStatsView(container) {
  _container = container;
  _container.innerHTML = `<div class="dash-page"><p class="dash-status" style="padding:24px;color:#64748b">Loading…</p></div>`;
}

export function renderStats(features) {
  if (!_container) return;
  const feats = features || [];
  const ris = (p) => asList(p.ris);
  const nMulti = feats.filter((f) => ris(f.properties || {}).length > 1).length;
  const nHarm = feats.filter((f) => (f.properties || {}).geri_harmonized === true
                                 || (f.properties || {}).geri_harmonized === 'true').length;
  const nLong = feats.filter((f) => {
    const v = (f.properties || {}).long_term_threshold_met;
    return v === true || v === 'true';
  }).length;
  const decade = (p) => (p.established ? [`${Math.floor(Number(p.established) / 10) * 10}s`] : []);
  const byDecade = countBy(feats, decade).sort((a, b) => a[0].localeCompare(b[0]));

  _container.innerHTML = `
    <div class="dash-page">
      <header class="dash-header">
        <h1>GERI sites — summary</h1>
        <p class="dash-sub">
          ${fmtInt(feats.length)} mapped sites match the current scope and filters ·
          ${fmtInt(nMulti)} belong to two or more research infrastructures ·
          ${fmtInt(nHarm)} are covered by the GERI harmonized products ·
          ${fmtInt(nLong)} have at least 10 years of record (from the year established).
        </p>
      </header>
      <div class="area-grid">
        <div class="dash-card">
          <h4>Research infrastructure</h4>
          <p class="dash-sub">A site in two RIs counts in both.</p>
          ${bars('Sites per RI', countBy(feats, ris), (k) => RI_LABELS[k] || k)}
        </div>
        <div class="dash-card">
          <h4>Facility type</h4>
          ${bars('Sites per type', countBy(feats, (p) => [p.type]),
                 (k) => String(k).replace(/-/g, ' '), (k) => TYPE_COLORS[k])}
        </div>
        <div class="dash-card">
          <h4>Primary sphere</h4>
          ${bars('Sites per sphere', countBy(feats, (p) => [p.primary_sphere]),
                 (k) => k, (k) => SPHERE_COLORS[k])}
        </div>
        <div class="dash-card">
          <h4>Country</h4>
          <p class="dash-sub">Where the site is (ISO 3166-1).</p>
          ${bars('Sites per country', countBy(feats, (p) => [p.country]), countryName, () => null, 15)}
        </div>
        <div class="dash-card dash-card-coverage">
          <h4>Year established</h4>
          <p class="dash-sub">From DEIMS-SDR; sites with no year are not shown.</p>
          ${bars('Sites per decade', byDecade, (k) => k, () => null, 40)}
        </div>
      </div>
    </div>`;
}
