"use strict";
const $ = (id) => document.getElementById(id);
const state = { topic: "Teknologi", granularity: "monthly", demo: true, request: 0, busy: false, data: null };
const NS = "http://www.w3.org/2000/svg";
const number = (value) => new Intl.NumberFormat("id-ID").format(value);
const dateLabel = (value, period = state.granularity) => {
  const options = { timeZone: "Asia/Jakarta" };
  if (period === "yearly") options.year = "numeric";
  else if (period === "monthly") Object.assign(options, { month: "short", year: "numeric" });
  else if (period === "hours") Object.assign(options, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  else Object.assign(options, { day: "numeric", month: "short", year: "numeric" });
  return new Intl.DateTimeFormat("id-ID", options).format(new Date(value));
};
function svg(tag, attributes = {}, text) {
  const node = document.createElementNS(NS, tag);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text !== undefined) node.textContent = text;
  return node;
}
function empty(container, title, message) {
  container.replaceChildren();
  const node = document.createElement("div"); node.className = "empty";
  const strong = document.createElement("strong"); strong.textContent = title;
  const detail = document.createElement("span"); detail.textContent = message;
  node.append(strong, detail); container.append(node);
}
function status(message, error = false) {
  $("status").hidden = false;
  $("status").classList.toggle("error", error);
  $("status").textContent = message;
}
async function api(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { "X-TopicLens-Token": document.querySelector('meta[name="topiclens-token"]').content, ...(options.headers || {}) } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Permintaan gagal. Coba lagi.");
  return data;
}
function currentTopic() {
  const value = $("topic").value.trim().replace(/\s+/g, " ");
  if (value.length < 2 || value.length > 80) throw new Error("Masukkan topik dengan 2–80 karakter.");
  return value;
}
async function load() {
  const sequence = ++state.request;
  $("active-topic").textContent = state.topic;
  $("demo-banner").hidden = !state.demo;
  $("data-badge").textContent = state.demo ? "DEMO" : "DATA LOKAL";
  $("demo").checked = state.demo;
  document.querySelectorAll("[data-period]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.period === state.granularity)));
  $("trend-chart").classList.add("loading");
  try {
    const params = new URLSearchParams({ topic: state.topic, granularity: state.granularity, demo: state.demo ? "1" : "0" });
    const data = await api(`/api/analysis?${params}`);
    if (sequence !== state.request) return;
    state.data = data;
    render(data);
  } catch (error) {
    if (sequence === state.request) {
      state.data = null;
      ["metric-total", "metric-sources", "metric-peak", "metric-coverage"].forEach(id => $(id).textContent = "—");
      empty($("trend-chart"), "Analisis tidak dapat dimuat", "Periksa koneksi ke server Python.");
      empty($("word-cloud"), "Data tidak tersedia", "Muat ulang analisis untuk mencoba lagi.");
      $("top-words").replaceChildren(); $("articles-body").replaceChildren(); $("series-body").replaceChildren();
      status(error.message, true);
    }
  } finally { if (sequence === state.request) $("trend-chart").classList.remove("loading"); }
}
function render(data) {
  $("date-range").textContent = `${dateLabel(data.start, "daily")} — ${dateLabel(data.end, "daily")} · WIB`;
  $("metric-total").textContent = number(data.total);
  $("metric-stored").textContent = `${number(data.stored)} artikel tersimpan${data.demo ? " (simulasi)" : " untuk topik ini"}`;
  $("metric-sources").textContent = number(data.sources);
  $("metric-peak").textContent = data.peak ? dateLabel(data.peak.date) : "—";
  $("peak-count").textContent = data.peak ? `${number(data.peak.count)} artikel · puncak sampel` : "Belum ada data pada periode ini";
  $("metric-coverage").textContent = number(data.observed_buckets);
  $("coverage-count").textContent = `dari ${number(data.total_buckets)} interval kalender`;
  $("chart-unit").textContent = ({yearly: "Per tahun · 5 tahun terakhir", monthly: "Per bulan · 5 tahun terakhir", daily: "Per hari · 5 tahun terakhir", hours: "Per 10 menit · 5 jam terakhir"})[state.granularity];
  $("chart-note").textContent = "Interval kosong = belum ada data dalam sampel. Interval pertama/terakhir dapat berupa periode parsial.";
  $("quality-note").textContent = `${number(data.unknown_dates)} artikel tersimpan tanpa tanggal terbit, dikecualikan dari grafik. Data dengan tanggal saja tidak masuk tampilan 5 jam. Tanpa zona waktu, tanggal impor dianggap WIB.`;
  chart(data.series);
  cloud(data.words);
  wordList(data.words);
  articles(data.articles);
  $("series-body").replaceChildren();
  const fragment = document.createDocumentFragment();
  data.series.forEach(point => {
    const row = document.createElement("tr");
    [dateLabel(point.date), point.count === null ? "Belum ada data" : number(point.count)].forEach(value => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); });
    fragment.append(row);
  });
  $("series-body").append(fragment);
}
function chart(series) {
  const container = $("trend-chart"); container.replaceChildren();
  if (!series.some(point => point.count !== null)) {
    empty(container, "Belum ada artikel pada periode ini", "Mulai crawling, impor arsip bertanggal, atau coba Mode demo."); return;
  }
  const width = Math.max(540, container.clientWidth - 30), height = 260;
  const margin = { left: 42, right: 18, top: 22, bottom: 36 };
  const plotWidth = width - margin.left - margin.right, plotHeight = height - margin.top - margin.bottom;
  const rawMax = Math.max(...series.map(point => point.count || 0));
  const step = Math.max(1, Math.ceil(rawMax / 4)), max = step * 4;
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Grafik jumlah artikel per interval. Angka lengkap tersedia melalui Lihat angka." });
  const x = i => margin.left + (i + 0.5) * plotWidth / series.length;
  const y = count => margin.top + plotHeight * (1 - count / max);
  for (let i = 0; i <= 4; i++) {
    const value = step * i, position = y(value);
    root.append(svg("line", { x1: margin.left, x2: width - margin.right, y1: position, y2: position, stroke: "#e8eff0", "stroke-dasharray": i ? "3 4" : "none" }));
    root.append(svg("text", { x: margin.left - 12, y: position + 4, fill: "#83969c", "font-size": 11, "text-anchor": "end" }, number(value)));
  }
  const stride = Math.max(1, Math.ceil(series.length / 6));
  series.forEach((point, i) => {
    if (i % stride === 0) {
      root.append(svg("text", { x: x(i), y: height - 10, fill: "#73898f", "font-size": 11, "text-anchor": "middle" }, dateLabel(point.date, state.granularity === "daily" ? "monthly" : state.granularity)));
    }
    if (point.count === null) return;
    const caption = `${dateLabel(point.date)}: ${number(point.count)} artikel`;
    if (state.granularity === "yearly" || state.granularity === "monthly") {
      const barWidth = Math.max(2, Math.min(45, plotWidth / series.length * 0.65));
      const bar = svg("rect", { x: x(i) - barWidth / 2, y: y(point.count), width: barWidth, height: y(0) - y(point.count), rx: Math.min(3, barWidth / 3), fill: "#138c89" });
      bar.append(svg("title", {}, caption)); root.append(bar);
    } else {
      if (i && series[i - 1].count !== null) root.append(svg("line", { x1: x(i - 1), y1: y(series[i - 1].count), x2: x(i), y2: y(point.count), stroke: "#168d88", "stroke-width": 2 }));
      const dot = svg("circle", { cx: x(i), cy: y(point.count), r: state.granularity === "daily" ? 2.2 : 4, fill: "#087e83" });
      dot.append(svg("title", {}, caption)); root.append(dot);
    }
  });
  container.append(root);
}
function cloud(words) {
  const container = $("word-cloud"); container.replaceChildren();
  if (!words.length) { empty(container, "Kata akan muncul di sini", "Word cloud mengikuti topik dan periode yang dipilih."); return; }
  const width = 680, height = 310, rectangles = [];
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Word cloud frekuensi kata. Daftar kata teratas tersedia di panel sebelah." });
  const context = document.createElement("canvas").getContext("2d");
  const colors = ["#087e83", "#163e49", "#3e8a83", "#477281", "#bd7b26", "#67a69c"];
  words.slice(0, 45).forEach((item, index) => {
    let fontSize = Math.round(15 + 40 * Math.sqrt(item.count / words[0].count));
    context.font = `600 ${fontSize}px "Segoe UI", Arial, sans-serif`;
    let textWidth = context.measureText(item.word).width;
    if (textWidth > width - 30) { fontSize *= (width - 30) / textWidth; textWidth = width - 30; }
    const w = textWidth + 12, h = fontSize + 9;
    for (let step = 0; step < 1400; step++) {
      const angle = step * 0.22, radius = 2.7 * Math.sqrt(step);
      const cx = width / 2 + Math.cos(angle) * radius * 2.6, cy = height / 2 + Math.sin(angle) * radius * 1.25;
      const box = { x: cx - w / 2, y: cy - h / 2, w, h };
      if (box.x < 4 || box.y < 4 || box.x + w > width - 4 || box.y + h > height - 4) continue;
      if (rectangles.some(other => box.x < other.x + other.w && box.x + box.w > other.x && box.y < other.y + other.h && box.y + box.h > other.y)) continue;
      rectangles.push(box);
      const label = svg("text", { x: cx, y: cy, "text-anchor": "middle", "dominant-baseline": "central", "font-size": fontSize, "font-weight": 600, "font-family": "Segoe UI, Arial, sans-serif", fill: colors[index % colors.length] }, item.word);
      label.append(svg("title", {}, `${item.word}: ${number(item.count)} kali`)); root.append(label); break;
    }
  });
  container.append(root);
}
function wordList(words) {
  $("top-words").replaceChildren();
  if (!words.length) { const li = document.createElement("li"); li.textContent = "Belum ada kata."; $("top-words").append(li); return; }
  words.slice(0, 7).forEach((word, i) => {
    const li = document.createElement("li");
    const rank = document.createElement("span"); rank.className = "word-rank"; rank.textContent = String(i + 1).padStart(2, "0");
    const label = document.createElement("span"); label.className = "word-label"; label.textContent = word.word;
    const bar = document.createElement("span"); bar.className = "word-bar"; bar.style.width = `${word.count / words[0].count * 100}%`; label.append(bar);
    const count = document.createElement("span"); count.className = "word-count"; count.textContent = number(word.count);
    li.append(rank, label, count); $("top-words").append(li);
  });
}
function articles(items) {
  $("articles-body").replaceChildren(); $("article-count").textContent = `${items.length} ARTIKEL`;
  if (!items.length) { const row = document.createElement("tr"), cell = document.createElement("td"); cell.colSpan = 3; cell.textContent = "Belum ada artikel. Pilih sumber dan mulai crawling, atau impor arsip Anda."; row.append(cell); $("articles-body").append(row); return; }
  items.forEach(item => {
    const row = document.createElement("tr"), title = document.createElement("td"), source = document.createElement("td"), date = document.createElement("td");
    const link = document.createElement(item.url ? "a" : "span"); link.textContent = item.title;
    if (item.url) { link.href = item.url; link.target = "_blank"; link.rel = "noopener noreferrer"; }
    title.append(link); source.className = "article-source"; source.textContent = item.source;
    date.textContent = dateLabel(item.published_at, "daily") + (item.date_precision === "time" ? ` · ${dateLabel(item.published_at, "hours")}` : "");
    row.append(title, source, date); $("articles-body").append(row);
  });
}
function setBusy(busy) { state.busy = busy; $("crawl-button").disabled = busy; $("import-button").disabled = busy; $("crawl-button").textContent = busy ? "Sedang memproses…" : "↗ Mulai crawling"; }
async function refreshTopics() {
  try { const data = await api("/api/config"); const existing = new Set([...$("topic-list").options].map(item => item.value.toLowerCase())); data.topics.forEach(topic => { if (!existing.has(topic.toLowerCase())) { const option = document.createElement("option"); option.value = topic; $("topic-list").append(option); } }); } catch { /* Analysis errors are reported separately. */ }
}
$("view-topic").addEventListener("click", () => { try { state.topic = currentTopic(); load(); } catch (error) { status(error.message, true); } });
document.querySelectorAll("[data-topic]").forEach(button => button.addEventListener("click", () => { $("topic").value = button.dataset.topic; state.topic = button.dataset.topic; load(); }));
$("demo").addEventListener("change", () => { state.demo = $("demo").checked; load(); });
document.querySelectorAll("[data-period]").forEach(button => button.addEventListener("click", () => { state.granularity = button.dataset.period; load(); }));
$("crawl-form").addEventListener("submit", async event => {
  event.preventDefault(); if (state.busy) return;
  try {
    const topic = currentTopic();
    setBusy(true);
    const job = await api("/api/crawl", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ topic, sources: [...document.querySelectorAll('input[name="source"]:checked')].map(node => node.value), urls: $("urls").value.split(/\r?\n/).map(url => url.trim()).filter(Boolean), limit: Number($("limit").value) }) });
    status("Crawling dimulai. Artikel yang cocok akan disimpan otomatis.");
    let result;
    do { await new Promise(resolve => setTimeout(resolve, 1200)); result = await api(`/api/jobs/${job.id}`); status(result.message, result.state === "error"); } while (result.state === "running");
    if (result.warnings?.length) status(`${result.message}\nCatatan: ${result.warnings.join("; ")}`, true);
    if (result.state === "done") { state.topic = topic; $("topic").value = topic; state.demo = false; await load(); await refreshTopics(); }
  } catch (error) { status(error.message, true); }
  finally { setBusy(false); }
});
$("import-form").addEventListener("submit", async event => {
  event.preventDefault(); if (state.busy) return;
  try {
    const topic = currentTopic(), file = $("archive-file").files[0];
    if (!file) throw new Error("Pilih file CSV.");
    if (file.size > 5 * 1024 * 1024) throw new Error("Ukuran file maksimal 5 MB.");
    const payload = new FormData(); payload.append("topic", topic); payload.append("file", file);
    setBusy(true); status("Membaca arsip…");
    const result = await api("/api/import", { method: "POST", body: payload });
    state.topic = topic; state.demo = false; status(result.message); await load(); await refreshTopics();
  } catch (error) { status(error.message, true); }
  finally { setBusy(false); }
});
let resizeTimer;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.data) chart(state.data.series); }, 150); });
refreshTopics(); load();
