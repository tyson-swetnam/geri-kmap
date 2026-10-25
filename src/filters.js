import { fetchCSV } from './csv.js';
import { DATA_BASE as BASE } from './config.js';

// Country checklist labels. The codes come from the data (every
// facilities.country present in public/facilities.geojson), so the list
// grows with the catalogue; Intl.DisplayNames turns ISO alpha-2 into a name.
const REGION_NAMES = (() => {
  try { return new Intl.DisplayNames(['en'], { type: 'region' }); } catch { return null; }
})();
const countryName = (code) => {
  try { return REGION_NAMES?.of(code) || code; } catch { return code; }
};

// ── Scope lens ───────────────────────────────────────────────────────
//
// One lens per GERI research infrastructure, plus the sites the GERI
// harmonization pipeline covers. The lens is a single-choice facet that
// narrows every facility query; "All GERI" removes it. Nothing is deleted
// from the data to make the narrower views.
//
// Each lens is defined twice, and the two must agree: `sql` for the
// DuckDB path and `test` for the GeoJSON-fallback path (which sees only
// the properties scripts/export_parquet.py writes: ris, geri_harmonized).
export const DEFAULT_SCOPE = 'all';
const riScope = (slug, label, hint) => ({
  label, hint,
  sql: `f.facility_id IN (SELECT nm.facility_id FROM network_membership nm
                          WHERE nm.network_id = '${slug}')`,
  test: (p) => (Array.isArray(p.ris) ? p.ris : []).includes(slug),
});
export const SCOPES = {
  all: {
    label: 'All GERI',
    hint: 'Every site of the six GERI research infrastructures',
    sql: null,
    test: () => true,
  },
  harmonized: {
    label: 'Harmonized sites',
    hint: 'Sites covered by the GERI harmonized drought products',
    sql: `f.facility_id IN (SELECT si.facility_id FROM site_identifiers si
                            WHERE si.scheme = 'geri-harmonized-id')`,
    test: (p) => !!p.geri_harmonized,
  },
  neon: riScope('neon', 'NEON', 'National Ecological Observatory Network (USA)'),
  elter: riScope('elter', 'eLTER', 'European Long-Term Ecosystem Research'),
  icos: riScope('icos', 'ICOS', 'Integrated Carbon Observation System (Europe)'),
  tern: riScope('tern', 'TERN', 'Terrestrial Ecosystem Research Network (Australia)'),
  saeon: riScope('saeon', 'SAEON', 'South African Environmental Observation Network'),
  cern: riScope('cern', 'CERN', 'Chinese Ecosystem Research Network'),
};

/** Build a collapsible facet section element. */
function makeFacetSection(id, title, bodyHtml, collapsed = false) {
  const sec = document.createElement('div');
  sec.className = 'facet-section' + (collapsed ? ' collapsed' : '');
  sec.id = id;
  sec.innerHTML = `
    <div class="facet-header">
      <h2>${title}</h2>
      <span class="facet-toggle">${collapsed ? '&#9660;' : '&#9650;'}</span>
    </div>
    <div class="facet-body">${bodyHtml}</div>
  `;
  sec.querySelector('.facet-header').addEventListener('click', () => {
    sec.classList.toggle('collapsed');
    sec.querySelector('.facet-toggle').innerHTML =
      sec.classList.contains('collapsed') ? '&#9660;' : '&#9650;';
  });
  return sec;
}

function checkbox(facet, value, label) {
  const safeVal = String(value).replace(/"/g, '&quot;');
  const safeLabel = String(label ?? value).replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  return `<label><input type="checkbox" data-facet="${facet}" data-value="${safeVal}" /> ${safeLabel}</label>`;
}

export async function initFilters(container, state) {
  // "Clear all" link (only clears facility-filter checkboxes, not overlays)
  const clearLink = document.createElement('a');
  clearLink.id = 'clear-all';
  clearLink.textContent = 'Clear all filters';
  clearLink.href = '#';
  clearLink.addEventListener('click', (e) => {
    e.preventDefault();
    container.querySelectorAll('input[type=checkbox]').forEach((cb) => { cb.checked = false; });
    // Numeric / boolean LTO filters reset back to their defaults too.
    const ltMet = container.querySelector('#f-long-term-only');
    if (ltMet) ltMet.checked = false;
    const eMin = container.querySelector('#f-established-min');
    const eMax = container.querySelector('#f-established-max');
    if (eMin) eMin.value = '';
    if (eMax) eMax.value = '';
    state.setFilters({
      types: new Set(), countries: new Set(),
      areas: new Set(), networks: new Set(),
      spheres: new Set(), ecosystems: new Set(), lifeZones: new Set(),
      longTermOnly: false,
      establishedMin: null, establishedMax: null,
    });
  });
  container.appendChild(clearLink);

  // 0. Scope lens — single choice, always open, never cleared by
  // "Clear all filters" (it is a lens over the catalogue, not a filter
  // someone forgot they set).
  const scopeSection = makeFacetSection(
    'f-scope', 'Scope',
    Object.entries(SCOPES).map(([key, s]) =>
      `<label title="${s.hint}"><input type="radio" name="f-scope" value="${key}"${
        key === (state.filters.scope || DEFAULT_SCOPE) ? ' checked' : ''} /> ${s.label}</label>`
    ).join(''),
    false,
  );
  container.appendChild(scopeSection);
  scopeSection.addEventListener('change', (ev) => {
    if (ev.target?.name === 'f-scope') state.setFilters({ scope: ev.target.value });
  });

  // ── Filter sidebar ordering ──
  //
  // For an LTO catalog the most useful discovery facets are:
  //   1. ≥10-year-record toggle (Peters et al. 2013 inclusion gate)
  //   2. Primary sphere (atmosphere / cryosphere / terrestrial / agriculture
  //      / ocean-estuarine / freshwater)
  //   3. Network (LTER, NEON, USFS-EFR, LTAR, IOOS RAs, NERRS, AmeriFlux …)
  //   — those three answer "show me LTERs in the cryosphere with ≥30 yr"
  //
  // Everything else (research area, ecosystem, life zone, country, type,
  // established year range) is secondary and starts collapsed.
  //
  // Each LTO-specific facet is rendered with a stub body up front so the
  // section is visible even if its CSV fetch is slow / fails; the async
  // block at the bottom replaces stubBody with real labels.

  // 1. Long-term threshold — primary inclusion gate.
  const thresholdSection = makeFacetSection(
    'f-threshold', 'Long-term threshold',
    `<label><input type="checkbox" id="f-long-term-only" />
       Show only facilities with &ge;10y record</label>`,
    true,  // expanded by default
  );
  container.appendChild(thresholdSection);

  // 2. Primary sphere.
  // Titled "Sphere", not "Primary sphere": the WHERE clause deliberately
  // matches ANY facility_spheres role, so selecting Arid also surfaces
  // the LTAR/ARS rangeland sites that carry arid as a secondary sphere
  // (user-directed behavior — agriculture keeps their primary).
  const sphereSection = makeFacetSection(
    'f-sphere', 'Sphere', '<div class="facet-loading">Loading…</div>', true,
  );
  container.appendChild(sphereSection);

  // 3. Network — loaded async into this placeholder. The previous code
  // inserted the network section *before* type after the CSV fetch; now
  // we reserve its slot up-front so the layout doesn't reflow.
  const networkSection = makeFacetSection(
    'f-network', 'Network', '<div class="facet-loading">Loading…</div>', true,
  );
  container.appendChild(networkSection);

  // 4. Facility type — filled from schema/vocab/facility_types.csv below.
  const typeSlugs = [];
  const typeSection = makeFacetSection(
    'f-type', 'Facility type',
    typeSlugs.map((s) => checkbox('type', s, s)).join(''),
    false,  // collapsed
  );
  container.appendChild(typeSection);

  // 5. Established year range (numeric inputs, populated below).
  // Section appended later via the dedicated established block so the
  // markup stays in one place. Placeholder kept here only for ordering.

  // 9. Country / territory — the codes present in the data, by name.
  const countrySection = makeFacetSection(
    'f-country', 'Country / territory', '<div class="facet-loading">Loading…</div>', false,
  );
  container.appendChild(countrySection);
  fetch(`${BASE}facilities.geojson`).then((r) => r.json()).then((gj) => {
    const codes = [...new Set(gj.features.map((f) => f.properties.country).filter(Boolean))];
    codes.sort((a, b) => countryName(a).localeCompare(countryName(b)));
    countrySection.querySelector('.facet-body').innerHTML =
      codes.map((c) => checkbox('country', c, countryName(c))).join('');
  }).catch((e) => console.warn('Could not list countries:', e));

  // ── Established year range ──
  //
  // Two numeric inputs filtering on facilities.established (an INTEGER
  // year). Empty input = no bound. Validated lightly (we just coerce
  // to a Number; non-numeric input clears that bound).
  const yearSection = makeFacetSection(
    'f-established', 'Established year',
    `<div class="year-range">
       <label>Min <input type="number" id="f-established-min" min="1700" max="2100" step="1" placeholder="e.g. 1980" /></label>
       <label>Max <input type="number" id="f-established-max" min="1700" max="2100" step="1" placeholder="e.g. 2025" /></label>
     </div>`,
    true,
  );
  container.appendChild(yearSection);

  // Wire numeric / boolean LTO inputs separately from the unified
  // checkbox handler at the bottom of this function — they aren't
  // checkboxes (the threshold one *is* but it has its own state key)
  // and the change handler matches by data-facet attribute.
  thresholdSection.querySelector('#f-long-term-only').addEventListener('change', (ev) => {
    state.setFilters({ longTermOnly: !!ev.target.checked });
  });
  const onYearChange = () => {
    const minEl = yearSection.querySelector('#f-established-min');
    const maxEl = yearSection.querySelector('#f-established-max');
    const min = minEl.value === '' ? null : Number(minEl.value);
    const max = maxEl.value === '' ? null : Number(maxEl.value);
    state.setFilters({
      establishedMin: Number.isFinite(min) ? min : null,
      establishedMax: Number.isFinite(max) ? max : null,
    });
  };
  yearSection.querySelector('#f-established-min').addEventListener('change', onYearChange);
  yearSection.querySelector('#f-established-max').addEventListener('change', onYearChange);

  // Async: load vocab CSVs, then insert research-area + network sections before type
  (async () => {
    try {
      const [networkRows, typeRows] = await Promise.all([
        fetchCSV(`${BASE}vocab/networks.csv`),
        fetchCSV(`${BASE}vocab/facility_types.csv`),
      ]);

      // LTO vocab — sphere / ecosystem / life-zone CSVs. Loaded with
      // Promise.allSettled so a missing CSV (e.g. on a deploy that
      // hasn't synced public/vocab/ yet) leaves its filter section
      // empty rather than wiping out the whole sidebar.
      Promise.allSettled([
        fetchCSV(`${BASE}vocab/spheres.csv`),
      ]).then(([sphRes]) => {
        const fillFacet = (section, facetKey, rows, emptyMsg) => {
          const body = section.querySelector('.facet-body');
          if (!body) return;
          if (!Array.isArray(rows) || rows.length === 0) {
            body.innerHTML = `<div class="facet-empty">${emptyMsg}</div>`;
            return;
          }
          body.innerHTML = rows
            .map((r) => checkbox(facetKey, r.slug, r.label || r.slug))
            .join('');
        };
        fillFacet(
          sphereSection, 'sphere',
          sphRes.status === 'fulfilled' ? sphRes.value : null,
          'Spheres vocab unavailable.'
        );
      });

      // Update type labels now that we have the CSV. Filter the rows
      // against the in-use set above so "reserved" vocab entries
      // (industry / local-gov / university-institute / vessel / virtual)
      // stay in the schema but don't appear as dead-end checkboxes.
      const typeBody = typeSection.querySelector('.facet-body');
      typeBody.innerHTML = typeRows
        .map((r) => checkbox('type', r.slug, r.label))
        .join('');

      // Fill the pre-allocated Network section. Show "ACRONYM — Full Name"
      // so users can both pattern-match on the acronym they know
      // (IOOS, NERRS, LTER…) and read the full organisation name. The
      // schema stores the short form in `label` and the expanded form(s)
      // in `aliases` (pipe-separated). Fall back to label alone if the
      // alias is missing or identical to the label.
      const netLabel = (r) => {
        const label = (r.label || '').trim();
        const alias = String(r.aliases || '').split('|')[0].trim();
        if (!alias || alias.toLowerCase() === label.toLowerCase()) return label;
        return `${label} — ${alias}`;
      };
      const netBody = networkSection.querySelector('.facet-body');
      if (netBody) {
        netBody.innerHTML = networkRows
          .map((r) => checkbox('network', r.slug, netLabel(r)))
          .join('');
      }

    } catch (e) {
      console.warn('Could not load vocab CSVs for filters:', e);
    }
  })();

  // Unified change handler
  container.addEventListener('change', (ev) => {
    const input = ev.target;
    if (!(input instanceof HTMLInputElement)) return;
    const { facet, value } = input.dataset;
    if (!facet) return;

    const keyMap = {
      type: 'types', country: 'countries', area: 'areas', network: 'networks',
      // LTO six-sphere model facets.
      sphere: 'spheres', ecosystem: 'ecosystems', 'life-zone': 'lifeZones',
    };
    const key = keyMap[facet];
    if (!key) return;
    const set = new Set(state.filters[key]);
    if (input.checked) set.add(value);
    else set.delete(value);
    state.setFilters({ [key]: set });
  });
}

export function applyFilters(filterState) {
  const clauses = [];
  const params = [];

  const scope = SCOPES[filterState.scope];
  if (scope?.sql) clauses.push(scope.sql);

  if (filterState.types?.size) {
    clauses.push(`f.facility_type IN (${Array.from(filterState.types).map(() => '?').join(',')})`);
    params.push(...filterState.types);
  }
  if (filterState.countries?.size) {
    clauses.push(`f.country IN (${Array.from(filterState.countries).map(() => '?').join(',')})`);
    params.push(...filterState.countries);
  }
  if (filterState.areas?.size) {
    const slugs = Array.from(filterState.areas);
    clauses.push(
      `f.facility_id IN (SELECT al.facility_id FROM area_links al ` +
      `WHERE al.area_id IN (${slugs.map(() => '?').join(',')}))`
    );
    params.push(...slugs);
  }
  if (filterState.networks?.size) {
    const slugs = Array.from(filterState.networks);
    clauses.push(
      `f.facility_id IN (SELECT nm.facility_id FROM network_membership nm ` +
      `WHERE nm.network_id IN (${slugs.map(() => '?').join(',')}))`
    );
    params.push(...slugs);
  }
  // LTO six-sphere facets. Each is a slug-IN subquery against the new
  // crosswalk tables (facility_spheres, facility_ecosystems,
  // facility_life_zones). Wrapped so an empty Set → no clause emitted.
  if (filterState.spheres?.size) {
    const slugs = Array.from(filterState.spheres);
    clauses.push(
      `f.facility_id IN (SELECT fs.facility_id FROM facility_spheres fs ` +
      `WHERE fs.sphere_slug IN (${slugs.map(() => '?').join(',')}))`
    );
    params.push(...slugs);
  }
  if (filterState.ecosystems?.size) {
    const slugs = Array.from(filterState.ecosystems);
    clauses.push(
      `f.facility_id IN (SELECT fe.facility_id FROM facility_ecosystems fe ` +
      `WHERE fe.ecosystem_slug IN (${slugs.map(() => '?').join(',')}))`
    );
    params.push(...slugs);
  }
  if (filterState.lifeZones?.size) {
    const slugs = Array.from(filterState.lifeZones);
    clauses.push(
      `f.facility_id IN (SELECT fl.facility_id FROM facility_life_zones fl ` +
      `WHERE fl.life_zone_slug IN (${slugs.map(() => '?').join(',')}))`
    );
    params.push(...slugs);
  }
  // Long-term threshold (Peters et al. 2013): the boolean column is
  // precomputed in facilities.parquet by the ingest pipeline.
  if (filterState.longTermOnly) {
    clauses.push(`f.long_term_threshold_met = TRUE`);
  }
  // Established-year bounds. Use IS NOT NULL + bound so that a facility
  // with NULL `established` doesn't get accidentally swept in by a
  // permissive bound (DuckDB returns NULL for `f.established >= ?`
  // when established is NULL, which evaluates to false in WHERE — but
  // we add the explicit IS NOT NULL for symmetry with the threshold
  // clause and to make the intent obvious.
  if (Number.isFinite(filterState.establishedMin)) {
    clauses.push(`f.established IS NOT NULL AND f.established >= ?`);
    params.push(filterState.establishedMin);
  }
  if (Number.isFinite(filterState.establishedMax)) {
    clauses.push(`f.established IS NOT NULL AND f.established <= ?`);
    params.push(filterState.establishedMax);
  }
  if (filterState.q) {
    clauses.push(`(lower(f.canonical_name) LIKE ? OR lower(f.acronym) LIKE ?)`);
    const q = `%${filterState.q.toLowerCase()}%`;
    params.push(q, q);
  }

  return {
    where: clauses.length ? `WHERE ${clauses.join(' AND ')}` : '',
    params,
  };
}
