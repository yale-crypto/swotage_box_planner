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
const PALETTE = ["#3360d8", "#11968c", "#d98a2b", "#7556c9", "#2f9e44",
                 "#e8590c", "#c2255c", "#1098ad", "#5c7cfa", "#f08c00"];
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

  // container wireframe
  traces.push(edgeTrace([{ pos: [0, 0, 0], size: [bl, bw, bh] }], "#a9aaa2", 2.5));

  // solid items
  for (const p of r.placements) {
    const [x, y, z] = p.position, [l, w, h] = p.orientation;
    traces.push(cuboidMesh(x, y, z, l, w, h, {
      color: p.color, opacity: 1.0,
      hover: `Type ${p.item_id}<br>${fmt(p.orientation)}<br>@ (${fmt(p.position)})`,
    }));
  }
  // per-item outlines (so identical stacked items stay countable) — kept dark
  // and thick enough to read clearly against same-coloured neighbours.
  if (r.placements.length) {
    traces.push(edgeTrace(
      r.placements.map((p) => ({ pos: p.position, size: p.orientation })),
      "#15171c", 3.5));
  }
  // free voids — slate, translucent, dashed
  if (showFree) {
    for (const v of r.free_spaces) {
      const [x, y, z] = v.origin, [l, w, h] = v.size;
      traces.push(cuboidMesh(x, y, z, l, w, h, {
        color: "#8c93a0", opacity: 0.12,
        hover: `Void<br>${fmt(v.size)}<br>@ (${fmt(v.origin)})<br>vol ${+v.volume.toFixed(2)}`,
      }));
    }
    traces.push(edgeTrace(
      r.free_spaces.map((v) => ({ pos: v.origin, size: v.size })),
      "#7b8290", 1.5, "dash"));
  }
  return traces;
}
function axis(title, max) {
  return {
    title: { text: title, font: { color: "#9a9b93", size: 11, family: "IBM Plex Mono" } },
    range: [0, max], backgroundcolor: "rgba(0,0,0,0)", gridcolor: "#e4e3dc",
    zerolinecolor: "#d8d7cf", showbackground: false, color: "#a8a99f",
    tickfont: { size: 9, color: "#b9b9b0" },
  };
}
function render(r) {
  if (typeof Plotly === "undefined") { showError("3-D library failed to load — reload the page."); return; }
  const [bl, bw, bh] = r.summary.box;
  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    margin: { l: 0, r: 0, t: 0, b: 0 }, showlegend: false,
    font: { family: "IBM Plex Sans" },
    scene: {
      aspectmode: "data",
      xaxis: axis("Length", bl), yaxis: axis("Width", bw), zaxis: axis("Height", bh),
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

  $("scene-sub").textContent =
    `${fmt(s.box)} · ${s.placed_count} of ${totalReq} items placed`;

  // legend overlay
  const lg = $("legend-items"); lg.innerHTML = "";
  for (const t of r.per_type) {
    const row = document.createElement("div");
    row.className = "legend-row";
    row.innerHTML = `<span class="swatch" style="background:${t.color}"></span>
      <span class="lg-id">Type ${t.id}</span>
      <span class="lg-size">${fmt(t.size)}</span>`;
    lg.appendChild(row);
  }
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
