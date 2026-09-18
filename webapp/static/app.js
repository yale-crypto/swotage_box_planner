"use strict";

/* Stowage — front-end controller.
   Talks to the existing /api/pack backend; renders the result into the
   Stowage layout (metric cards, interactive Plotly scene, inspector tabs). */

// Blank starting state — no example is packed on load.
const BLANK = {
  box: { l: "", w: "", h: "" },
  items: [
    { l: "", w: "", h: "", qty: 1 },
    { l: "", w: "", h: "", qty: 1 },
    { l: "", w: "", h: "", qty: 1 },
  ],
};
let lastResult = null;
let showFree = true;
let focusType = null;   // legend selection: id of the type to highlight, or null for all
let focusAxis = null;   // "l" | "w" | "h" — dimension to call out in the scene, or null

// Free-space (void) styling — translucent fill so items stay visible through it,
// with clear dashed outlines so each void is easy to pick out. Tweak to taste.
const FREE_FILL_OPACITY = 0.18;
const FREE_EDGE_COLOR = "#5f6b7d";
const FREE_EDGE_WIDTH = 2.4;

// Axis call-out styling. The highlight rides the container's own edges, so it
// reads as a measurement of the box rather than another item in the scene.
// `push` is the direction the dimension line is carried outside the box, as a
// multiple of the pad per axis — chosen so the call-out lands on a face the
// default camera is looking at rather than behind the load.
const AXIS_META = {
  l: { i: 0, name: "Length", input: "box-l", push: [0, 1, 0] },
  w: { i: 1, name: "Width",  input: "box-w", push: [1, 0, 0] },
  h: { i: 2, name: "Height", input: "box-h", push: [1, 0, 0] },
};
const AXIS_COLOR = "#3360d8";
const AXIS_EDGE_WIDTH = 4;     // enough to pick out an edge, not enough to shout
const AXIS_PAD = 0.11;        // call-out offset, as a fraction of the longest side

const $ = (id) => document.getElementById(id);

/* ── Item rows ──────────────────────────────────────────────────────────── */
function rowTemplate(item = { l: "", w: "", h: "", qty: 1 }) {
  const row = document.createElement("div");
  row.className = "item-row";
  row.innerHTML = `
    <span class="swatch"></span>
    <input class="num it-l" type="number" min="0.01" step="any" value="${item.l}" />
    <input class="num it-w" type="number" min="0.01" step="any" value="${item.w}" />
    <input class="num it-h" type="number" min="0.01" step="any" value="${item.h}" />
    <input class="num qty it-q" type="number" min="1" step="1" value="${item.qty}" />
    <button class="item-del" type="button" title="Remove">×</button>`;
  row.querySelector(".item-del").addEventListener("click", () => { row.remove(); recolorRows(); });
  return row;
}
function addRow(item) { $("items-body").appendChild(rowTemplate(item)); recolorRows(); }

// Preview swatches mirror the backend palette order.
// Must stay in the same order as ITEM_PALETTE in webapp/app.py.
const PALETTE = ["#3360d8", "#11968c", "#d98a2b", "#7556c9", "#2f9e44",
                 "#e03131", "#15aabf", "#e64980", "#9c6644", "#f59f00"];
function recolorRows() {
  [...$("items-body").children].forEach((row, i) => {
    row.querySelector(".swatch").style.background = PALETTE[i % PALETTE.length];
  });
}

function loadProblem(p) {
  $("box-l").value = p.box.l; $("box-w").value = p.box.w; $("box-h").value = p.box.h;
  $("items-body").innerHTML = "";
  p.items.forEach(addRow);
}
function collectProblem() {
  const box = { l: +$("box-l").value, w: +$("box-w").value, h: +$("box-h").value };
  const items = [...$("items-body").children].map((row, i) => ({
    id: String.fromCharCode(65 + i),         // A, B, C, … to match the design
    l: +row.querySelector(".it-l").value,
    w: +row.querySelector(".it-w").value,
    h: +row.querySelector(".it-h").value,
    qty: parseInt(row.querySelector(".it-q").value, 10),
  }));
  return { box, items };
}

/* ── Geometry → Plotly ──────────────────────────────────────────────────── */
const TRI_I = [0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3];
const TRI_J = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4];
const TRI_K = [2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7];
const EDGE_SEQ = [0, 1, 2, 3, 0, null, 4, 5, 6, 7, 4, null, 0, 4, null, 1, 5, null, 2, 6, null, 3, 7];

function corners(x, y, z, l, w, h) {
  return [[x, y, z], [x + l, y, z], [x + l, y + w, z], [x, y + w, z],
          [x, y, z + h], [x + l, y, z + h], [x + l, y + w, z + h], [x, y + w, z + h]];
}
function cuboidMesh(x, y, z, l, w, h, o) {
  const xs = [x, x + l, x + l, x, x, x + l, x + l, x];
  const ys = [y, y, y + w, y + w, y, y, y + w, y + w];
  const zs = [z, z, z, z, z + h, z + h, z + h, z + h];
  return {
    type: "mesh3d", x: xs, y: ys, z: zs, i: TRI_I, j: TRI_J, k: TRI_K,
    color: o.color, opacity: o.opacity, flatshading: true,
    hovertext: o.hover, hoverinfo: "text", showlegend: false,
    lighting: { ambient: 0.72, diffuse: 0.72, specular: 0.06, roughness: 0.9 },
    lightposition: { x: 900, y: 1200, z: 1600 },
  };
}
function edgeTrace(items, color, width, dash) {
  const X = [], Y = [], Z = [];
  for (const it of items) {
    const [x, y, z] = it.pos, [l, w, h] = it.size, c = corners(x, y, z, l, w, h);
    for (const idx of EDGE_SEQ) {
      if (idx === null) { X.push(null); Y.push(null); Z.push(null); }
      else { X.push(c[idx][0]); Y.push(c[idx][1]); Z.push(c[idx][2]); }
    }
    X.push(null); Y.push(null); Z.push(null);
  }
  return { type: "scatter3d", mode: "lines", x: X, y: Y, z: Z,
           line: { color, width, dash }, hoverinfo: "skip", showlegend: false };
}

const fmt = (t) => t.map((v) => +(+v).toFixed(2)).join("×");

function buildTraces(r) {
  const traces = [];
  const [bl, bw, bh] = r.summary.box;

  // container wireframe — faded while one dimension is called out, so the
  // highlighted edges are the only strong lines on the box
  traces.push(edgeTrace([{ pos: [0, 0, 0], size: [bl, bw, bh] }],
                        focusAxis ? "#d3d2ca" : "#a9aaa2", 2.5));

  // solid items — when a legend type is focused, the others go transparent
  const focusing = focusType !== null;
  for (const p of r.placements) {
    const [x, y, z] = p.position, [l, w, h] = p.orientation;
    const lit = !focusing || p.item_id === focusType;
    traces.push(cuboidMesh(x, y, z, l, w, h, {
      color: p.color, opacity: lit ? 1.0 : 0.07,
      hover: `Type ${p.item_id}<br>${fmt(p.orientation)}<br>@ (${fmt(p.position)})`,
    }));
  }
  // per-item outlines (so identical stacked items stay countable) — kept dark
  // and thick enough to read clearly against same-coloured neighbours. When
  // focusing, only outline the highlighted type so it stands out cleanly.
  const outlineSrc = focusing
    ? r.placements.filter((p) => p.item_id === focusType)
    : r.placements;
  if (outlineSrc.length) {
    traces.push(edgeTrace(
      outlineSrc.map((p) => ({ pos: p.position, size: p.orientation })),
      "#15171c", 3.5));
  }
  // free voids — slate, translucent fill + clear dashed outlines
  if (showFree) {
    for (const v of r.free_spaces) {
      const [x, y, z] = v.origin, [l, w, h] = v.size;
      traces.push(cuboidMesh(x, y, z, l, w, h, {
        color: "#8c93a0", opacity: FREE_FILL_OPACITY,
        hover: `Void<br>${fmt(v.size)}<br>@ (${fmt(v.origin)})<br>vol ${+v.volume.toFixed(2)}`,
      }));
    }
    traces.push(edgeTrace(
      r.free_spaces.map((v) => ({ pos: v.origin, size: v.size })),
      FREE_EDGE_COLOR, FREE_EDGE_WIDTH, "dash"));
  }
  if (focusAxis) traces.push(...axisHighlight(r.summary.box));
  return traces;
}

const axisPad = (box) => AXIS_PAD * Math.max(...box);

/* Call out the focused dimension two ways, because each covers the other's
   blind spot:

     · all four container edges running along that axis — shows the direction,
       but translucent voids and items can sit in front of them;
     · a dimension line carried outside the box on extension lines, the way a
       drawing marks a measurement — never occluded by the load.  */
function axisHighlight(box) {
  const meta = AXIS_META[focusAxis];
  const i = meta.i, span = box[i], pad = axisPad(box);
  const [a, b] = [0, 1, 2].filter((k) => k !== i);   // the two other axes

  // 1. the four box edges parallel to this axis
  const X = [], Y = [], Z = [];
  const seg = (p, q) => {
    for (const pt of [p, q]) { X.push(pt[0]); Y.push(pt[1]); Z.push(pt[2]); }
    X.push(null); Y.push(null); Z.push(null);
  };
  for (const offA of [0, box[a]]) {
    for (const offB of [0, box[b]]) {
      const start = [0, 0, 0];
      start[a] = offA; start[b] = offB;
      const end = start.slice();
      end[i] = span;
      seg(start, end);
    }
  }

  // 2. the dimension line, offset clear of the box, plus its extension lines
  const base = meta.push.map((m, k) => (m ? box[k] + pad : 0));
  const p0 = base.slice(), p1 = base.slice();
  p0[i] = 0; p1[i] = span;
  const corner = (p) => p.map((v, k) => (meta.push[k] ? box[k] : v));

  const DX = [], DY = [], DZ = [];
  const dseg = (p, q) => {
    for (const pt of [p, q]) { DX.push(pt[0]); DY.push(pt[1]); DZ.push(pt[2]); }
    DX.push(null); DY.push(null); DZ.push(null);
  };
  dseg(p0, p1);                 // the measurement itself
  dseg(corner(p0), p0);         // extension lines back to the box corners
  dseg(corner(p1), p1);

  return [
    { type: "scatter3d", mode: "lines", x: X, y: Y, z: Z,
      line: { color: AXIS_COLOR, width: AXIS_EDGE_WIDTH },
      hoverinfo: "skip", showlegend: false },
    { type: "scatter3d", mode: "lines+markers", x: DX, y: DY, z: DZ,
      line: { color: AXIS_COLOR, width: 2.5 },
      marker: { color: AXIS_COLOR, size: 2.5 },
      hoverinfo: "skip", showlegend: false },
  ];
}
function axis(title, max, hot, limit) {
  return {
    title: {
      text: title,
      font: { color: hot ? AXIS_COLOR : "#6c6d66", size: hot ? 17 : 15,
              family: "IBM Plex Mono" },
    },
    range: [0, limit ?? max], backgroundcolor: "rgba(0,0,0,0)", gridcolor: "#e4e3dc",
    zerolinecolor: "#d8d7cf", showbackground: false, color: "#8a8b84",
    tickfont: { size: hot ? 13 : 12, color: hot ? AXIS_COLOR : "#8a8b84" },
  };
}
function render(r) {
  if (typeof Plotly === "undefined") { showError("3-D library failed to load — reload the page."); return; }
  const [bl, bw, bh] = r.summary.box;
  // Widen the ranges the call-out is pushed into; Plotly clips to the range cube.
  const push = focusAxis ? AXIS_META[focusAxis].push : [0, 0, 0];
  const lim = [bl, bw, bh].map((v, k) => (push[k] ? v + axisPad([bl, bw, bh]) * 1.5 : v));
  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    margin: { l: 0, r: 0, t: 0, b: 0 }, showlegend: false,
    font: { family: "IBM Plex Sans" },
    scene: {
      aspectmode: "data",
      xaxis: axis("Length", bl, focusAxis === "l", lim[0]),
      yaxis: axis("Width", bw, focusAxis === "w", lim[1]),
      zaxis: axis("Height", bh, focusAxis === "h", lim[2]),
      camera: { eye: { x: 1.5, y: 1.5, z: 1.05 } },
    },
  };
  Plotly.react("plot", buildTraces(r), layout,
    { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["resetCameraDefault3d"] });
}

/* ── Result panels ──────────────────────────────────────────────────────── */
const num = (v) => (+(+v).toFixed(2)).toLocaleString();

function fillResults(r) {
  const s = r.summary;
  const totalReq = r.per_type.reduce((a, t) => a + t.requested, 0);
  const leftover = r.per_type.reduce((a, t) => a + t.leftover, 0);
  const freePct = Math.round((s.free_volume / s.box_volume) * 100);

  $("m-util").textContent = s.utilization.toFixed(1) + "%";
  $("m-util-bar").style.width = s.utilization.toFixed(1) + "%";
  $("m-placed").textContent = s.placed_count;
  $("m-leftover").textContent = leftover + " left unplaced";
  $("m-leftover").classList.toggle("muted", leftover === 0);
  $("m-leftover").classList.toggle("danger", leftover > 0);
  $("m-free").textContent = num(s.free_volume);
  $("m-free-pct").textContent = freePct + "% of container";
  $("m-voids").textContent = r.free_spaces.length;

  // A truncated search still produced a valid packing — say so rather than
  // letting a result that could have been better look definitive.
  const cut = r.search && r.search.truncated
    ? ` · search stopped at ${r.search.budget_s}s`
    : "";
  $("scene-sub").textContent =
    `${fmt(s.box)} · ${s.placed_count} of ${totalReq} items placed${cut}`;

  // legend overlay — click a row to highlight that type (others go transparent)
  const lg = $("legend-items"); lg.innerHTML = "";
  for (const t of r.per_type) {
    const row = document.createElement("div");
    row.className = "legend-row";
    row.dataset.type = t.id;
    row.title = "Click to highlight this type";
    row.innerHTML = `<span class="swatch" style="background:${t.color}"></span>
      <span class="lg-id">Type ${t.id}</span>
      <span class="lg-size">${fmt(t.size)}</span>`;
    row.addEventListener("click", () => toggleFocus(t.id));
    lg.appendChild(row);
  }
  applyLegendFocus();
  $("legend").hidden = r.per_type.length === 0;

  // inspector: type cards
  const tc = $("type-cards"); tc.innerHTML = "";
  for (const t of r.per_type) {
    const pct = Math.round((t.packed / t.requested) * 100) || 0;
    let cls = "partial", txt = `${t.leftover} unplaced`;
    if (t.leftover === 0) { cls = "complete"; txt = "Complete"; }
    else if (t.packed === 0) { cls = "none"; txt = "None placed"; }
    const card = document.createElement("div");
    card.className = "type-card";
    card.innerHTML = `
      <div class="tc-head">
        <span class="swatch" style="background:${t.color}"></span>
        <span class="tc-id">Type ${t.id}</span>
        <span class="tc-size">${fmt(t.size)}</span>
        <span class="badge ${cls}">${txt}</span>
      </div>
      <div class="row-bar"><div class="bar-fill" style="width:${pct}%;background:${t.color}"></div></div>
      <div class="tc-foot"><span><b>${t.packed}</b> / ${t.requested} packed</span><span>${t.leftover} leftover</span></div>`;
    tc.appendChild(card);
  }

  // inspector: void cards
  const vc = $("void-cards"); vc.innerHTML = "";
  if (!r.free_spaces.length) {
    vc.innerHTML = `<p class="hint">No open voids — container completely filled.</p>`;
  }
  const maxVol = Math.max(1, ...r.free_spaces.map((v) => v.volume));
  r.free_spaces.forEach((v, i) => {
    const card = document.createElement("div");
    card.className = "void-card";
    card.innerHTML = `
      <div class="vc-head">
        <span class="vc-id"><span class="swatch"></span>Void ${i + 1}</span>
        <span class="vc-vol"><b>${num(v.volume)}</b></span>
      </div>
      <div class="row-bar thin"><div class="bar-fill" style="width:${Math.round(v.volume / maxVol * 100)}%;background:#8c93a0"></div></div>
      <div class="vc-foot"><span>origin (${fmt(v.origin)})</span><span>${fmt(v.size)}</span></div>`;
    vc.appendChild(card);
  });

  // inspector: log
  const lr = $("log-rows"); lr.innerHTML = "";
  r.log.forEach((line, i) => {
    const skip = /\bSKIP\b/.test(line);
    const text = line.replace(/^\[\s*\d+\]\s*/, "");   // drop the [ N] prefix
    const row = document.createElement("div");
    row.className = "log-row" + (skip ? " skip" : "");
    row.innerHTML = `<span class="ln">${String(i + 1).padStart(2, "0")}</span><span class="tx">${escapeHtml(text)}</span>`;
    lr.appendChild(row);
  });
}
function escapeHtml(s) { return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

// Legend focus: click a type to highlight it; click it again to show all.
function toggleFocus(id) {
  focusType = focusType === id ? null : id;
  applyLegendFocus();
  if (lastResult) render(lastResult);
}
function applyLegendFocus() {
  document.querySelectorAll("#legend-items .legend-row").forEach((row) => {
    const active = focusType === null || row.dataset.type === focusType;
    row.classList.toggle("dim", !active);
    row.classList.toggle("active", focusType !== null && active);
  });
}

// Axis focus: click Length / Width / Height to call that dimension out on the
// container; click the same one again to clear it.
function toggleAxis(key) {
  focusAxis = focusAxis === key ? null : key;
  applyAxisFocus();
  if (lastResult) render(lastResult);
}
function applyAxisFocus() {
  document.querySelectorAll("[data-axis]").forEach((el) => {
    el.setAttribute("aria-pressed", String(el.dataset.axis === focusAxis));
  });
  for (const [key, meta] of Object.entries(AXIS_META)) {
    $(meta.input).classList.toggle("axis-hot", key === focusAxis);
  }
}

function updateBoxVol() {
  const v = (+$("box-l").value) * (+$("box-w").value) * (+$("box-h").value);
  $("box-vol").textContent = Number.isFinite(v) && v > 0 ? num(v) : "—";
}

/* ── Pack ───────────────────────────────────────────────────────────────── */
async function pack() {
  showError(null);
  $("spinner").hidden = false;
  try {
    const res = await fetch("/api/pack", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectProblem()),
    });
    const data = await res.json();
    if (!data.ok) { showError(data.error || "Packing failed."); return; }
    lastResult = data;
    focusType = null;   // fresh result shows every type
    $("placeholder").hidden = true;
    $("btn-png").disabled = false;
    $("btn-report").disabled = false;
    render(data);
    fillResults(data);
  } catch (err) {
    showError("Could not reach the server: " + err.message);
  } finally {
    $("spinner").hidden = true;
  }
}
function showError(msg) {
  const el = $("error");
  if (!msg) { el.hidden = true; el.textContent = ""; return; }
  el.hidden = false; el.textContent = msg;
}

// Return the scene + panels to the empty state (no result shown).
function clearResults() {
  lastResult = null;
  focusType = null;
  focusAxis = null;
  applyAxisFocus();
  $("btn-png").disabled = true;
  $("btn-report").disabled = true;
  $("legend").hidden = true;
  $("placeholder").hidden = false;
  if (typeof Plotly !== "undefined") Plotly.purge("plot");
  ["m-util", "m-placed", "m-free", "m-voids"].forEach((id) => ($(id).textContent = "—"));
  $("m-util-bar").style.width = "0%";
  $("m-leftover").textContent = "—";
  $("m-free-pct").textContent = "—";
  $("scene-sub").textContent = "—";
  $("type-cards").innerHTML = "";
  $("void-cards").innerHTML = "";
  $("log-rows").innerHTML = "";
}

/* ── Exports / actions ──────────────────────────────────────────────────── */
function exportPng() {
  Plotly.downloadImage("plot", { format: "png", width: 1500, height: 1000, filename: "stowage-plan" });
}
function downloadReport() {
  if (!lastResult) return;
  download(lastResult.report, "stowage-report.txt", "text/plain");
}
function savePlan() {
  const plan = { problem: collectProblem(), result: lastResult || null };
  download(JSON.stringify(plan, null, 2), "stowage-plan.json", "application/json");
}

// Load a previously saved plan (same JSON shape savePlan produces) and re-pack.
function importPlan(file) {
  const reader = new FileReader();
  reader.onerror = () => showError("Couldn't read that file.");
  reader.onload = () => {
    let data;
    try {
      data = JSON.parse(reader.result);
    } catch (e) {
      showError("That file isn't valid JSON.");
      return;
    }
    const problem = data && (data.problem || data);   // accept {problem,…} or a bare problem
    if (!problem || !problem.box || !Array.isArray(problem.items) || !problem.items.length) {
      showError("Plan JSON needs a 'box' and a non-empty 'items' list.");
      return;
    }
    loadProblem({
      box: { l: problem.box.l, w: problem.box.w, h: problem.box.h },
      items: problem.items.map((it) => ({ l: it.l, w: it.w, h: it.h, qty: it.qty ?? 1 })),
    });
    updateBoxVol();
    showError(null);
    pack();   // recompute from the imported inputs (always consistent)
  };
  reader.readAsText(file);
}
function download(content, name, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}
function resetView() {
  if (lastResult) Plotly.relayout("plot", { "scene.camera.eye": { x: 1.5, y: 1.5, z: 1.05 } });
}

/* ── Wiring ─────────────────────────────────────────────────────────────── */
function init() {
  loadProblem(BLANK);
  updateBoxVol();

  $("btn-add").addEventListener("click", () => addRow());
  $("btn-pack").addEventListener("click", pack);
  $("btn-reset").addEventListener("click", () => { loadProblem(BLANK); updateBoxVol(); clearResults(); });
  $("btn-save").addEventListener("click", savePlan);
  $("btn-import").addEventListener("click", () => $("file-import").click());
  $("file-import").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) importPlan(file);
    e.target.value = "";   // allow re-importing the same file
  });
  $("btn-png").addEventListener("click", exportPng);
  $("btn-report").addEventListener("click", downloadReport);
  $("btn-resetview").addEventListener("click", resetView);

  ["box-l", "box-w", "box-h"].forEach((id) => $(id).addEventListener("input", updateBoxVol));

  // Both the container labels and the scene chips drive the same call-out.
  document.querySelectorAll("[data-axis]").forEach((el) => {
    el.addEventListener("click", () => toggleAxis(el.dataset.axis));
  });

  $("toggle-free").addEventListener("click", () => {
    showFree = !showFree;
    $("toggle-free").setAttribute("aria-pressed", String(showFree));
    if (lastResult) render(lastResult);
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.querySelector(`.tab-panel[data-panel="${tab.dataset.tab}"]`).classList.add("active");
    });
  });
  // No auto-pack: start on the empty placeholder until the user clicks Pack.
}
document.addEventListener("DOMContentLoaded", init);
