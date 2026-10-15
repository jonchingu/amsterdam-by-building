// Tokyo, one by one: step through the PLATEAU buildings, each framed on its own with its neighbours around it.
// Data from pipeline/tokyo_s01_buildings.py: buildings.json (columnar index) and cells/<i>_<j>.bin (geometry).
import * as THREE from '../vendor/three.module.js';
import { OrbitControls } from '../vendor/OrbitControls.js';

const DATA = '../data/tokyo/';
let current = -1;
const ROW = 44;
const SKY = 0xe6e8ea;
const ACCENT = 0xe0401f;
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
scene.background = new THREE.Color(SKY);
scene.fog = new THREE.Fog(SKY, 200, 800);
const camera = new THREE.PerspectiveCamera(35, 1, 0.5, 30000);
camera.position.set(-150, 120, 200);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI * 0.495;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.7;

scene.add(new THREE.HemisphereLight(0xffffff, 0xb8bec3, 1.7));
const sun = new THREE.DirectionalLight(0xffffff, 2.1);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.4;
scene.add(sun, sun.target);

const ground = new THREE.Mesh(new THREE.PlaneGeometry(60000, 60000), new THREE.MeshStandardMaterial({ color: 0xf2f3f4, roughness: 1 }));
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.05;
ground.receiveShadow = true;
scene.add(ground);

const contextMat = new THREE.MeshStandardMaterial({ color: 0xd3d7da, roughness: 0.9, flatShading: true });
const focusMat = new THREE.MeshStandardMaterial({ color: ACCENT, roughness: 0.7, flatShading: true,
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
const edgeMat = new THREE.LineBasicMaterial({ color: 0x3a0d03, transparent: true, opacity: 0.5 });
let edges = null;

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
// split out the building in view, so the focus material can colour it.
const cells = new Map();

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
  geom.computeVertexNormals();
  geom.computeBoundingSphere();
  const mesh = new THREE.Mesh(geom, [contextMat, focusMat]);
  mesh.castShadow = mesh.receiveShadow = true;
  mesh.userData.ci = entry.ci;
  Object.assign(entry, { mesh, local, localIdx, vStart, iStart });
  scene.add(mesh);
  applyGroups(entry);
  return entry;
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
  return C.name[i] || (addressOf(i) || idOf(i)).replace(/^東京都/, '');
}

function refilter() {
  const q = $('search').value.trim().toLowerCase();
  const ward = $('ward').value, usage = $('usage').value;
  const named = $('named').checked, lod2 = $('lod2').checked;
  const keep = [];
  for (let i = 0; i < N; i++) {
    if (named && !C.name[i]) continue;
    if (lod2 && C.lod[i] < 2) continue;
    if (ward !== '' && C.ward[i] !== +ward) continue;
    if (usage !== '' && C.usage[i] !== +usage) continue;
    if (q && !(C.name[i].toLowerCase().includes(q) || addressOf(i).includes(q) || idOf(i).includes(q))) continue;
    keep.push(i);
  }
  const sort = $('sort').value;
  const h = (i) => C.height[i] || 0;
  if (sort === 'height') keep.sort((a, b) => h(b) - h(a));
  else if (sort === 'area') keep.sort((a, b) => (C.area[b] || 0) - (C.area[a] || 0) || h(b) - h(a));
  else if (sort === 'shuffle') keep.sort((a, b) => shuffleKey[a] - shuffleKey[b]);
  else keep.sort((a, b) => (!C.name[a] - !C.name[b]) || (C.name[a] && collator.compare(C.name[a], C.name[b]))
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
    el.children[1].classList.toggle('unnamed', !C.name[i]);
    el.children[2].textContent = C.height[i] ? `${Math.round(C.height[i])} m` : '';
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
  const title = $('title');
  title.textContent = C.name[i] || 'Unnamed building';
  title.classList.toggle('unnamed', !C.name[i]);
  title.lang = C.name[i] ? 'ja' : 'en';
  $('address').textContent = addressOf(i);
  const facts = $('facts');
  facts.replaceChildren();
  if (C.height[i]) facts.append(fact('Height', `${C.height[i].toFixed(1)} m`));
  if (C.floors[i]) facts.append(fact('Floors', C.basements[i] ? `${C.floors[i]} + ${C.basements[i]} below` : `${C.floors[i]}`));
  const [useJa, useEn] = index.usages[C.usage[i]];
  if (useJa) facts.append(fact('Use', useEn, useJa));
  const [strJa, strEn] = index.structures[C.structure[i]];
  if (strJa) facts.append(fact('Structure', strEn, strJa, true));
  if (C.area[i]) facts.append(fact('Footprint', `${Math.round(C.area[i]).toLocaleString('en')} m²`, '', true));
  facts.append(fact('Model', C.lod[i] >= 2 ? 'LOD2, with roof shapes' : 'LOD1, a block at measured height', '', true));
  facts.append(fact('PLATEAU id', idOf(i), '', true));
  const [lat, lon] = latLon(i).map((v) => v.toFixed(6));
  const links = $('links');
  links.replaceChildren();
  for (const [text, href] of [
    ['OpenStreetMap', `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=19/${lat}/${lon}`],
    ['Google Maps', `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`],
  ]) {
    const a = document.createElement('a');
    a.href = href; a.target = '_blank'; a.rel = 'noopener'; a.textContent = text;
    links.appendChild(a);
  }
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
  history.replaceState(null, '', `#${idOf(i)}`);
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
  flight = { t0: performance.now(), dur: fly ? 900 : 0, fromTarget: controls.target.clone(), toTarget: target,
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
let typing;
$('search').addEventListener('input', () => { clearTimeout(typing); typing = setTimeout(refilter, 150); });
for (const id of ['ward', 'usage', 'sort', 'named', 'lod2']) $(id).addEventListener('change', refilter);
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
