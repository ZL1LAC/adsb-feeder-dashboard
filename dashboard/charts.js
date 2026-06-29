/** Lightweight SVG sparklines for feeder history (no dependencies). */

function downsample(rows, maxPoints = 120) {
  if (rows.length <= maxPoints) return rows;
  const step = rows.length / maxPoints;
  const out = [];
  for (let i = 0; i < maxPoints; i++) {
    out.push(rows[Math.floor(i * step)]);
  }
  return out;
}

function fmtStat(v, unit = "") {
  if (v == null || Number.isNaN(v)) return "—";
  const n = Number(v);
  const s = Number.isInteger(n) ? String(n) : n.toFixed(1);
  return unit ? `${s}${unit}` : s;
}

function sparklineSvg(rows, key, opts = {}) {
  const width = opts.width || 280;
  const height = opts.height || 64;
  const color = opts.color || "#3d9cf5";
  const transform = opts.transform || ((v) => v);
  const values = rows
    .map((r) => transform(Number(r[key])))
    .filter((v) => v != null && !Number.isNaN(v));
  if (values.length < 2) {
    return `<svg class="spark" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><text x="4" y="34" fill="#8b9cb3" font-size="11">Collecting data…</text></svg>`;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - 4) + 2;
    const y = height - 14 - ((v - min) / range) * (height - 22);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const areaPts = `2,${height - 14} ${pts.join(" ")} ${width - 2},${height - 14}`;
  const last = values[values.length - 1];
  const fillId = `fill-${key}`;
  return `<svg class="spark" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${opts.label || key}">
    <defs>
      <linearGradient id="${fillId}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${color}" stop-opacity="0.25" />
        <stop offset="100%" stop-color="${color}" stop-opacity="0" />
      </linearGradient>
    </defs>
    <polygon fill="url(#${fillId})" points="${areaPts}" />
    <polyline fill="none" stroke="${color}" stroke-width="1.5" points="${pts.join(" ")}" />
    <text x="${width - 4}" y="12" fill="#8b9cb3" font-size="10" text-anchor="end">${fmtStat(last, opts.unit || "")}</text>
  </svg>`;
}

function statRange(rows, key, opts = {}) {
  const transform = opts.transform || ((v) => v);
  const values = rows
    .map((r) => transform(Number(r[key])))
    .filter((v) => v != null && !Number.isNaN(v));
  if (!values.length) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const unit = opts.unit || "";
  if (min === max) return `${fmtStat(min, unit)} steady`;
  return `${fmtStat(min, unit)}–${fmtStat(max, unit)}`;
}

function timeAxis(rows, range = "24h") {
  if (!rows.length) return "";
  const first = rows[0]?.t;
  const last = rows[rows.length - 1]?.t;
  if (!first || !last) {
    const label = range === "7d" ? "7d ago" : "24h ago";
    return `<div class="chart-axis"><span>${label}</span><span>now</span></div>`;
  }
  try {
    const fmt =
      range === "7d"
        ? (d) => d.toLocaleDateString([], { month: "short", day: "numeric" })
        : (d) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const t0 = fmt(new Date(first));
    const t1 = fmt(new Date(last));
    return `<div class="chart-axis"><span>${t0}</span><span>now (${t1})</span></div>`;
  } catch {
    const label = range === "7d" ? "7d ago" : "24h ago";
    return `<div class="chart-axis"><span>${label}</span><span>now</span></div>`;
  }
}

function renderHistoryCharts(rows, range = "24h") {
  const el = document.getElementById("history-charts");
  if (!el) return;
  const data = downsample(rows || []);
  const charts = [
    { key: "aircraft_total", label: "Aircraft", color: "#3d9cf5", unit: "" },
    { key: "aircraft_positioned", label: "Positioned", color: "#3ecf8e", unit: "" },
    { key: "snr", label: "SNR", color: "#f5b83d", unit: " dB" },
    {
      key: "max_distance",
      label: "Max range",
      color: "#a78bfa",
      unit: " km",
      transform: (v) => (v > 0 ? v / 1000 : null),
    },
  ];
  const blocks = charts
    .map((c) => {
      const rangeLine = statRange(data, c.key, c);
      const rangeHtml = rangeLine ? `<div class="chart-range">${rangeLine}</div>` : "";
      return `<div class="chart-block">
        <div class="chart-label">${c.label}</div>
        ${rangeHtml}
        ${sparklineSvg(data, c.key, { label: c.label, color: c.color, unit: c.unit, transform: c.transform })}
      </div>`;
    })
    .join("");
  el.innerHTML = blocks + timeAxis(data, range);
}

window.renderHistoryCharts = renderHistoryCharts;
