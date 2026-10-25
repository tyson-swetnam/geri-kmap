import maplibregl from 'maplibre-gl';
import { fetchCSV } from './csv.js';
import { DATA_BASE as BASE } from './config.js';
import { cardById, schemeLabel, splitIdentifiers, idText, idHref, variableLabel, yearSpan } from './cards.js';

// LTO six-sphere palette, used when the user picks "Color by primary
// sphere" in the legend. Slugs match schema/vocab/spheres.csv. Colours
// were chosen to be intuitive (sky blue for atmosphere, ice blue for
// cryosphere, forest green for terrestrial, …) and to remain readable
// against the Positron base map. Default fallback (#64748b slate) is
// used for any facility row whose primary_sphere is null/missing.
export const SPHERE_COLORS = {
  'atmosphere':       '#5DADE2', // sky blue
  'cryosphere':       '#AED6F1', // ice blue
  'terrestrial':      '#52BE80', // forest green
  'arid':             '#CA8A5B', // desert sand/terracotta
  'agriculture':      '#F4D03F', // wheat yellow
  'ocean-estuarine':  '#1F618D', // deep ocean blue
  'freshwater':       '#48C9B0', // freshwater teal
};

// GERI facility types (schema/vocab/facility_types.csv). Most types belong
// to one research infrastructure, so colouring by type also reads as
// colouring by RI: NEON greens, ICOS blues, TERN ochre, CERN red, eLTER
// purple.
export const TYPE_COLORS = {
  'neon-terrestrial-site':   '#15803d',
  'neon-aquatic-site':       '#0d9488',
  'icos-ecosystem-station':  '#2563eb',
  'icos-atmosphere-station': '#60a5fa',
  'icos-ocean-station':      '#1e3a8a',
  'supersite':               '#b45309',
  'plot-network':            '#d97706',
  'flux-tower':              '#ca8a04',
  'field-station':           '#dc2626',
  'lter-site':               '#7c3aed',
  'ltser-platform':          '#c026d3',
  'marine-site':             '#0369a1',
  'ri-site':                 '#64748b',
};

function typeColorExpr() {
  const expr = ['match', ['get', 'type']];
  for (const [k, v] of Object.entries(TYPE_COLORS)) expr.push(k, v);
  expr.push('#64748b');
  return expr;
}

// Match against feature.properties.primary_sphere. Falls through to
// slate (#64748b) for facilities whose primary_sphere is null — until
// Wave B research populates facility_spheres for every facility, that
// will include most rows.
function sphereColorExpr() {
  const expr = ['match', ['get', 'primary_sphere']];
  for (const [k, v] of Object.entries(SPHERE_COLORS)) expr.push(k, v);
  expr.push('#64748b');
  return expr;
}

// Active marker color encoding. 'sphere' (default) paints by
// primary_sphere; 'type' paints by facility_type (legacy behavior).
// Persisted to localStorage so the user's choice survives reloads.
let _colorMode = (() => {
  try {
    const v = localStorage.getItem('geri-kmap:colorMode');
    return v === 'type' ? 'type' : 'sphere';
  } catch (_) { return 'sphere'; }
})();

function colorExprFor(mode) {
  return mode === 'type' ? typeColorExpr() : sphereColorExpr();
}

export function getColorMode() { return _colorMode; }
export function setColorMode(mode) {
  const next = mode === 'type' ? 'type' : 'sphere';
  if (next === _colorMode) return;
  _colorMode = next;
  try { localStorage.setItem('geri-kmap:colorMode', next); } catch (_) { /* ignore */ }
  // Repaint the live map (skip in stub mode where setPaintProperty is a no-op).
  if (map && !_stubMode) {
    try { map.setPaintProperty('facility-points', 'circle-color', colorExprFor(next)); }
    catch (_) { /* layer not added yet */ }
  }
  refreshLegend();
}

let map;
let _stubMode = false;
let _currentFeatures = [];

// Plug-in API used by overlays.js to publish what's currently rendered.
let _legendOverlayProvider = () => [];
export function registerLegendOverlayProvider(fn) {
  _legendOverlayProvider = fn || (() => []);
}
export function refreshLegend() {
  document.querySelector('.legend-control')?.dispatchEvent(new CustomEvent('legend:refresh'));
}

// True when the host has no usable WebGL context (e.g. a headless Linux box
// with llvmpipe software rendering, where MapLibre's `_setupPainter` throws).
// overlays.js and main.js use this to skip operations that would NPE on the
// stub map.
export function isMapAvailable() {
  return !_stubMode;
}

// Probe WebGL synchronously. MapLibre's constructor throws inside
// `_setupPainter` if the browser can't create a WebGL context, which kills
// the whole main.js module and breaks every other tab. Detect it ourselves
// first so we can render a graceful fallback and keep Browse / People / SQL /
// Stats / Network / Docs working.
function detectWebGL() {
  try {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl2')
      || c.getContext('webgl')
      || c.getContext('experimental-webgl');
    return !!gl;
  } catch (_) {
    return false;
  }
}

function renderNoWebGLFallback(container) {
  container.classList.add('map-no-webgl');
  container.innerHTML = `
    <div class="map-no-webgl-inner">
      <h2>Interactive map unavailable</h2>
      <p>The map view needs WebGL, but your browser couldn't create a WebGL
        context. This usually means hardware acceleration is disabled or the
        device has no GPU (e.g. a headless Linux session falling back to
        software rendering).</p>
      <p><strong>What works without WebGL:</strong> the
        <a href="#/browse">Browse</a>, <a href="#/network">Network</a>,
        <a href="#/people">People</a>, <a href="#/sql">SQL</a>,
        <a href="#/stats">Stats</a>, and <a href="#/docs">Docs</a> tabs above.</p>
      <p><strong>To get the map back:</strong> enable hardware acceleration in
        your browser settings, or in Chromium-based browsers visit
        <code>chrome://flags</code> and enable
        <em>"Override software rendering list"</em>.</p>
    </div>
  `;
}

// Lightweight stand-in for a maplibregl.Map. Implements only the surface that
// main.js, overlays.js, and this module poke at — every method is a no-op
// (or returns a sensible empty value) so callers don't have to special-case
// the missing map.
function makeStubMap() {
  const noop = () => {};
  const stub = {
    on: noop, off: noop, once: noop, fire: noop,
    addControl: noop, removeControl: noop,
    addSource: noop, removeSource: noop,
    addLayer: noop, removeLayer: noop, moveLayer: noop,
    setFilter: noop, setLayoutProperty: noop, setPaintProperty: noop,
    setData: noop,
    getSource: () => null,
    getLayer: () => null,
    getCanvas: () => ({ style: {} }),
    getBounds: () => ({ contains: () => true }),
    isStyleLoaded: () => false,
    resize: noop,
    flyTo: noop, fitBounds: noop, panTo: noop, jumpTo: noop,
    queryRenderedFeatures: () => [],
  };
  return stub;
}

// The whole GERI footprint: North America to Australia, South Africa to
// the Arctic stations.
const HOME_BOUNDS = [[-160, -48], [160, 72]];

const COASTLINE_URL =
  'https://raw.githubusercontent.com/martynafford/natural-earth-geojson/master/50m/physical/ne_50m_coastline.json';

export function initMap(container) {
  if (!detectWebGL()) {
    _stubMode = true;
    renderNoWebGLFallback(container);
    map = makeStubMap();
    return map;
  }

  map = new maplibregl.Map({
    container,
    style: 'https://tiles.openfreemap.org/styles/positron',
    // Opens on the whole GERI footprint, matching the default scope lens
    // (src/filters.js).
    bounds: HOME_BOUNDS,
    fitBoundsOptions: { padding: 20 },
    attributionControl: false,
  });

  map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');

  map.addControl(makeFitControl(), 'top-right');
  map.addControl(makeLegendControl(), 'bottom-left');

  map.on('load', () => {
    // Coastline reference line — subtle teal
    map.addSource('coastline', { type: 'geojson', data: COASTLINE_URL });
    map.addLayer({
      id: 'coastline-line',
      type: 'line',
      source: 'coastline',
      paint: {
        'line-color': '#0d6e6e',
        'line-width': 0.6,
        'line-opacity': 0.45,
      },
    });

    // Facilities source — NON-CLUSTERED.
    //
    // We used to run this source with cluster:true + clusterRadius:50, but
    // MapLibre-GL 4.7.1's GeoJSON source gets into a wedged state when the
    // source is added with empty features and then later setData()-ed with
    // real features while other sources (the default-on overlays) are still
    // loading. The cluster index never rebuilds, and 200 points render as
    // at most a single stray unclustered dot. At this dataset size (≈200
    // points) clustering isn't necessary for performance, and the user-
    // facing UX (viewport-driven browse list) is clearer without it.
    map.addSource('facilities', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });

    map.addLayer({
      id: 'facility-points',
      type: 'circle',
      source: 'facilities',
      paint: {
        'circle-radius': 6,
        'circle-color': colorExprFor(_colorMode),
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#fff',
      },
    });

    map.addLayer({
      id: 'facility-points-hover',
      type: 'circle',
      source: 'facilities',
      filter: ['==', ['get', 'id'], ''],
      paint: {
        'circle-radius': 9,
        'circle-color': 'transparent',
        'circle-stroke-width': 2.5,
        'circle-stroke-color': '#0d6e6e',
      },
    });

    map.on('click', 'facility-points', (e) => {
      const feat = e.features[0];
      const coords = feat.geometry.coordinates.slice();
      const p = feat.properties;
      // MapLibre stringifies array-valued feature properties when a feature
      // passes through its tiler. Re-parse list fields back into real arrays.
      for (const key of ['areas', 'networks', 'funders', 'regions', 'region_kinds']) {
        if (typeof p[key] === 'string') {
          try { p[key] = JSON.parse(p[key]); } catch (_) { p[key] = []; }
        }
      }
      const popup = new maplibregl.Popup({ maxWidth: '320px' })
        .setLngLat(coords)
        .setHTML(popupHtml(p))
        .addTo(map);
      // Registry ids and harmonized coverage come from the site's card
      // (public/cache/browse_cards.json, fetched once and shared with the
      // Browse tab); the popup opens at once and fills in when it arrives.
      cardById(p.id).then((card) => {
        const slot = popup.getElement()?.querySelector(`.popup-geri[data-id="${CSS.escape(p.id)}"]`);
        if (slot && card) slot.innerHTML = popupGeriHtml(card);
      }).catch(() => { /* no cache: the popup keeps what it has */ });
    });

    map.on('mousemove', 'facility-points', (e) => {
      map.getCanvas().style.cursor = 'pointer';
      const id = e.features[0].properties.id || '';
      map.setFilter('facility-points-hover', ['==', ['get', 'id'], id]);
    });
    map.on('mouseleave', 'facility-points', () => {
      map.getCanvas().style.cursor = '';
      map.setFilter('facility-points-hover', ['==', ['get', 'id'], '']);
    });


    // Fire a custom 'facilities:sourceready' event so the rest of the app
    // can know the source exists and start painting/list-syncing.
    map.fire('facilities:sourceready');
  });

  return map;
}

/**
 * Compute which of the currently-rendered features fall inside the map's
 * current viewport bounds. Used by main.js to drive the bottom browse list
 * and the facility-count status — "only show what's actually visible".
 */
export function featuresInView() {
  if (!map) return _currentFeatures;
  const b = map.getBounds();
  return _currentFeatures.filter((f) => {
    const c = f.geometry?.coordinates;
    if (!Array.isArray(c)) return false;
    const [lng, lat] = c;
    return b.contains([lng, lat]);
  });
}

/** Subscribe to map move events so the UI can re-sync viewport-visible features. */
export function onViewportChange(handler) {
  const fire = () => handler(featuresInView());
  if (!map) return () => {};
  map.on('moveend', fire);
  map.on('zoomend', fire);
  return () => {
    map.off('moveend', fire);
    map.off('zoomend', fire);
  };
}

export function renderFacilities(features) {
  _currentFeatures = features;
  // No WebGL → no map → no source to paint. Stash the features so the
  // browse / stats / people tabs still render and bail before we attach
  // listeners that the stub map would never fire.
  if (_stubMode) return;
  const payload = { type: 'FeatureCollection', features };

  // The old gate was `map.isStyleLoaded()`, but that flips back to false every
  // time a new source gets added to the style — e.g. when the default-on
  // overlays kick off their lazy GeoJSON fetches in initOverlays(). In that
  // window the polled setData call never fires and the facilities source
  // stays empty even though its layers already exist. The only precondition
  // that actually matters here is "the `facilities` source has been created",
  // which happens synchronously inside `map.on('load', ...)`. Wait for that
  // instead.
  const trySet = () => {
    const src = map?.getSource('facilities');
    if (src) {
      src.setData(payload);
      return true;
    }
    return false;
  };

  if (trySet()) return;
  if (!map) {
    // Extremely early call (initMap hasn't returned yet): fall back to a
    // short poll until the Map instance is created.
    const iv = setInterval(() => {
      if (map) { clearInterval(iv); waitForSource(); }
    }, 50);
    return;
  }
  waitForSource();

  function waitForSource() {
    if (trySet()) return;
    const onStyleData = () => {
      if (trySet()) map.off('styledata', onStyleData);
    };
    map.on('styledata', onStyleData);
    // Safety net in case styledata never fires for this particular case.
    map.once('load', trySet);
  }
}

function popupHtml(p) {
  const color = TYPE_COLORS[p.type] || '#64748b';
  const nameHtml = p.url
    ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.name)}</a>`
    : esc(p.name);
  const areas = Array.isArray(p.areas) && p.areas.length
    ? p.areas.slice(0, 4).map(esc).join(', ') : null;
  const networks = Array.isArray(p.networks) && p.networks.length
    ? p.networks.slice(0, 3).map(esc).join(', ') : null;
  const funders = Array.isArray(p.funders) && p.funders.length
    ? p.funders.slice(0, 3).map(esc).join(', ') : null;
  const regions = Array.isArray(p.regions) && p.regions.length
    ? p.regions.slice(0, 4).map(esc).join(', ') : null;

  return `<div class="popup">
    <div class="popup-name">${nameHtml}${p.acronym ? ` <span class="popup-acr">(${esc(p.acronym)})</span>` : ''}</div>
    <div class="popup-meta">
      <span class="type-badge" style="background:${color}">${esc(p.type || 'unknown')}</span>
      ${p.country ? `<span class="popup-country">${esc(p.country)}</span>` : ''}
    </div>
    ${p.parent_org ? `<div class="popup-row"><em>Org:</em> ${esc(p.parent_org)}</div>` : ''}
    ${areas ? `<div class="popup-row"><em>Research:</em> ${areas}</div>` : ''}
    ${networks ? `<div class="popup-row"><em>Networks:</em> ${networks}</div>` : ''}
    ${regions ? `<div class="popup-row"><em>Inside:</em> ${regions}</div>` : ''}
    ${funders ? `<div class="popup-row"><em>Funders:</em> ${funders}</div>` : ''}
    <div class="popup-geri" data-id="${esc(p.id)}"></div>
    ${p.url ? `<a class="popup-source" href="${esc(p.url)}" target="_blank" rel="noopener">Visit website</a>` : ''}
  </div>`;
}

// The GERI part of a popup: harmonized coverage (one line per variable)
// and the site's registry ids, from its Browse card.
function popupGeriHtml(card) {
  const { registry, harmonized } = splitIdentifiers(card);
  const cov = card.coverage || [];
  const covHtml = cov.length
    ? `<div class="popup-row"><em>GERI harmonized</em> <span class="popup-harm-ids">${esc(harmonized.join(' · '))}</span>
         <ul class="popup-cov">${cov.map((c) => `<li>${esc(variableLabel(c.variable))}
           <span>${esc(yearSpan(c.first, c.last))}</span></li>`).join('')}</ul></div>`
    : '';
  const shown = registry.slice(0, 6);
  const idsHtml = shown.length
    ? `<div class="popup-row"><em>Ids:</em> ${shown.map((i) => {
        const href = idHref(i);
        const val = href
          ? `<a href="${esc(href)}" target="_blank" rel="noopener" title="${esc(i.value)}">${esc(idText(i))}</a>`
          : esc(idText(i));
        return `<span class="popup-id"><b>${esc(schemeLabel(i.scheme))}</b> ${val}</span>`;
      }).join(' ')}${registry.length > shown.length ? ` <span class="popup-more">+${registry.length - shown.length}</span>` : ''}</div>`
    : '';
  return covHtml + idsHtml;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

// ── Custom controls ────────────────────────────────────────────────
function makeFitControl() {
  return {
    onAdd(m) {
      const div = document.createElement('div');
      div.className = 'maplibregl-ctrl fit-control';
      // Inline SVG: U+2316 has no glyph in many system fonts (an empty box).
      div.innerHTML = '<a href="#" title="Zoom to data"><svg viewBox="0 0 16 16" width="12" height="12" '
        + 'aria-hidden="true" focusable="false" style="vertical-align:-1px"><circle cx="8" cy="8" r="4.5" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 1v4M8 11v4M1 8h4M11 8h4" '
        + 'stroke="currentColor" stroke-width="1.5"/></svg> Fit</a>';
      div.querySelector('a').addEventListener('click', (e) => {
        e.preventDefault();
        if (_currentFeatures.length === 0) return;
        const coords = _currentFeatures.map((f) => f.geometry?.coordinates).filter(Boolean);
        if (!coords.length) return;
        const lngs = coords.map((c) => c[0]);
        const lats = coords.map((c) => c[1]);
        m.fitBounds(
          [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
          { padding: 60 }
        );
      });
      return div;
    },
    onRemove() {},
  };
}

function makeLegendControl() {
  return {
    onAdd() {
      const div = document.createElement('div');
      div.className = 'maplibregl-ctrl legend-control';
      div.innerHTML = `
        <div class="legend-header">
          <span>Legend</span>
          <span class="legend-toggle">&#9650;</span>
        </div>
        <div class="legend-body">
          <div class="legend-section legend-points">
            <div class="legend-section-label">Facilities</div>
            <div class="legend-color-mode">
              <label><input type="radio" name="color-mode" value="sphere" /> By primary sphere</label>
              <label><input type="radio" name="color-mode" value="type" /> By facility type</label>
            </div>
            <div class="legend-types" id="legend-types">Loading…</div>
          </div>
          <div class="legend-section legend-overlays" id="legend-overlays" hidden>
            <div class="legend-section-label">Overlays</div>
            <div id="legend-overlay-rows"></div>
          </div>
        </div>
      `;
      // Reflect the persisted color mode in the radio group, then wire
      // it up so a user click flips the marker color encoding live.
      const radios = div.querySelectorAll('input[name="color-mode"]');
      radios.forEach((r) => {
        r.checked = (r.value === _colorMode);
        r.addEventListener('change', (ev) => {
          if (ev.target.checked) setColorMode(ev.target.value);
        });
      });
      div.querySelector('.legend-header').addEventListener('click', () => {
        div.classList.toggle('collapsed');
        div.querySelector('.legend-toggle').innerHTML =
          div.classList.contains('collapsed') ? '&#9660;' : '&#9650;';
      });
      div.addEventListener('click', (e) => e.stopPropagation());
      div.addEventListener('wheel', (e) => e.stopPropagation());

      const refresh = () => {
        const ov = _legendOverlayProvider();
        const sec = div.querySelector('#legend-overlays');
        const rows = div.querySelector('#legend-overlay-rows');
        if (!ov || ov.length === 0) {
          sec.hidden = true;
          rows.innerHTML = '';
          return;
        }
        sec.hidden = false;
        rows.innerHTML = ov.map((o) =>
          `<div class="legend-row">
            <span class="legend-chip legend-chip-square" style="background:${o.color}"></span>
            <span>${esc(o.label)}</span>
          </div>`
        ).join('');
      };
      div.addEventListener('legend:refresh', refresh);

      // Initial population: facility types via vocab CSV, limited to the
      // types TYPE_COLORS paints (the GERI types), in that order.
      const SHOWN_TYPES = new Set(Object.keys(TYPE_COLORS));

      // Cache the type-chip HTML once (it depends only on the vocab
      // CSV + TYPE_COLORS) and the sphere-chip HTML once (it's
      // SPHERE_COLORS + an async fetch of the spheres vocab CSV for
      // labels). renderChips() picks whichever block matches the
      // current _colorMode.
      let typeChipHtml = '';
      let sphereChipHtml = Object.entries(SPHERE_COLORS).map(([slug, color]) =>
        `<div class="legend-row"><span class="legend-chip" style="background:${color}"></span><span>${esc(slug)}</span></div>`
      ).join('');

      const renderChips = () => {
        const body = div.querySelector('#legend-types');
        if (!body) return;
        body.innerHTML = (_colorMode === 'sphere') ? sphereChipHtml : typeChipHtml;
      };

      fetchCSV(`${BASE}vocab/facility_types.csv`).then((rows) => {
        typeChipHtml = rows
          .filter((r) => SHOWN_TYPES.has(r.slug))
          .map((r) => {
            const color = TYPE_COLORS[r.slug] || '#64748b';
            return `<div class="legend-row">
              <span class="legend-chip" style="background:${color}"></span>
              <span>${esc(r.label)}</span>
            </div>`;
          }).join('');
        renderChips();
      }).catch(() => {
        typeChipHtml = Object.entries(TYPE_COLORS).map(([slug, color]) =>
          `<div class="legend-row"><span class="legend-chip" style="background:${color}"></span><span>${slug}</span></div>`
        ).join('');
        renderChips();
      });

      // Replace the sphere-chip stub with a label-rich version once
      // the spheres vocab CSV lands. Tolerant of a missing CSV (e.g.
      // before Wave A populated it on a fresh deploy) — falls back to
      // the slug-only stub above.
      fetchCSV(`${BASE}vocab/spheres.csv`).then((rows) => {
        if (Array.isArray(rows) && rows.length) {
          sphereChipHtml = rows.map((r) => {
            const color = SPHERE_COLORS[r.slug] || '#64748b';
            return `<div class="legend-row">
              <span class="legend-chip" style="background:${color}"></span>
              <span>${esc(r.label || r.slug)}</span>
            </div>`;
          }).join('');
          renderChips();
        }
      }).catch(() => { /* keep stub */ });

      // Re-render chips whenever the color mode changes. setColorMode()
      // calls refreshLegend() which dispatches 'legend:refresh' on this
      // element — piggy-back on the same event.
      div.addEventListener('legend:refresh', renderChips);

      renderChips();
      refresh();
      return div;
    },
    onRemove() {},
  };
}
