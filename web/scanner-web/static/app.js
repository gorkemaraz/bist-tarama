const $ = (id) => document.getElementById(id);
const statusEl = $("status");
const tbody = $("tbody");

const fmtNum = (v, d = 2) => v == null ? "-" : v.toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtInt = (v) => v == null ? "-" : v.toLocaleString("tr-TR");
const fmtPct = (v) => v == null ? "-" : `${v > 0 ? "+" : ""}${fmtNum(v)}%`;
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const DIRECTION = { up: ["Yükseliş", "up"], down: ["Düşüş", "down"], neutral: ["Nötr", "neutral"] };
const DIR_SIGN = { up: 1, down: -1, neutral: 1 };
const ISSUE_LABELS = {
  close_filled: "Kapanış İş Yatırım'dan tamamlandı",
  close_approx: "Kapanış saatlik veriden tahmin edildi",
  source_mismatch: "Yahoo ve İş Yatırım farklı",
  limit_exceeded: "Fiyat marjını aşan hareket",
  ohlc_inconsistent: "Tutarsız OHLC düzeltildi",
  no_close: "Kapanışı olmayan satır atlandı",
  no_data: "Veri gelmeyen sembol",
};

let scans = {};
let filters = {};               // id -> {title, group}
const active = new Set();       // seçili filtre id'leri
let currentScan = null;
let btView = null;              // açık backtest görünümü: {type: "scan", id} | {type: "board", horizon}
let results = [];
let sort = { key: null, dir: -1 };

function setStatus(t) { statusEl.textContent = t || ""; }
async function getJSON(url, opts) {
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Hata");
  return data;
}
const filterQuery = () => [...active].join(",");
const filterSuffix = () => active.size ? " + " + [...active].map((f) => filters[f].title).join(" + ") : "";

// ---- Taramalar ----
async function loadScans() {
  const data = await getJSON("/api/scans");
  const groups = {};
  for (const s of data.scans) {
    scans[s.id] = s;
    (groups[s.category] ??= []).push(s);
  }
  $("scanGroups").innerHTML = Object.entries(groups).map(([cat, items]) => `
    <div class="scanCat">${esc(cat)}</div>
    ${items.map(scanItem).join("")}`).join("");
}

function dirBadge(direction) {
  const [label, cls] = DIRECTION[direction] ?? DIRECTION.neutral;
  return `<span class="badge ${cls}">${label}</span>`;
}

function scanItem(s) {
  const [label, cls] = DIRECTION[s.direction] ?? DIRECTION.neutral;
  return `
    <div class="scanItem" data-scan="${s.id}">
      <button class="scanRun" data-run="${s.id}" title="${esc(s.description)}">
        <i class="dot ${cls}" title="${label}"></i><span>${esc(s.title)}</span>
      </button>
      <button class="btMini" data-bt="${s.id}" title="Backtest">BT</button>
    </div>`;
}

$("scanGroups").addEventListener("click", (e) => {
  const run = e.target.closest("button[data-run]");
  if (run) return runScan(run.dataset.run, run);
  const bt = e.target.closest("button[data-bt]");
  if (bt) return showBacktest(bt.dataset.bt);
});

async function runScan(id, btn, scroll = true) {
  currentScan = id;
  document.querySelectorAll(".scanItem").forEach((el) => el.classList.toggle("active", el.dataset.scan === id));
  $("resultsTitle").textContent = `${scans[id].title}${filterSuffix()}`;
  $("scanDesc").textContent = scans[id].description;
  $("scanDesc").hidden = !scans[id].description;
  setStatus("Çalışıyor…");
  if (btn) btn.disabled = true;
  try {
    const data = await getJSON(`/api/run/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days: Number($("days").value), filters: [...active] }),
    });
    results = data.results;
    sort = { key: null, dir: -1 };
    renderRows();
    setStatus(`${data.count} hisse`);
    if (results.length) showChart(results[0].symbol);
    else hideChart();
    // geniş ekranda sonuçlar ve grafik zaten görünür; sadece dar ekranda kaydır
    if (scroll && window.innerWidth <= 760) $("resultsTitle").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setStatus("Hata: " + err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ---- Filtreler ----
async function loadFilters() {
  const data = await getJSON("/api/filters");
  for (const f of data.filters) filters[f.id] = f;
  renderFilters();
}

function renderFilters() {
  $("filterBar").innerHTML = Object.values(filters).map((f) =>
    `<button class="chip ${active.has(f.id) ? "on" : ""}" data-filter="${f.id}">${esc(f.title)}</button>`).join("");
  $("clearFilters").hidden = active.size === 0;
}

function toggleFilter(id, on = !active.has(id)) {
  if (on) {
    // aynı gruptaki filtreler birbirini dışlar (ör. Fiyat > EMA50 / Fiyat < EMA50)
    for (const other of [...active]) if (filters[other].group === filters[id].group) active.delete(other);
    active.add(id);
  } else {
    active.delete(id);
  }
  renderFilters();
  refreshViews();
}

function refreshViews() {
  if (currentScan) runScan(currentScan, null, false);
  if (btView?.type === "scan") showBacktest(btView.id, false);
  if (btView?.type === "board") showLeaderboard(btView.horizon, false);
}

$("filterBar").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-filter]");
  if (chip) toggleFilter(chip.dataset.filter);
});
$("clearFilters").addEventListener("click", () => {
  active.clear();
  renderFilters();
  refreshViews();
});

// ---- Sonuç tablosu ----
function renderRows() {
  const rows = [...results];
  if (sort.key) {
    rows.sort((a, b) => {
      const x = a[sort.key], y = b[sort.key];
      return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
    });
  }
  document.querySelectorAll("th[data-key]").forEach((th) => {
    th.dataset.sort = th.dataset.key === sort.key ? (sort.dir > 0 ? "asc" : "desc") : "";
  });
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="muted">Bu pencerede sinyal yok.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((r) => `
    <tr data-symbol="${esc(r.symbol)}" class="clickable ${r.symbol === chartSymbol ? "selected" : ""}"
        title="Hacim: ${fmtInt(r.volume)} · Son fiyat: ${fmtNum(r.last_close)}">
      <td class="sym">${esc(r.symbol)}</td>
      <td>${esc(r.date)}</td>
      <td class="num">${fmtNum(r.close)}</td>
      <td class="num ${r.change_pct > 0 ? "pos" : r.change_pct < 0 ? "neg" : ""}">${fmtPct(r.change_pct)}</td>
      <td class="num ${r.rel_volume >= 2 ? "hot" : ""}">${r.rel_volume == null ? "-" : fmtNum(r.rel_volume) + "x"}</td>
    </tr>`).join("");
}

// ↑ ↓ ile sonuçlar arasında gezinme
document.addEventListener("keydown", (e) => {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  if (e.target.closest("input, select, textarea")) return;
  const trs = [...tbody.querySelectorAll("tr[data-symbol]")];
  if (!trs.length) return;
  e.preventDefault();
  const i = trs.findIndex((tr) => tr.dataset.symbol === chartSymbol);
  const next = trs[Math.max(0, Math.min(trs.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
  next.scrollIntoView({ block: "nearest" });
  showChart(next.dataset.symbol);
});

document.querySelector("thead").addEventListener("click", (e) => {
  const th = e.target.closest("th[data-key]");
  if (!th) return;
  sort = { key: th.dataset.key, dir: sort.key === th.dataset.key ? -sort.dir : -1 };
  renderRows();
});

tbody.addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-symbol]");
  if (tr) showChart(tr.dataset.symbol);
});

// ---- Grafik ----
const COLORS = { up: "#22c55e", down: "#ef4444", ema20: "#3b82f6", ema50: "#f59e0b", signal: "#e8eef5", grid: "#1a2330", border: "#1f2a3a", text: "#8a97a8" };
const VISIBLE_BARS = 130;
let chart, candles, volume, ema20, ema50, chartSymbol = null;

function ensureChart() {
  if (chart) return;
  chart = LightweightCharts.createChart($("chart"), {
    autoSize: true,
    layout: { background: { color: "transparent" }, textColor: COLORS.text },
    grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
    rightPriceScale: { borderColor: COLORS.border, scaleMargins: { top: 0.05, bottom: 0.25 } },
    timeScale: { borderColor: COLORS.border },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    localization: { locale: "tr-TR" },
  });
  candles = chart.addCandlestickSeries({
    upColor: COLORS.up, downColor: COLORS.down, borderVisible: false,
    wickUpColor: COLORS.up, wickDownColor: COLORS.down,
  });
  const line = { lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
  ema20 = chart.addLineSeries({ ...line, color: COLORS.ema20 });
  ema50 = chart.addLineSeries({ ...line, color: COLORS.ema50 });
  volume = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
  chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
}

async function showChart(symbol) {
  chartSymbol = symbol;
  document.querySelectorAll("tr[data-symbol]").forEach((tr) => tr.classList.toggle("selected", tr.dataset.symbol === symbol));
  $("chartEmpty").hidden = true;
  $("chartTitle").textContent = `${symbol} yükleniyor…`;
  ensureChart();

  const q = currentScan ? `?scan_id=${currentScan}&filters=${filterQuery()}` : "";
  const d = await getJSON(`/api/chart/${encodeURIComponent(symbol)}${q}`);
  if (symbol !== chartSymbol) return; // bu sırada başka satıra tıklandı

  candles.setData(d.candles);
  ema20.setData(d.ema20);
  ema50.setData(d.ema50);
  volume.setData(d.volume.map((v) => ({ time: v.time, value: v.value, color: (v.up ? COLORS.up : COLORS.down) + "55" })));
  const down = d.direction === "down";
  candles.setMarkers(d.signals.map((t) => ({
    time: t,
    position: down ? "aboveBar" : "belowBar",
    shape: d.direction === "up" ? "arrowUp" : down ? "arrowDown" : "circle",
    color: d.direction === "up" ? COLORS.up : down ? COLORS.down : COLORS.signal,
  })));
  const n = d.candles.length;
  chart.timeScale().setVisibleLogicalRange({ from: n - VISIBLE_BARS, to: n + 3 });

  const last = d.candles.at(-1);
  const scanTitle = currentScan ? ` · ${scans[currentScan].title}${filterSuffix()}` : "";
  $("chartTitle").textContent = `${symbol}${scanTitle} · ${fmtNum(last.close)} (${last.time}) · son 250 günde ${d.signals.length} sinyal`;
}

function hideChart() {
  chartSymbol = null;
  $("chartTitle").textContent = "Grafik";
  $("chartEmpty").textContent = "Bu taramada sinyal yok.";
  $("chartEmpty").hidden = false;
}

// ---- Backtest ----
const goodClass = (v, direction) => {
  const s = (v ?? 0) * DIR_SIGN[direction];
  return s > 0 ? "pos" : s < 0 ? "neg" : "";
};

function verdict(st, direction) {
  if (!st || !st.n) return "Bu kombinasyon geçmişte hiç sinyal üretmemiş.";
  if (direction === "neutral") return "Yönsüz (kararsızlık) formasyonu: tek başına al/sat sinyali değil, sonuçlar bilgi amaçlı.";
  if (st.n < 30) return `Sadece ${st.n} işlem var; sonuç çıkarmak için örneklem çok küçük.`;
  const s = st.edge * DIR_SIGN[direction];
  const strong = Math.abs(st.t_stat ?? 0) >= 2;
  const consistency = st.consistent ? " İlk ve son dönemde de beklenen yönde, tutarlı." : " Ancak dönemler arasında tutarlı değil; dikkatli ol.";
  if (s > 0 && strong) return `5 günlük vadede piyasa ortalamasından anlamlı şekilde iyi (fark ${fmtPct(st.edge)}, t=${fmtNum(st.t_stat)}).${consistency}`;
  if (s < 0 && strong) return `5 günlük vadede beklenen yönün tersine, piyasa ortalamasından anlamlı şekilde kötü (fark ${fmtPct(st.edge)}). Bu haliyle kullanılmamalı.`;
  if (s > 0 && st.consistent) return `Fark beklenen yönde ve iki dönemde de tutarlı (${fmtPct(st.edge)}), ama istatistiksel olarak henüz güçlü değil (t=${fmtNum(st.t_stat)}).`;
  return `5 günlük vadede piyasa ortalamasından istatistiksel olarak ayırt edilemiyor (fark ${fmtPct(st.edge)}).`;
}

const STAT_HEAD = `<th class="num">İşlem</th><th class="num">İsabet</th><th class="num">Ort. Getiri</th><th class="num">Medyan</th><th class="num">Piyasa Ort.</th><th class="num">Fark</th><th class="num">t</th><th class="num" title="Farkın verinin ilk %60'ı ve son %40'ındaki değeri">İlk / Son dönem</th>`;
const STAT_COLS = 8;

function splitCell(st, direction) {
  if (st.edge_early === undefined) return `<td class="num muted">-</td>`;
  const part = (v) => v == null ? "-" : `<span class="${goodClass(v, direction)}">${fmtPct(v)}</span>`;
  return `<td class="num">${part(st.edge_early)} / ${part(st.edge_late)} ${st.consistent ? '<span class="ok" title="İki dönemde de beklenen yönde">✓</span>' : '<span class="muted">✗</span>'}</td>`;
}

function statCells(st, direction) {
  if (!st || !st.n) return `<td class="num">0</td><td colspan="${STAT_COLS - 1}" class="muted">sinyal yok</td>`;
  return `
    <td class="num ${st.n < 30 ? "muted" : ""}">${fmtInt(st.n)}</td>
    <td class="num">${fmtNum(st.hit_rate, 1)}%</td>
    <td class="num ${st.mean > 0 ? "pos" : st.mean < 0 ? "neg" : ""}">${fmtPct(st.mean)}</td>
    <td class="num">${fmtPct(st.median)}</td>
    <td class="num muted">${fmtPct(st.baseline)}</td>
    <td class="num ${goodClass(st.edge, direction)}"><b>${fmtPct(st.edge)}</b></td>
    <td class="num ${Math.abs(st.t_stat ?? 0) >= 2 ? "" : "muted"}">${st.t_stat == null ? "-" : fmtNum(st.t_stat)}</td>
    ${splitCell(st, direction)}`;
}

function openBtSection(title, scroll) {
  $("btSection").hidden = false;
  $("btTitle").innerHTML = title;
  $("btControls").innerHTML = "";
  $("btBody").innerHTML = `<p class="muted">Hesaplanıyor… (ilk seferde birkaç saniye sürer)</p>`;
  if (scroll) $("btSection").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function showBacktest(id, scroll = true) {
  btView = { type: "scan", id };
  const s = scans[id];
  openBtSection(`Backtest · ${esc(s.title + filterSuffix())} ${dirBadge(s.direction)}`, scroll);
  try {
    const q = `filters=${filterQuery()}`;
    const [d, fa] = await Promise.all([
      getJSON(`/api/backtest/${id}?${q}`),
      getJSON(`/api/backtest/${id}/filters?${q}`),
    ]);
    if (btView?.type !== "scan" || btView.id !== id) return;
    const years = Object.entries(d.by_year_5d);
    $("btBody").innerHTML = `
      <p class="verdict">${esc(verdict(d.horizons["5"], d.direction))}</p>
      <p class="muted small">${d.symbols} hisse · ${d.period[0]} – ${d.period[1]} · dönem ayrımı ${d.split_date}</p>
      <div class="tableWrap"><table>
        <thead><tr><th>Vade</th>${STAT_HEAD}</tr></thead>
        <tbody>${Object.entries(d.horizons).map(([h, st]) => `<tr><td>${h} gün</td>${statCells(st, d.direction)}</tr>`).join("")}</tbody>
      </table></div>

      <h3>Filtre analizi <span class="muted small">— bu kombinasyona bir filtre daha eklenirse (5 gün vade). Satıra tıkla → filtreyi ekle.</span></h3>
      <div class="tableWrap"><table>
        <thead><tr><th>Eklenen filtre</th>${STAT_HEAD}</tr></thead>
        <tbody>
          <tr class="baseRow"><td><i>Mevcut hali</i></td>${statCells(fa.base, d.direction)}</tr>
          ${fa.rows.map((r) => `<tr class="clickable" data-add-filter="${r.filter}"><td>+ ${esc(r.title)}</td>${statCells(r, d.direction)}</tr>`).join("")
            || `<tr><td colspan="${STAT_COLS + 1}" class="muted">Eklenebilecek filtre kalmadı.</td></tr>`}
        </tbody>
      </table></div>

      <h3>Yıllara göre (5 gün vade)</h3>
      <div class="tableWrap"><table>
        <thead><tr><th>Yıl</th>${STAT_HEAD}</tr></thead>
        <tbody>${years.map(([y, st]) => `<tr><td>${y}</td>${statCells(st, d.direction)}</tr>`).join("") || `<tr><td colspan="${STAT_COLS + 1}" class="muted">sinyal yok</td></tr>`}</tbody>
      </table></div>`;
  } catch (err) {
    $("btBody").innerHTML = `<p class="neg">Hata: ${esc(err.message)}</p>`;
  }
}

async function showLeaderboard(horizon = 5, scroll = true) {
  btView = { type: "board", horizon };
  openBtSection(`Formasyon Karnesi${esc(filterSuffix())}`, scroll);
  $("btControls").innerHTML = `
    <label class="muted">Vade <select id="lbHorizon">
      ${[1, 5, 10, 20].map((h) => `<option value="${h}" ${h === horizon ? "selected" : ""}>${h} gün</option>`).join("")}
    </select></label>`;
  $("lbHorizon").addEventListener("change", (e) => showLeaderboard(Number(e.target.value), false));
  try {
    const d = await getJSON(`/api/backtest?horizon=${horizon}&filters=${filterQuery()}`);
    if (btView?.type !== "board") return;
    $("btBody").innerHTML = `
      <p class="muted small">${d.symbols} hisse · ${d.period[0]} – ${d.period[1]} · ${horizon} gün vade · beklenen yönde en iyi farktan en kötüye sıralı (30'dan az işlem sonda). Satıra tıkla → detay.</p>
      <div class="tableWrap"><table>
        <thead><tr><th>Tarama</th><th>Yön</th>${STAT_HEAD}</tr></thead>
        <tbody>${d.rows.map((r) => `
          <tr class="clickable" data-bt-row="${r.scan}">
            <td class="sym">${esc(r.title)}</td><td>${dirBadge(r.direction)}</td>${statCells(r, r.direction)}
          </tr>`).join("")}</tbody>
      </table></div>`;
  } catch (err) {
    $("btBody").innerHTML = `<p class="neg">Hata: ${esc(err.message)}</p>`;
  }
}

$("leaderBtn").addEventListener("click", () => showLeaderboard(5));
$("btClose").addEventListener("click", () => {
  btView = null;
  $("btSection").hidden = true;
});
$("btBody").addEventListener("click", (e) => {
  const row = e.target.closest("tr[data-bt-row]");
  if (row) return showBacktest(row.dataset.btRow);
  const add = e.target.closest("tr[data-add-filter]");
  if (add) toggleFilter(add.dataset.addFilter, true);
});

// ---- Veri durumu ve güncelleme ----
async function loadStatus() {
  const s = await getJSON("/api/status");
  const updated = s.last_update ? new Date(s.last_update).toLocaleString("tr-TR") : "hiç";
  $("dataInfo").innerHTML = s.symbols
    ? `<b>${s.symbols}</b> hisse · son mum <b>${esc(s.latest_date)}</b><br>güncelleme: ${updated}`
    : "Veri yok. Güncelle butonuna bas.";

  const job = s.job;
  $("updateBtn").disabled = job.running;
  $("updateBtn").textContent = job.running ? "Güncelleniyor…" : "Veriyi Güncelle";
  $("updateLog").textContent = job.error ? "Hata: " + job.error : (job.log.at(-1) ?? "");
  if (job.running) setTimeout(loadStatus, 2000);
  else loadIssues();
}

$("updateBtn").addEventListener("click", async () => {
  await fetch("/api/update", { method: "POST" });
  loadStatus();
});

async function loadIssues() {
  const { issues } = await getJSON("/api/issues");
  $("issueCount").textContent = issues.length ? `(${issues.length})` : "(temiz)";
  const byKind = {};
  for (const i of issues) (byKind[i.kind] ??= []).push(i);
  $("issueBody").innerHTML = Object.entries(byKind).map(([kind, list]) => `
    <details class="issueGroup">
      <summary>${esc(ISSUE_LABELS[kind] ?? kind)} <span class="muted">(${list.length})</span></summary>
      <ul>${list.map((i) => `<li><b>${esc(i.symbol)}</b> ${esc(i.date ?? "")} <span class="muted">${esc(i.detail)}</span></li>`).join("")}</ul>
    </details>`).join("") || `<p class="muted">Son güncellemede sorun bulunmadı.</p>`;
}

loadScans();
loadFilters();
loadStatus();
