// sql.js — DuckDB SQL console
//
// Runs ad-hoc SQL against the parquet views registered in src/db.js
// (facilities, facility_types, networks, research_areas, regions,
// funders, area_links, network_membership, facility_regions,
// funding_links, region_area_links). Includes a handful of curated
// queries the user can click to preview interesting slices of the
// lto schema.

import { getConn, whenReady, unwrapRow, ensureSqlTables } from '../db.js';

// ── Canned queries ──────────────────────────────────────────────────
//
// Keep these intentionally short (single SELECT, no VIEWs, no CTEs
// longer than a screen) so users can read them as teaching material
// before hitting Run. Each has a title that the UI renders as a
// button label and a description that shows under the editor while
// the query is active.
const EXAMPLES = [
  {
    id: 'sites-per-ri',
    title: 'Sites per research infrastructure',
    description:
      'How many sites each GERI research infrastructure has, by facility type. ' +
      'A site in two RIs is counted in both.',
    sql: `-- Sites per GERI research infrastructure
SELECT n.label                       AS ri,
       f.facility_type               AS type,
       count(*)                      AS sites
FROM   network_membership nm
JOIN   networks   n ON n.network_id  = nm.network_id
JOIN   facilities f ON f.facility_id = nm.facility_id
WHERE  n.level = 'continental-ri'
GROUP  BY n.label, f.facility_type
ORDER  BY ri, sites DESC;`,
  },
  {
    id: 'multi-ri',
    title: 'Sites shared by two or more RIs',
    description:
      'Sites whose registry record names more than one GERI research ' +
      'infrastructure, e.g. an eLTER site that is also an ICOS station.',
    sql: `-- Sites in more than one RI
SELECT canonical_name, country, ris, identifiers
FROM   v_facility_geri
WHERE  len(ris) > 1
ORDER  BY len(ris) DESC, canonical_name;`,
  },
  {
    id: 'find-by-id',
    title: 'Find a site by any identifier',
    description:
      'site_identifiers holds every id a site carries (DEIMS id, NEON site ' +
      'code, ICOS station, GERI harmonized id). Change the value to look one up.',
    sql: `-- Look a site up by any of its ids
SELECT f.canonical_name, f.country, si.scheme, si.value, si.source_url
FROM   site_identifiers si
JOIN   facilities f ON f.facility_id = si.facility_id
WHERE  si.facility_id IN (SELECT facility_id FROM site_identifiers
                          WHERE value ILIKE '%Hyy%')
ORDER  BY f.canonical_name, si.scheme;`,
  },
  {
    id: 'icos-classes',
    title: 'ICOS stations by kind',
    description:
      'ICOS ecosystem, atmosphere and ocean stations, and how many of each ' +
      'also have a DEIMS-SDR record.',
    sql: `-- ICOS stations by kind
SELECT n.label                                         AS kind,
       count(*)                                        AS stations,
       count(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM site_identifiers d
         WHERE d.facility_id = nm.facility_id AND d.scheme = 'deims-id')) AS with_deims
FROM   network_membership nm
JOIN   networks n ON n.network_id = nm.network_id
WHERE  n.parent_id = 'icos'
GROUP  BY n.label
ORDER  BY stations DESC;`,
  },
  {
    id: 'type-counts',
    title: 'Facilities by type',
    description: 'Count of facilities per facility_type slug.',
    sql: `-- Facilities by type
SELECT facility_type, count(*) AS n
FROM   facilities
GROUP  BY facility_type
ORDER  BY n DESC;`,
  },
  {
    id: 'country-counts',
    title: 'Facilities by country',
    description: 'Count of facilities per ISO 3166-1 alpha-2 country (where the site is).',
    sql: `-- Facilities by country
SELECT country, count(*) AS n
FROM   facilities
GROUP  BY country
ORDER  BY n DESC;`,
  },
  {
    id: 'long-record',
    title: 'Longest-running sites',
    description:
      'Sites by year established (from DEIMS-SDR), with their research infrastructures.',
    sql: `-- Longest-running sites
SELECT f.canonical_name, f.country, f.established, g.ris
FROM   facilities f
JOIN   v_facility_geri g ON g.facility_id = f.facility_id
WHERE  f.established IS NOT NULL
ORDER  BY f.established
LIMIT  50;`,
  },
];

// ── State ───────────────────────────────────────────────────────────
let _container = null;
let _activeId = EXAMPLES[0].id;

function escHtml(s) {
  return String(s ?? '').replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

// Convert a DuckDB-Wasm Arrow RecordBatch-backed Table to a simple
// array of plain JS objects. Delegates to unwrapRow (db.js) which
// handles BigInts, Arrow Vectors (LIST<STRUCT>), and nested structs.
// DATE and TIMESTAMP columns arrive from DuckDB-Wasm as epoch
// milliseconds (plain numbers, never Date objects), so they are
// formatted here from the Arrow schema: a DATE as YYYY-MM-DD, a
// TIMESTAMP as YYYY-MM-DD HH:MM:SS (UTC when the column has a zone).
const ARROW_DATE = 8;        // apache-arrow Type.Date
const ARROW_TIMESTAMP = 10;  // apache-arrow Type.Timestamp
function fmtTemporal(v, type) {
  const n = typeof v === 'bigint' ? Number(v) : v;
  if (typeof n !== 'number' || !Number.isFinite(n)) return v;
  const d = new Date(n);
  if (Number.isNaN(d.getTime())) return v;
  const iso = d.toISOString();
  if (type.typeId === ARROW_DATE) return iso.slice(0, 10);
  const t = iso.slice(0, 19).replace('T', ' ') + (iso.slice(19, 23) === '.000' ? '' : iso.slice(19, 23));
  return type.timezone ? `${t} UTC` : t;
}
function resultToRows(result) {
  const temporal = (result.schema?.fields || [])
    .filter((f) => f.type && (f.type.typeId === ARROW_DATE || f.type.typeId === ARROW_TIMESTAMP))
    .map((f) => [f.name, f.type]);
  return result.toArray().map((row) => {
    const o = unwrapRow(row.toJSON());
    for (const [k, type] of temporal) {
      if (o[k] != null) o[k] = fmtTemporal(o[k], type);
    }
    for (const k of Object.keys(o)) {
      if (o[k] instanceof Date) o[k] = o[k].toISOString();
    }
    return o;
  });
}

function renderTable(rows) {
  if (!rows.length) return '<p class="sql-empty">Query returned 0 rows.</p>';
  const cols = Object.keys(rows[0]);
  const head = cols.map((c) => `<th>${escHtml(c)}</th>`).join('');
  const body = rows.slice(0, 500).map((r) =>
    `<tr>${cols.map((c) => {
      const v = r[c];
      // NULL is shown as such, so it can be told apart from an empty string.
      if (v == null) return '<td class="sql-null">NULL</td>';
      const display = typeof v === 'object' ? JSON.stringify(v) : String(v);
      const num = typeof v === 'number' ? ' class="num"' : '';
      return `<td${num}>${escHtml(display)}</td>`;
    }).join('')}</tr>`,
  ).join('');
  const truncated = rows.length > 500
    ? `<p class="sql-trunc">Showing the first 500 of ${rows.length.toLocaleString()} rows.</p>`
    : '';
  return `<table class="sql-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${truncated}`;
}

// ── Run ─────────────────────────────────────────────────────────────
async function run(sql) {
  const statusEl = _container.querySelector('#sql-status');
  const resultsEl = _container.querySelector('#sql-results');
  statusEl.textContent = 'Running…';
  resultsEl.innerHTML = '';
  const t0 = performance.now();
  try {
    await whenReady();
    const conn = getConn();
    if (!conn) throw new Error('DuckDB connection not ready');
    // The console is the only surface allowed to read the lazy tables and
    // helper views, so it is the one place that registers them. Memoised —
    // every run after the first awaits an already-resolved promise.
    await ensureSqlTables();
    const result = await conn.query(sql);
    const rows = resultToRows(result);
    const ms = (performance.now() - t0).toFixed(0);
    statusEl.innerHTML = `<strong>${rows.length.toLocaleString()}</strong> row${rows.length === 1 ? '' : 's'} · ${ms} ms`;
    resultsEl.innerHTML = renderTable(rows);
  } catch (err) {
    const ms = (performance.now() - t0).toFixed(0);
    statusEl.innerHTML = `<span class="sql-err">Error after ${ms} ms</span>`;
    resultsEl.innerHTML = `<pre class="sql-error">${escHtml(err.message || String(err))}</pre>`;
    console.error('[sql]', err);
  }
}

// ── Init ────────────────────────────────────────────────────────────
function pickExample(id) {
  const ex = EXAMPLES.find((e) => e.id === id) || EXAMPLES[0];
  _activeId = ex.id;
  const editor = _container.querySelector('#sql-editor');
  const desc = _container.querySelector('#sql-description');
  editor.value = ex.sql;
  desc.textContent = ex.description;
  _container.querySelectorAll('.sql-example').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.id === ex.id);
  });
}

export function initSqlView(container) {
  _container = container;

  const exampleBtns = EXAMPLES.map((ex) => `
    <button type="button" class="sql-example" data-id="${ex.id}">${escHtml(ex.title)}</button>
  `).join('');

  _container.innerHTML = `
    <div class="sql-view">
      <header class="sql-header">
        <div>
          <h2>DuckDB SQL console</h2>
          <p class="sql-sub">Queries run client-side in WebAssembly against the parquet
          views in <code>public/parquet/</code>. No server round-trip; the whole dataset
          lives in your browser. Pick an example to get started, or edit and run your own.</p>
        </div>
      </header>
      <div class="sql-layout">
        <aside class="sql-examples">
          <div class="sql-examples-title">Example queries</div>
          ${exampleBtns}
          <div class="sql-schema-title">Tables in scope</div>
          <ul class="sql-schema">
            <li>facilities · facility_types · locations</li>
            <li>networks · network_membership</li>
            <li>site_identifiers · harmonized_coverage</li>
            <li>spheres · facility_spheres</li>
            <li>data_archives · facility_archives · data_products</li>
            <li>api_endpoints · cloud_buckets</li>
            <li>archive_types · data_formats · data_licenses · access_modes</li>
            <li>provenance</li>
            <li class="sql-schema-views">v_facility_geri · v_facility_enriched · v_facility_map</li>
          </ul>
        </aside>
        <section class="sql-main">
          <p id="sql-description" class="sql-description"></p>
          <textarea id="sql-editor" class="sql-editor" spellcheck="false"></textarea>
          <div class="sql-actions">
            <button id="sql-run" type="button" class="btn-primary">Run query</button>
            <span id="sql-status" class="sql-status">Ready.</span>
          </div>
          <div id="sql-results" class="sql-results"></div>
        </section>
      </div>
    </div>`;

  _container.querySelectorAll('.sql-example').forEach((btn) => {
    btn.addEventListener('click', () => pickExample(btn.dataset.id));
  });

  _container.querySelector('#sql-run').addEventListener('click', () => {
    const sql = _container.querySelector('#sql-editor').value.trim();
    if (!sql) return;
    run(sql);
  });

  // Keyboard shortcut: Cmd/Ctrl+Enter runs the query.
  _container.querySelector('#sql-editor').addEventListener('keydown', (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key === 'Enter') {
      ev.preventDefault();
      const sql = ev.target.value.trim();
      if (sql) run(sql);
    }
  });

  pickExample(_activeId);
}

// Called on route activation. Lazy-runs the active example the very
// first time the tab is visited so the user sees a real result right
// away; subsequent visits just re-show the existing editor + results.
let _firstRunDone = false;
export function renderSqlView() {
  if (!_container) return;
  if (_firstRunDone) return;
  _firstRunDone = true;
  const sql = _container.querySelector('#sql-editor').value.trim();
  if (sql) run(sql);
}
