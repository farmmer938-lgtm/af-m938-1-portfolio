// DataBridge: CSV<->JSON conversion with delimiter sniffing and type inference.
export function infer(v) {
  if (v === null || v === undefined) return v;
  const s = String(v).trim();
  if (s === '') return '';
  if (/^-?\d+$/.test(s)) return parseInt(s, 10);
  if (/^-?\d*\.\d+$/.test(s)) return parseFloat(s);
  if (/^(true|false)$/i.test(s)) return s.toLowerCase() === 'true';
  return s;
}

export function sniffDelimiter(text) {
  const line = String(text).split(/\r?\n/).find((l) => l.trim().length) || '';
  const counts = { ',': 0, ';': 0, '\t': 0, '|': 0 };
  let inQ = false;
  for (const ch of line) {
    if (ch === '"') inQ = !inQ;
    else if (!inQ && ch in counts) counts[ch]++;
  }
  let best = ',', n = 0;
  for (const [d, c] of Object.entries(counts)) if (c > n) { n = c; best = d; }
  return best;
}

function splitRow(line, delim) {
  const out = []; let cur = ''; let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQ && line[i + 1] === '"') { cur += '"'; i++; }
      else inQ = !inQ;
    } else if (ch === delim && !inQ) { out.push(cur); cur = ''; }
    else cur += ch;
  }
  out.push(cur);
  return out;
}

export function csvToJson(text, delimiter) {
  const delim = delimiter || sniffDelimiter(text);
  const lines = String(text).split(/\r?\n/).filter((l) => l.trim().length);
  if (!lines.length) return [];
  const headers = splitRow(lines[0], delim).map((h) => h.trim());
  return lines.slice(1).map((line) => {
    const cells = splitRow(line, delim);
    const row = {};
    headers.forEach((h, i) => { row[h] = infer(cells[i]); });
    return row;
  });
}

// Weighted KPI scoring engine.
export function normalise(metric) {
  const { value, target, direction } = metric;
  if (target === 0) return value === 0 ? 1 : 0;
  if (direction === 'lower') return Math.max(0, Math.min(1, target / value));
  return Math.max(0, Math.min(1, value / target));
}

export function score(metrics) {
  if (!metrics || !metrics.length) return { score: 0, breakdown: [] };
  const totalWeight = metrics.reduce((s, m) => s + (m.weight ?? 1), 0) || 1;
  const breakdown = metrics.map((m) => {
    const w = m.weight ?? 1;
    const n = normalise(m);
    return { name: m.name, weight: w, normalised: +n.toFixed(4), contribution: +((n * w) / totalWeight).toFixed(4) };
  });
  const total = breakdown.reduce((s, b) => s + b.contribution, 0);
  return { score: +total.toFixed(4), breakdown };
}
