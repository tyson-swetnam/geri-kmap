// cards.js — the pre-computed site cards (public/cache/browse_cards.json,
// written by scripts/export_view_caches.py) and the labels both the
// Browse cards (src/views/list.js) and the map popups (src/map.js) use
// for a site's registry ids and GERI harmonized coverage.

import { DATA_BASE } from './config.js';

// Fetched once and shared. Default caching, not 'force-cache':
// force-cache reuses a stored copy however old, so a returning visitor
// kept the cards from before a data update (and only the ids both
// versions share). The default honours Pages' max-age and then
// revalidates by ETag.
let _allCardsPromise = null;
export function loadAllCardsOnce() {
  if (_allCardsPromise) return _allCardsPromise;
  _allCardsPromise = fetch(`${DATA_BASE}cache/browse_cards.json`)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`cache ${r.status}`))))
    .catch((err) => {
      // Reset so a later call can retry; one failed fetch must not
      // disable the fast path for good.
      _allCardsPromise = null;
      throw err;
    });
  return _allCardsPromise;
}

let _byId = null;
/** The card of one site, or null (no cache, or no such id). */
export async function cardById(id) {
  if (!_byId) {
    const all = await loadAllCardsOnce();
    _byId = new Map(all.map((c) => [c.id, c]));
  }
  return _byId.get(id) || null;
}

// Registry-identifier schemes (site_identifiers.scheme) as labels.
// '<network>-site-code' schemes fall through to "<NETWORK> code".
const SCHEME_LABELS = {
  'deims-id': 'DEIMS',
  'neon-site': 'NEON',
  'icos-station': 'ICOS',
  'fluxnet-id': 'FLUXNET',
  'ozflux-site': 'OzFlux',
  'ausplots-site': 'AusPlots',
  'mexflux-site': 'MexFlux',
  'ameriflux-id': 'AmeriFlux',
  'doi': 'DOI',
  'geri-harmonized-id': 'GERI',
};
export const schemeLabel = (s) => SCHEME_LABELS[s]
  || (s.endsWith('-site-code') ? `${s.slice(0, -10).toUpperCase()} code` : s);

// Listed with the harmonized coverage instead ('geri-harmonized-id'), or
// saying only that the products are a site's sole source ('harmonized-only').
const SCHEMES_HIDDEN = new Set(['harmonized-only', 'geri-harmonized-id']);

/** The ids a site shows as registry ids, and its harmonized site ids. */
export function splitIdentifiers(card) {
  const ids = card?.identifiers || [];
  return {
    registry: ids.filter((i) => !SCHEMES_HIDDEN.has(i.scheme)),
    harmonized: ids.filter((i) => i.scheme === 'geri-harmonized-id').map((i) => i.value),
  };
}

/** Display text (a DEIMS uuid is shortened) and link for one id. */
export const idText = (i) => (i.scheme === 'deims-id' ? `${i.value.slice(0, 8)}…` : i.value);
export const idHref = (i) => (i.scheme === 'doi' ? `https://doi.org/${i.value}` : i.url);

// harmonized_coverage.variable -> what the variable is.
const VARIABLE_LABELS = {
  mean_air_temp_degC: 'Air temperature',
  bulk_precipitation_mm: 'Precipitation',
  mean_swc_percent: 'Soil moisture',
  mean_soil_temp_degC: 'Soil temperature',
  sand_percent: 'Soil texture: sand',
  silt_percent: 'Soil texture: silt',
  clay_percent: 'Soil texture: clay',
};
export const variableLabel = (v) => VARIABLE_LABELS[v] || v;

/** '2013–2021', or one year when first and last fall in it. */
export function yearSpan(first, last) {
  const a = first ? String(first).slice(0, 4) : '';
  const b = last ? String(last).slice(0, 4) : '';
  return b && b !== a ? `${a}–${b}` : a;
}
