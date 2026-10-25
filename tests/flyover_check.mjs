/*
  Headless check of the quest flyovers against a running copy of the app (the fixture city works: see fixture_city.py).

    node tests/flyover_check.mjs [http://localhost:8642] [screenshot folder]

  Needs Playwright (require('playwright') must resolve) and its Chromium. Fails with a message on the first problem.
*/
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { resolve, join } from "node:path";

const require = createRequire(resolve("package.json"));
const { chromium } = require("playwright");
const base = process.argv[2] || "http://localhost:8642";
const shots = resolve(process.argv[3] || "out-flyover");
mkdirSync(shots, { recursive: true });

const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const errors = [];
const sleep = ms => new Promise(r => setTimeout(r, ms));
function check(ok, msg) { if (!ok) throw new Error(msg); console.log("ok", msg); }

async function open(opts = {}, query = "lang=en") {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, ...opts });
  const page = await ctx.newPage();
  page.on("pageerror", e => errors.push(String(e)));
  page.on("console", m => { if (m.type() === "error" && !/Failed to load resource|ERR_/.test(m.text())) errors.push(m.text()); });
  await page.goto(`${base}/?${query}`);
  await page.waitForFunction(() => window.__dbg && window.__dbg.quests.length && document.getElementById("loading").hidden, null, { timeout: 120000 });
  return { ctx, page };
}
const cam = page => page.evaluate(() => window.__dbg.camera.position.toArray());
const tourOf = page => page.evaluate(() => window.__dbg.tour);
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
async function waitTourEnd(page, ms = 30000) { await page.waitForFunction(() => !window.__dbg.tour, null, { timeout: ms }); }

// ---- 1. Normal motion: a choice step flies its leg; find steps don't fly to their answer ----
{
  const { ctx, page } = await open();
  const route = await page.evaluate(() => window.__dbg.quests.find(q => q.id === "fixture").route);
  check(route && route.length >= 4, `the fixture quest has a route of ${route?.length} anchors`);

  await page.evaluate(() => { const d = window.__dbg; d.startQuest(d.quests.find(q => q.id === "fixture"), 0, 0, []); });
  await sleep(200);
  check(!(await tourOf(page)), "entering a find step plays no route (the overview flight instead)");

  await page.evaluate(() => { const d = window.__dbg; d.startQuest(d.quests.find(q => q.id === "fixture"), 1, 100, [100]); });
  let t = await tourOf(page);
  check(t && t.kind === "segment", "entering a choice step flies that step's leg of the route");
  await sleep(1800);
  const mid = await cam(page);
  await page.screenshot({ path: join(shots, "1-choice-leg-midway.png") });
  await waitTourEnd(page);
  const stop1 = route.find(a => a.step === 1);
  const end = await cam(page);
  check(dist(end, stop1.p) < 0.5, `the leg ends on the step's framing (${dist(end, stop1.p).toFixed(2)} m off)`);
  check(dist(mid, end) > 20, "the camera was midway along the leg at 1.8 s");
  const fov = await page.evaluate(() => window.__dbg.camera.fov);
  check(Math.abs(fov - 2 * Math.atan(Math.tan(35 / 2 * Math.PI / 180) / stop1.zoom) * 180 / Math.PI) < 0.05, `the lens matches the anchor's zoom ${stop1.zoom}`);
  await page.screenshot({ path: join(shots, "2-choice-framed.png") });

  // Year step after it: also flies; its building stays hidden in red.
  await page.evaluate(() => { const d = window.__dbg; d.startQuest(d.quests.find(q => q.id === "fixture"), 2, 200, [100, 100]); });
  check((await tourOf(page))?.kind === "segment", "entering a year step flies its leg");
  await waitTourEnd(page);
  check(dist(await cam(page), route.find(a => a.step === 2).p) < 0.5, "the year step's leg ends on its framing");
  // The last step is a find: entering it never flies to the answer.
  await page.evaluate(() => { const d = window.__dbg; d.startQuest(d.quests.find(q => q.id === "fixture"), 3, 300, [100, 100, 100]); });
  await sleep(200);
  check(!(await tourOf(page)), "entering the last (find) step plays no route");
  await page.evaluate(() => document.querySelector(".q-close").click());

  // ---- 2. The tour of a finished quest, and the hand-back ----
  await page.evaluate(() => localStorage.setItem("ams-quests2", JSON.stringify({ fixture: { step: 4, best: 340, score: 340, marks: [100, 100, 40, 100] } })));
  await page.click(".quests-open");
  const flyButtons = await page.$$eval(".q-fly", bs => bs.map(b => b.dataset.q));
  check(flyButtons.length === 1 && flyButtons[0] === "fixture", "only the finished quest offers 'Fly the route' in the list");
  await page.click('.q-fly[data-q="fixture"]');
  t = await tourOf(page);
  check(t && t.kind === "tour", "the list's 'Fly the route' starts the tour");
  const shotAt = [3000, 7000, 12000];
  let last = 0;
  for (const [n, ms] of shotAt.entries()) { await sleep(ms - last); last = ms; await page.screenshot({ path: join(shots, `3-tour-${n + 1}.png`) }); }
  const caption = await page.$eval(".q-now", e => e.textContent);
  check(/^Stop \d \/ 4/.test(caption), `the card names the stop: "${caption}"`);
  check((await page.$eval(".q-fly", e => e.textContent)) === "Stop the flight", "the button reads 'Stop the flight' while flying");

  // A drag on the map hands the camera back at once.
  // Damping off for this check: at swiftshader's ~15 fps a drag's own glide lasts seconds, and any motion left after
  // the drag could then only come from the route.
  await page.evaluate(() => { window.__dbg.controls.enableDamping = false; });
  await page.mouse.move(640, 500); await page.mouse.down(); await page.mouse.move(700, 520, { steps: 4 }); await page.mouse.up();
  check(!(await tourOf(page)), "a drag stops the tour");
  check((await page.$eval(".q-fly", e => e.textContent)) === "Fly the route", "the button reads 'Fly the route' again");
  await sleep(300);
  const settled = await cam(page);
  await sleep(1500);
  const later = await cam(page);
  check(dist(settled, later) < 0.05, `after the drag the route no longer moves the camera (${dist(settled, later).toFixed(3)} m in 1.5 s)`);
  await page.evaluate(() => { window.__dbg.controls.enableDamping = true; });

  // A key hands it back.
  await page.click(".q-fly");
  await sleep(1200);
  check((await tourOf(page))?.kind === "tour", "the tour plays again");
  await page.mouse.move(640, 400);
  await page.keyboard.press("w");
  check(!(await tourOf(page)), "a key stops the tour");

  // The wheel hands it back.
  await page.click(".q-fly");
  await sleep(1200);
  await page.mouse.move(640, 400);
  await page.mouse.wheel(0, 200);
  await sleep(50);
  check(!(await tourOf(page)), "the wheel stops the tour");

  // Played to the end, it rests on the opening view.
  await page.click(".q-fly");
  await waitTourEnd(page, 90000);
  check(dist(await cam(page), route.at(-1).p) < 0.5, "the tour ends on the overview");
  await page.evaluate(() => document.querySelector(".q-close").click());
  await sleep(1200);
  check(Math.abs((await page.evaluate(() => window.__dbg.camera.fov)) - 35) < 0.01, "closing the quest opens the lens back to 35°");
  await ctx.close();
}

// ---- 3. Reduced motion: cuts, no glide ----
{
  const { ctx, page } = await open({ reducedMotion: "reduce" });
  const route = await page.evaluate(() => window.__dbg.quests.find(q => q.id === "fixture").route);
  await page.evaluate(() => { const d = window.__dbg; d.startQuest(d.quests.find(q => q.id === "fixture"), 1, 100, [100]); });
  check(!(await tourOf(page)), "with reduced motion a step's leg doesn't play");
  check(dist(await cam(page), route.find(a => a.step === 1).p) < 0.5, "with reduced motion the camera cuts straight to the step's framing");
  await page.evaluate(() => document.querySelector(".q-close").click());
  await page.evaluate(() => { const d = window.__dbg; d.showTour(d.quests.find(q => q.id === "fixture")); });
  check((await tourOf(page))?.cut, "with reduced motion the tour cuts from stop to stop");
  const shown = new Set();
  const stops = route.map((a, i) => ({ a, i })).filter(({ a, i }) => i === 0 || i === route.length - 1 || a.step !== undefined);
  for (let k = 0; k < 120 && (await tourOf(page)); k++) {
    const p = await cam(page);
    const hit = stops.find(({ a }) => dist(p, a.p) < 0.5);
    if (!hit) check(false, `frame ${k}: the camera is between stops (${p.map(v => v.toFixed(0))})`);
    shown.add(hit.i);
    await sleep(500);
  }
  const distinct = new Set(stops.map(({ a }) => a.p.join())).size;   // the closing view is the opening view
  check(!(await tourOf(page)) && shown.size === distinct, `the tour cut through all ${shown.size} distinct stops`);
  await page.screenshot({ path: join(shots, "4-reduced-motion.png") });
  await ctx.close();
}

// ---- 4. Dutch, and a phone ----
{
  const { ctx, page } = await open({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 }, "lang=nl");
  await page.evaluate(() => localStorage.setItem("ams-quests2", JSON.stringify({ fixture: { step: 4, best: 340 } })));
  await page.evaluate(() => { const d = window.__dbg; d.showTour(d.quests.find(q => q.id === "fixture")); });
  check((await page.$eval(".q-fly", e => e.textContent)) === "Stop de vlucht", "Dutch: 'Stop de vlucht'");
  await page.waitForFunction(() => !document.querySelector(".q-now").hidden, null, { timeout: 60000 });
  check(/^Halte \d \/ 4/.test(await page.$eval(".q-now", e => e.textContent)), "Dutch: 'Halte n / 4'");
  await page.screenshot({ path: join(shots, "5-phone-nl.png") });
  // A touch on the map hands the camera back.
  await page.touchscreen.tap(195, 700);
  await sleep(50);
  check(!(await tourOf(page)), "a touch stops the tour");
  check((await page.$eval(".q-fly", e => e.textContent)) === "Vlieg de route", "Dutch: 'Vlieg de route'");
  await ctx.close();
}

await browser.close();
if (errors.length) { console.error("page errors:\n" + errors.join("\n")); process.exit(1); }
console.log("no page errors; screenshots in", shots);
