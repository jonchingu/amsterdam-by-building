// Tokyo, one by one: step through the PLATEAU buildings, each framed on its own with its neighbours around it.
// Data from pipeline/tokyo_s01_buildings.py: buildings.json (columnar index) and cells/<i>_<j>.bin (geometry);
// names, years, architects and photos from Wikidata in wiki.json (pipeline/tokyo_s02_wiki.py), when present.
import * as THREE from '../vendor/three.module.js';
import { OrbitControls } from '../vendor/OrbitControls.js';

const DATA = '../data/tokyo/';
let current = -1;
const cells = new Map();
const ROW = 44;
const SUN = new THREE.Vector3(-0.45, 1, 0.55).normalize();

const $ = (id) => document.getElementById(id);
const statusEl = $('status');

let index;
try {
  const r = await fetch(DATA + 'buildings.json');
  if (!r.ok) throw new Error(r.status);
  index = await r.json();
} catch (e) {
  statusEl.textContent = 'No data yet: run pipeline.tokyo_s00_fetch and pipeline.tokyo_s01_buildings, then reload.';
  throw e;
}
const C = index.columns;
const N = C.bldg.length;
const wardOf = (i) => index.wards[C.ward[i]];
const idOf = (i) => `${wardOf(i)[0]}-bldg-${C.bldg[i]}`;
const addressOf = (i) => index.addresses[C.address[i]];
const members = index.cells.map(() => []);
for (let i = 0; i < N; i++) members[C.cell[i]][C.slot[i]] = i;
const cellXY = index.cells.map((k) => k.split('_').map(Number));
const cellByKey = new Map(index.cells.map((k, ci) => [k, ci]));

// Wikidata's name comes first: PLATEAU's 名称 is sometimes a tenant (the Grand Hyatt is filed under a police box).
const wiki = new Array(N);
let heritageLevels = [];
try {
  const r = await fetch(DATA + 'wiki.json');
  if (r.ok) {
    const data = await r.json();
    heritageLevels = data.heritageLevels || [];
    for (let i = 0; i < N; i++) wiki[i] = data.buildings[idOf(i)];
  }
} catch { /* the viewer works without it */ }
const nameOf = (i) => wiki[i]?.ja || C.name[i] || wiki[i]?.en || '';
const labels = (list) => (list || []).flat().filter((v) => typeof v === 'string');
const haystack = Array.from({ length: N }, (_, i) => {
  const w = wiki[i] || {};
  return [nameOf(i), C.name[i], w.en || '', index.addresses[C.address[i]], idOf(i),
    ...labels(w.types), ...labels(w.styles), ...labels(w.heritage)].join(' ').toLowerCase();
});

// ---------------------------------------------------------------- colour modes for the neighbours
// Flood colours are the national hazard-map scale (水害ハザードマップ作成の手引き); eras follow the reigns.
const MODES = {
  plain: { title: 'Plain', bins: [] },
  floors: { title: 'Floors', note: 'Floors above ground, from PLATEAU.', value: (i) => C.floors[i] || null, bins: [
    ['1–2', 1, 2, '#dce8eb'], ['3–5', 3, 5, '#b3d0d8'], ['6–10', 6, 10, '#84b2c2'],
    ['11–20', 11, 20, '#5591a8'], ['21–40', 21, 40, '#2f6f8c'], ['41 and more', 41, Infinity, '#1b4b66']] },
  flood: { title: 'Flood', note: 'Depth under the assumed maximum rainfall, worst river basin.',
    value: (i) => C.flood[i] || null, bins: [
      ['Under 0.5 m', 0, 0.5, '#f7f5a9'], ['0.5–3 m', 0.5, 3, '#ffd8c0'], ['3–5 m', 3, 5, '#ffb7b7'],
      ['5–10 m', 5, 10, '#ff9191'], ['10 m and more', 10, Infinity, '#f285c9']] },
  fire: { title: 'Fire zone', note: 'Fire-prevention districts of the city plan.', value: (i) => C.fire[i] || null,
    bins: index.fires.slice(1).map(([ja, en], k) => [`${en} ${ja}`, k + 1, k + 1, ['#e3b98f', '#b5653a'][k % 2]]) },
  heritage: { title: 'Heritage', note: 'Highest heritage designation, from Wikidata.',
    value: (i) => wiki[i]?.heritage?.[0]?.[2] ?? null,
    bins: heritageLevels.map((label, k) => [label, k, k,
      ['#5e1846', '#8e2f68', '#c0679a', '#3f5aa6', '#7f95d1', '#a99f8c'][k] || '#a99f8c']) },
  era: { title: 'Era', note: 'Year built or founded, from Wikidata; known for landmarks only.', value: (i) => wiki[i]?.year ?? null, bins: [
    ['Before 1868 · Edo and earlier', -Infinity, 1867, '#6b4a2b'], ['1868–1911 Meiji', 1868, 1911, '#a5642a'],
    ['1912–1925 Taishō', 1912, 1925, '#c99a3b'], ['1926–1944 early Shōwa', 1926, 1944, '#7f9a4a'],
    ['1945–1988 postwar Shōwa', 1945, 1988, '#3f8f7b'], ['1989–2018 Heisei', 1989, 2018, '#3a6fa0'],
    ['2019– Reiwa', 2019, Infinity, '#6a4f9a']] },
};
for (const mode of Object.values(MODES)) {
  mode.bins = mode.bins.map(([label, lo, hi, hex]) => ({ label, lo, hi, color: new THREE.Color(hex), count: 0 }));
  if (!mode.value) continue;
  for (let i = 0; i < N; i++) { const b = binOf(mode, i); if (b) b.count++; }
}
let mode = MODES.plain;
const plainColor = new THREE.Color();
function binOf(m, i) {
  const v = m.value?.(i);
  return v == null ? null : m.bins.find((b) => v >= b.lo && v <= b.hi) || null;
}

// Metres from Tokyo Station back to latitude and longitude, for the map links.
const [LAT0, LON0] = index.origin;
function latLon(i) {
  const a = 6378137, e2 = 6.69437999014e-3, p = LAT0 * Math.PI / 180, s = Math.sin(p) ** 2;
  const m = a * (1 - e2) / (1 - e2 * s) ** 1.5, n = a / Math.sqrt(1 - e2 * s);
  return [LAT0 - C.z[i] / m * 180 / Math.PI, LON0 + C.x[i] / (n * Math.cos(p)) * 180 / Math.PI];
}

// ---------------------------------------------------------------- scene
const canvas = $('scene');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;
const scene = new THREE.Scene();
scene.background = new THREE.Color();
scene.fog = new THREE.Fog(0, 200, 800);
const camera = new THREE.PerspectiveCamera(35, 1, 0.5, 30000);
camera.position.set(-150, 120, 200);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI * 0.495;
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
controls.autoRotate = !reducedMotion;
controls.autoRotateSpeed = 0.7;

const hemi = new THREE.HemisphereLight(0xffffff, 0xb8bec3, 1.7);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xffffff, 2.1);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.4;
scene.add(sun, sun.target);

const ground = new THREE.Mesh(new THREE.PlaneGeometry(60000, 60000), new THREE.MeshStandardMaterial({ roughness: 1 }));
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.05;
ground.receiveShadow = true;
scene.add(ground);

const contextMat = new THREE.MeshStandardMaterial({ roughness: 0.9, flatShading: true, vertexColors: true });
const focusMat = new THREE.MeshStandardMaterial({ roughness: 0.7, flatShading: true,
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
const edgeMat = new THREE.LineBasicMaterial({ transparent: true, opacity: 0.5 });
let edges = null;

// Colours come from the page's CSS tokens, so the scene follows the light or dark theme.
function applyTheme() {
  const css = getComputedStyle(document.documentElement);
  const token = (name) => new THREE.Color(css.getPropertyValue(name).trim());
  scene.background.copy(token('--sky'));
  scene.fog.color.copy(token('--sky'));
  ground.material.color.copy(token('--scene-ground'));
  plainColor.copy(token('--scene-context'));
  for (const entry of cells.values()) if (entry.mesh) paintCell(entry);
  focusMat.color.copy(token('--accent'));
  edgeMat.color.copy(token('--scene-edge'));
  const dark = css.colorScheme.includes('dark');
  hemi.intensity = dark ? 0.9 : 1.7;
  sun.intensity = dark ? 1.4 : 2.1;
}
applyTheme();
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
new MutationObserver(applyTheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

function resize() {
  renderer.setSize(innerWidth, innerHeight, false);
  camera.aspect = innerWidth / innerHeight;
  if (current >= 0) frameView();
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();

// ---------------------------------------------------------------- cells
// A cell holds every building whose centre falls in one 500 m square; it is drawn as one mesh whose groups
// split out the building in view, so the focus material can colour it. Vertex colours carry the colour mode.

function loadCell(ci) {
  if (!cells.has(ci)) {
    const entry = { ci };
    entry.ready = fetch(`${DATA}cells/${index.cells[ci]}.bin`)
      .then((r) => { if (!r.ok) throw new Error(`cell ${index.cells[ci]}: ${r.status}`); return r.arrayBuffer(); })
      .then((buf) => buildCell(entry, buf))
      .catch((e) => { cells.delete(ci); throw e; });
    cells.set(ci, entry);
  }
  return cells.get(ci).ready;
}

function buildCell(entry, buf) {
  const n = new Uint32Array(buf, 0, 1)[0];
  const vc = new Uint32Array(buf, 4, n), ic = new Uint32Array(buf, 4 + 4 * n, n);
  const vStart = new Uint32Array(n + 1), iStart = new Uint32Array(n + 1);
  for (let k = 0; k < n; k++) { vStart[k + 1] = vStart[k] + vc[k]; iStart[k + 1] = iStart[k] + ic[k]; }
  const V = vStart[n], I = iStart[n];
  const local = new Float32Array(buf, 4 + 8 * n, 3 * V);
  const localIdx = new Uint32Array(buf, 4 + 8 * n + 12 * V, I);
  const pos = new Float32Array(3 * V), idx = new Uint32Array(I);
  const list = members[entry.ci];
  for (let k = 0; k < n; k++) {
    const bx = C.x[list[k]], bz = C.z[list[k]];
    for (let v = vStart[k]; v < vStart[k + 1]; v++) {
      pos[3 * v] = local[3 * v] + bx; pos[3 * v + 1] = local[3 * v + 1]; pos[3 * v + 2] = local[3 * v + 2] + bz;
    }
    for (let t = iStart[k]; t < iStart[k + 1]; t++) idx[t] = localIdx[t] + vStart[k];
  }
  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geom.setIndex(new THREE.BufferAttribute(idx, 1));
  geom.setAttribute('color', new THREE.BufferAttribute(new Uint8Array(3 * V), 3, true));
  geom.computeVertexNormals();
  geom.computeBoundingSphere();
  const mesh = new THREE.Mesh(geom, [contextMat, focusMat]);
  mesh.castShadow = mesh.receiveShadow = true;
  mesh.userData.ci = entry.ci;
  Object.assign(entry, { mesh, local, localIdx, vStart, iStart });
  paintCell(entry);
  scene.add(mesh);
  applyGroups(entry);
  return entry;
}

function paintCell(entry) {
  const attr = entry.mesh.geometry.getAttribute('color'), rgb = attr.array, list = members[entry.ci];
  for (let k = 0; k < list.length; k++) {
    const c = binOf(mode, list[k])?.color || plainColor;
    const r = c.r * 255, g = c.g * 255, b = c.b * 255;
    for (let v = entry.vStart[k]; v < entry.vStart[k + 1]; v++) { rgb[3 * v] = r; rgb[3 * v + 1] = g; rgb[3 * v + 2] = b; }
  }
  attr.needsUpdate = true;
}

function setMode(key) {
  mode = MODES[key];
  $('photoImg').addEventListener('error', () => { $('photo').hidden = true; });
for (const b of document.querySelectorAll('.modes button')) b.setAttribute('aria-pressed', b.dataset.mode === key);
  const legend = $('legend');
  legend.replaceChildren();
  legend.hidden = !mode.value;
  if (mode.value) {
    const note = document.createElement('p');
    note.textContent = mode.note;
    legend.appendChild(note);
    for (const b of mode.bins.filter((bin) => bin.count)) {
      const row = document.createElement('div');
      row.innerHTML = '<i></i><span></span><span class="n"></span>';
      row.children[0].style.background = `#${b.color.getHexString()}`;
      row.children[1].textContent = b.label;
      row.children[2].textContent = b.count.toLocaleString('en');
      legend.appendChild(row);
    }
  }
  for (const entry of cells.values()) if (entry.mesh) paintCell(entry);
}

function applyGroups(entry) {
  const geom = entry.mesh.geometry, total = geom.index.count;
  geom.clearGroups();
  const k = current >= 0 && C.cell[current] === entry.ci ? C.slot[current] : -1;
  if (k < 0) { geom.addGroup(0, total, 0); return; }
  const a = entry.iStart[k], b = entry.iStart[k + 1];
  if (a > 0) geom.addGroup(0, a, 0);
  geom.addGroup(a, b - a, 1);
  if (b < total) geom.addGroup(b, total - b, 0);
}

function dropFarCells(ci) {
  const [x0, y0] = cellXY[ci];
  for (const [cj, entry] of cells) {
    const [x, y] = cellXY[cj];
    if (Math.max(Math.abs(x - x0), Math.abs(y - y0)) <= 2 || !entry.mesh) continue;
    scene.remove(entry.mesh);
    entry.mesh.geometry.dispose();
    cells.delete(cj);
  }
}

function neighbourCells(ci) {
  const [x0, y0] = cellXY[ci], out = [];
  for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
    const cj = cellByKey.get(`${x0 + dx}_${y0 + dy}`);
    if (cj !== undefined && cj !== ci) out.push(cj);
  }
  return out;
}

// ---------------------------------------------------------------- order and filters
let order = new Int32Array(0);
const rankOf = new Int32Array(N).fill(-1);
let lastRank = 0;
const shuffleKey = new Float64Array(N).map(() => Math.random());
const collator = new Intl.Collator('ja');

function label(i) {
  return nameOf(i) || (addressOf(i) || idOf(i)).replace(/^東京都/, '');
}

function refilter() {
  const q = $('search').value.trim().toLowerCase();
  const ward = $('ward').value, usage = $('usage').value;
  const named = $('named').checked, lod2 = $('lod2').checked, heritage = $('heritageOnly').checked;
  const keep = [];
  for (let i = 0; i < N; i++) {
    if (named && !nameOf(i)) continue;
    if (lod2 && C.lod[i] < 2) continue;
    if (heritage && !wiki[i]?.heritage) continue;
    if (ward !== '' && C.ward[i] !== +ward) continue;
    if (usage !== '' && C.usage[i] !== +usage) continue;
    if (q && !haystack[i].includes(q)) continue;
    keep.push(i);
  }
  const sort = $('sort').value;
  const h = (i) => C.height[i] || 0;
  if (sort === 'height') keep.sort((a, b) => h(b) - h(a));
  else if (sort === 'area') keep.sort((a, b) => (C.area[b] || 0) - (C.area[a] || 0) || h(b) - h(a));
  else if (sort === 'shuffle') keep.sort((a, b) => shuffleKey[a] - shuffleKey[b]);
  else if (sort === 'year') keep.sort((a, b) => (wiki[a]?.year ?? Infinity) - (wiki[b]?.year ?? Infinity) || h(b) - h(a));
  else keep.sort((a, b) => (!nameOf(a) - !nameOf(b)) || (nameOf(a) && collator.compare(nameOf(a), nameOf(b)))
    || C.address[a] - C.address[b] || h(b) - h(a));
  rankOf.fill(-1);
  order = Int32Array.from(keep);
  order.forEach((i, r) => { rankOf[i] = r; });
  $('count').textContent = `${order.length.toLocaleString('en')} of ${N.toLocaleString('en')} buildings`;
  listEl.querySelector('.spacer').style.height = `${order.length * ROW}px`;
  if (order.length && rankOf[current] < 0) show(order[0]);
  else { renderList(); scrollToCurrent(); updatePos(); }
}

function step(d) {
  if (!order.length) return;
  const r = rankOf[current] >= 0 ? rankOf[current] : lastRank - (d > 0 ? 1 : 0);
  show(order[(r + d + order.length) % order.length]);
}

// ---------------------------------------------------------------- list (only the visible rows exist)
const listEl = $('list');
const rows = [];
function renderList() {
  const first = Math.max(0, Math.floor(listEl.scrollTop / ROW) - 4);
  const last = Math.min(order.length, first + Math.ceil(listEl.clientHeight / ROW) + 8);
  let used = 0;
  for (let r = first; r < last; r++, used++) {
    let el = rows[used];
    if (!el) {
      el = document.createElement('div');
      el.className = 'item';
      el.setAttribute('role', 'option');
      el.innerHTML = '<span class="rank"></span><span class="label" lang="ja"></span><span class="metric"></span>';
      el.addEventListener('click', () => show(order[+el.dataset.rank]));
      listEl.appendChild(el);
      rows.push(el);
    }
    const i = order[r];
    el.hidden = false;
    el.dataset.rank = r;
    el.style.top = `${r * ROW}px`;
    el.setAttribute('aria-selected', i === current);
    el.children[0].textContent = r + 1;
    el.children[1].textContent = label(i);
    el.children[1].classList.toggle('unnamed', !nameOf(i));
    el.children[2].textContent = $('sort').value === 'year' && wiki[i]?.year != null ? `${wiki[i].year}`
      : C.height[i] ? `${Math.round(C.height[i])} m` : '';
  }
  for (let k = used; k < rows.length; k++) rows[k].hidden = true;
}
listEl.addEventListener('scroll', renderList, { passive: true });

function scrollToCurrent() {
  const r = rankOf[current];
  if (r < 0) return;
  const top = r * ROW;
  if (top < listEl.scrollTop || top + ROW > listEl.scrollTop + listEl.clientHeight) {
    listEl.scrollTop = top - listEl.clientHeight / 2 + ROW / 2;
  }
  renderList();
}

function updatePos() {
  const r = rankOf[current];
  $('pos').textContent = `${r >= 0 ? (r + 1).toLocaleString('en') : '–'} / ${order.length.toLocaleString('en')}`;
}

// ---------------------------------------------------------------- card
function fact(dt, dd, ja, minor = false) {
  const row = document.createDocumentFragment();
  const t = document.createElement('dt'), d = document.createElement('dd');
  if (minor) t.className = d.className = 'minor';
  t.textContent = dt;
  d.textContent = dd;
  if (ja && ja !== dd) {
    const s = document.createElement('span');
    s.className = 'ja'; s.lang = 'ja'; s.textContent = ja;
    d.appendChild(s);
  }
  row.append(t, d);
  return row;
}

function updateCard(i) {
  const [, wardEn, wardJa] = wardOf(i);
  $('kicker').textContent = `${wardEn} ward · ${wardJa}`;
  const w = wiki[i] || {};
  const title = $('title'), name = nameOf(i);
  title.textContent = name || 'Unnamed building';
  title.classList.toggle('unnamed', !name);
  title.lang = name && name !== w.en ? 'ja' : 'en';
  const alt = $('alt');
  alt.replaceChildren();
  if (w.en && w.en !== name) alt.append(Object.assign(document.createElement('span'), { textContent: w.en, lang: 'en' }));
  if (C.name[i] && C.name[i] !== name) {
    alt.append(Object.assign(document.createElement('span'), { textContent: 'Listed in PLATEAU as ' }));
    alt.lastChild.append(Object.assign(document.createElement('span'), { textContent: C.name[i], lang: 'ja' }));
  }
  alt.hidden = !alt.childElementCount;
  const photo = $('photo');
  photo.hidden = !w.image;
  if (w.image) {
    const file = encodeURIComponent(w.image.replaceAll(' ', '_'));
    $('photoImg').src = `https://commons.wikimedia.org/wiki/Special:FilePath/${file}?width=640`;
    $('photoImg').alt = w.en || name;
    $('photoLink').href = `https://commons.wikimedia.org/wiki/File:${file}`;
  }
  $('address').textContent = addressOf(i);
  const facts = $('facts');
  facts.replaceChildren();
  if (C.height[i]) facts.append(fact('Height', `${C.height[i].toFixed(1)} m`));
  if (C.floors[i]) facts.append(fact('Floors', C.basements[i] ? `${C.floors[i]} + ${C.basements[i]} below` : `${C.floors[i]}`));
  if (w.year != null) facts.append(fact('Built or founded', `${w.year}`));
  if (w.architects) facts.append(fact('Architect', w.architects.slice(0, 3).map(([en]) => en).join(', '), '', true));
  if (w.types) facts.append(fact('Type', w.types.slice(0, 2).map(([en]) => en).join(', '), w.types[0][1]));
  if (w.styles) facts.append(fact('Style', w.styles.slice(0, 2).map(([en]) => en).join(', '), w.styles[0][1], true));
  for (const [en, ja] of (w.heritage || []).slice(0, 2)) facts.append(fact('Heritage', en, ja));
  const [useJa, useEn] = index.usages[C.usage[i]];
  if (useJa) facts.append(fact('Use', useEn, useJa));
  if (C.flood[i]) {
    const [, river] = index.rivers[C.river[i]];
    facts.append(fact('Flood depth', `${C.flood[i] < 0.1 ? 'under 0.1' : C.flood[i].toFixed(1)} m, ${river}`
      + (C.floodHours[i] ? `, ${C.floodHours[i]} h` : '')));
  }
  const [lsJa, lsEn] = index.landslides[C.landslide[i]];
  if (lsJa) facts.append(fact('Landslide', lsEn, lsJa));
  const [fireJa, fireEn] = index.fires[C.fire[i]];
  if (fireJa) facts.append(fact('Fire zone', fireEn, fireJa, true));
  const [hdJa, hdEn] = index.heightDistricts[C.heightDistrict[i]];
  if (hdJa) facts.append(fact('Height limit', hdEn, hdJa, true));
  const plan = index.districtPlans[C.districtPlan[i]];
  if (plan) {
    facts.append(fact('District plan', plan, '', true));
    facts.lastChild.lang = 'ja';
  }
  const [strJa, strEn] = index.structures[C.structure[i]];
  if (strJa) facts.append(fact('Structure', strEn, strJa, true));
  if (C.area[i]) facts.append(fact('Footprint', `${Math.round(C.area[i]).toLocaleString('en')} m²`, '', true));
  facts.append(fact('Model', C.lod[i] >= 2 ? 'LOD2, with roof shapes' : 'LOD1, a block at measured height', '', true));
  facts.append(fact('PLATEAU id', idOf(i), '', true));
  const [lat, lon] = latLon(i).map((v) => v.toFixed(6));
  const links = $('links');
  links.replaceChildren();
  const wp = (lang, title) => `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(title.replaceAll(' ', '_'))}`;
  showSummary(i, w);
  for (const [text, href] of [
    w.site && ['Website', w.site],
    w.commons && ['More photos', `https://commons.wikimedia.org/wiki/Category:${encodeURIComponent(w.commons.replaceAll(' ', '_'))}`],
    w.jawiki && ['Wikipedia (ja)', wp('ja', w.jawiki)],
    w.enwiki && ['Wikipedia (en)', wp('en', w.enwiki)],
    w.wd && ['Wikidata', `https://www.wikidata.org/wiki/${w.wd}`],
    ['OpenStreetMap', `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=19/${lat}/${lon}`],
    ['Google Maps', `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`],
  ].filter(Boolean)) {
    const a = document.createElement('a');
    a.href = href; a.target = '_blank'; a.rel = 'noopener'; a.textContent = text;
    links.appendChild(a);
  }
}

// A few sentences on the building: Wikipedia's summary, fetched by the browser (English first, the interface's
// language), else Wikidata's one-line description.
const summaries = new Map();
function showSummary(i, w) {
  const el = $('summary'), src = $('summarySource');
  const fallback = w.descEn || w.descJa || '';
  el.textContent = fallback;
  el.lang = w.descEn ? 'en' : 'ja';
  src.replaceChildren(fallback ? 'Wikidata' : '');
  $('about').hidden = !fallback;
  const lang = w.enwiki ? 'en' : w.jawiki ? 'ja' : null;
  if (!lang) return;
  const title = (lang === 'en' ? w.enwiki : w.jawiki).replaceAll(' ', '_');
  const key = `${lang}:${title}`;
  if (!summaries.has(key)) {
    summaries.set(key, fetch(`https://${lang}.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => (d && d.type === 'standard' && d.extract ? d : null))
      .catch(() => null));
  }
  summaries.get(key).then((d) => {
    if (!d || current !== i) return;
    const sentences = d.extract.match(/[^.!?。]+[.!?。]+["”」]?\s*/g) || [d.extract];
    let text = '';
    for (const s of sentences) { if (text && (text + s).length > 420) break; text += s; }
    el.textContent = text.trim();
    el.lang = lang;
    const a = Object.assign(document.createElement('a'), {
      href: d.content_urls?.desktop?.page || `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(title)}`,
      target: '_blank', rel: 'noopener', textContent: `Wikipedia (${lang})`,
    });
    src.replaceChildren('From ', a, ', CC BY-SA');
    $('about').hidden = false;
  });
}

// ---------------------------------------------------------------- showing a building
let flight = null;
const spherical = new THREE.Spherical();

async function show(i, { fly = true } = {}) {
  current = i;
  if (rankOf[i] >= 0) lastRank = rankOf[i];
  updateCard(i);
  updatePos();
  scrollToCurrent();
  try { history.replaceState(null, '', `#${idOf(i)}`); } catch { /* a sandboxed frame may refuse */ }
  const ci = C.cell[i];
  for (const entry of cells.values()) if (entry.mesh) applyGroups(entry);
  if (!cells.get(ci)?.mesh) statusEl.textContent = 'Loading…';
  let entry;
  try {
    entry = await loadCell(ci);
  } catch (e) {
    statusEl.textContent = 'Could not load this part of the city.';
    console.error(e);
    return;
  }
  if (current !== i) return;
  statusEl.textContent = '';
  setEdges(entry, i);
  frame(entry, i, fly);
  dropFarCells(ci);
  neighbourCells(ci).forEach((cj) => loadCell(cj).catch(console.error));
}

function setEdges(entry, i) {
  if (edges) { scene.remove(edges); edges.geometry.dispose(); }
  const k = C.slot[i];
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(entry.local.slice(3 * entry.vStart[k], 3 * entry.vStart[k + 1]), 3));
  g.setIndex(new THREE.BufferAttribute(entry.localIdx.slice(entry.iStart[k], entry.iStart[k + 1]), 1));
  edges = new THREE.LineSegments(new THREE.EdgesGeometry(g, 25), edgeMat);
  g.dispose();
  edges.position.set(C.x[i], 0, C.z[i]);
  scene.add(edges);
  edges.geometry.computeBoundingBox();
}

// The part of the screen the panels leave free: the building is centred and fitted there.
function freeRect() {
  const box = (sel) => document.querySelector(sel).getBoundingClientRect();
  const browse = document.querySelector('.browse');
  const rect = { left: 0, right: innerWidth, top: 0, bottom: box('.stepper').top };
  if (innerWidth > 760) {
    if (getComputedStyle(browse).display !== 'none') rect.left = box('.browse').right;
    rect.right = box('.card').left;
  } else {
    rect.top = box('.card').bottom;
  }
  return rect;
}

function frameView() {
  const r = freeRect();
  const dx = (r.left + r.right) / 2 - innerWidth / 2, dy = (r.top + r.bottom) / 2 - innerHeight / 2;
  camera.setViewOffset(innerWidth, innerHeight, -dx, -dy, innerWidth, innerHeight);
  const t = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  return Math.min(Math.atan(t * Math.max(r.bottom - r.top, 80) / innerHeight),
    Math.atan(t * camera.aspect * Math.max(r.right - r.left, 80) / innerWidth));
}

function frame(entry, i, fly) {
  const box = edges.geometry.boundingBox.clone().translate(edges.position);
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const radius = Math.max(sphere.radius / Math.sin(frameView()) * 1.05, 25);
  const target = sphere.center.clone();
  target.y = Math.min(target.y, box.max.y * 0.45);
  spherical.setFromVector3(camera.position.clone().sub(controls.target));
  const phi = THREE.MathUtils.clamp(spherical.phi, THREE.MathUtils.degToRad(40), THREE.MathUtils.degToRad(64));
  flight = { t0: performance.now(), dur: fly && !reducedMotion ? 900 : 0, fromTarget: controls.target.clone(), toTarget: target,
    fromRadius: spherical.radius, toRadius: radius, fromPhi: spherical.phi, toPhi: phi };
  scene.fog.near = radius * 1.4;
  scene.fog.far = radius * 4 + 250;
  const reach = sphere.radius * 2.5 + 60;
  Object.assign(sun.shadow.camera, { left: -reach, right: reach, top: reach, bottom: -reach, near: 1, far: reach * 6 });
  sun.shadow.camera.updateProjectionMatrix();
  sun.target.position.copy(sphere.center);
  sun.position.copy(sphere.center).addScaledVector(SUN, reach * 3);
}

function fly(now) {
  if (!flight) return;
  const k = flight.dur ? Math.min(1, (now - flight.t0) / flight.dur) : 1;
  const e = k < 0.5 ? 4 * k ** 3 : 1 - (-2 * k + 2) ** 3 / 2;
  spherical.setFromVector3(camera.position.clone().sub(controls.target));
  controls.target.lerpVectors(flight.fromTarget, flight.toTarget, e);
  spherical.radius = THREE.MathUtils.lerp(flight.fromRadius, flight.toRadius, e);
  spherical.phi = THREE.MathUtils.lerp(flight.fromPhi, flight.toPhi, e);
  camera.position.setFromSpherical(spherical).add(controls.target);
  if (k >= 1) flight = null;
}

// ---------------------------------------------------------------- picking a neighbour
const raycaster = new THREE.Raycaster();
let downAt = null;
canvas.addEventListener('pointerdown', (e) => { downAt = [e.clientX, e.clientY]; });
canvas.addEventListener('pointerup', (e) => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5) return;
  raycaster.setFromCamera(new THREE.Vector2(e.clientX / innerWidth * 2 - 1, -e.clientY / innerHeight * 2 + 1), camera);
  const meshes = [...cells.values()].filter((c) => c.mesh).map((c) => c.mesh);
  for (const hit of raycaster.intersectObjects(meshes, false)) {
    const entry = cells.get(hit.object.userData.ci);
    const t = hit.faceIndex * 3;
    let lo = 0, hi = entry.iStart.length - 2;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (entry.iStart[mid] <= t) lo = mid; else hi = mid - 1; }
    const i = members[entry.ci][lo];
    if (contextMat.visible || i === current) { if (i !== current) show(i); break; }
  }
});

// ---------------------------------------------------------------- controls
function toggle(id, on) {
  $(id).setAttribute('aria-pressed', on);
}
toggle('spin', controls.autoRotate);
$('prev').addEventListener('click', () => step(-1));
$('next').addEventListener('click', () => step(1));
$('random').addEventListener('click', () => order.length && show(order[Math.floor(Math.random() * order.length)]));
$('spin').addEventListener('click', () => { controls.autoRotate = !controls.autoRotate; toggle('spin', controls.autoRotate); });
$('alone').addEventListener('click', () => { contextMat.visible = !contextMat.visible; toggle('alone', !contextMat.visible); });
$('listToggle').addEventListener('click', () => {
  const open = document.querySelector('.browse').classList.toggle('open');
  $('listToggle').setAttribute('aria-expanded', open);
  if (open) scrollToCurrent();
});
for (const b of document.querySelectorAll('.modes button')) b.addEventListener('click', () => setMode(b.dataset.mode));
let typing;
$('search').addEventListener('input', () => { clearTimeout(typing); typing = setTimeout(refilter, 150); });
for (const id of ['ward', 'usage', 'sort', 'named', 'lod2', 'heritageOnly']) $(id).addEventListener('change', refilter);
addEventListener('keydown', (e) => {
  if (e.target.closest('input, select')) { if (e.key === 'Escape') e.target.blur(); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const act = { ArrowRight: () => step(1), ArrowDown: () => step(1), j: () => step(1),
    ArrowLeft: () => step(-1), ArrowUp: () => step(-1), k: () => step(-1),
    r: () => $('random').click(), ' ': () => $('spin').click(), a: () => $('alone').click(),
    '/': () => $('search').focus() }[e.key];
  if (act) { e.preventDefault(); act(); }
});

function fillSelect(id, entries) {
  const el = $(id);
  for (const [value, text] of entries) {
    const o = document.createElement('option');
    o.value = value; o.textContent = text;
    el.appendChild(o);
  }
}
const countBy = (col) => C[col].reduce((m, v) => (m[v] = (m[v] || 0) + 1, m), {});
const wardCounts = countBy('ward'), usageCounts = countBy('usage');
fillSelect('ward', index.wards.map(([, en, ja], w) => [w, `${en} ${ja} (${(wardCounts[w] || 0).toLocaleString('en')})`]));
fillSelect('usage', index.usages.map(([ja, en], u) => [u, `${en} ${ja !== en ? ja : ''} (${(usageCounts[u] || 0).toLocaleString('en')})`])
  .filter(([u]) => u > 0).sort((a, b) => usageCounts[b[0]] - usageCounts[a[0]]));

renderer.setAnimationLoop((now) => {
  fly(now);
  controls.update();
  renderer.render(scene, camera);
});

// Start from the building in the address bar, else from the tallest.
const wanted = decodeURIComponent(location.hash.slice(1));
let start = -1;
if (wanted) for (let i = 0; i < N && start < 0; i++) if (idOf(i) === wanted) start = i;
current = start;
refilter();
if (start >= 0) show(start, { fly: false });
else if (order.length) show(order[0], { fly: false });
