// DataBridge audit — deterministic data-quality audit for CSV/JSON. Pure functions, no
// network, no dependencies. The audit is the product: it turns a messy file into a signed
// report a developer can hand to a client (row/column shape, per-column type consistency,
// nulls, duplicates, whitespace, suspicious values) plus a 0-100 score. Every finding is a
// fact computed from the input, so the report is verifiable, not a model's opinion.
import { csvToJson, sniffDelimiter, splitRow, infer } from "./databridge.mjs";

const empty = (v) => v === "" || v === null || v === undefined;
const isMissingToken = (s) => /^(null|nil|n\/a|na|nan|none|-|\?|#n\/a)$/i.test(s.trim());

function rowShape(rows) {
  const headers = rows.length ? Object.keys(rows[0]) : [];
  const ragged = rows.filter((r) => Object.keys(r).length !== headers.length).length;
  return { columns: headers.length, rows: rows.length, raggedRows: ragged };
}

function columnProfile(rows, name, rawVals) {
  const vals = rows.map((r) => r[name]);
  const present = vals.filter((v) => !empty(v));
  const kinds = new Set(present.map((v) => (typeof v === "number" ? (Number.isInteger(v) ? "int" : "float")
    : typeof v === "boolean" ? "bool" : "string")));
  const missingTokens = present.filter((v) => typeof v === "string" && isMissingToken(v)).length;
  // Whitespace must be measured on the RAW cell: the CSV reader trims fields (so "  x  " and
  // "x" compare equal), but the pad is exactly what breaks a join key, so it is a finding.
  const raw = Array.isArray(rawVals) && rawVals.length === rows.length ? rawVals : vals.map(String);
  const padded = raw.filter((v) => typeof v === "string" && v !== v.trim() && v.trim() !== "").length;
  const uniq = new Set(present.map((v) => JSON.stringify(v))).size;
  const numbers = present.filter((v) => typeof v === "number");
  const outliers = [];
  if (numbers.length >= 8) {
    const sorted = [...numbers].sort((a, b) => a - b);
    const q1 = sorted[Math.floor(sorted.length * 0.25)];
    const q3 = sorted[Math.floor(sorted.length * 0.75)];
    const iqr = q3 - q1;
    if (iqr > 0) {
      const lo = q1 - 3 * iqr, hi = q3 + 3 * iqr;
      for (const v of numbers) if (v < lo || v > hi) outliers.push(v);
    }
  }
  const type = kinds.size === 0 ? "empty" : kinds.size === 1 ? [...kinds][0] : "mixed";
  return {
    name,
    type,
    mixedTypes: kinds.size > 1 ? [...kinds] : undefined,
    missing: vals.length - present.length,
    missingPct: vals.length ? +((vals.length - present.length) / vals.length * 100).toFixed(1) : 0,
    missingTokens,
    whitespacePadded: padded,
    unique: uniq,
    duplicateValues: present.length - uniq,
    outlierCount: outliers.length,
    min: numbers.length ? Math.min(...numbers) : undefined,
    max: numbers.length ? Math.max(...numbers) : undefined,
  };
}

function duplicateRows(rows) {
  const seen = new Map();
  for (const r of rows) {
    const k = JSON.stringify(Object.keys(r).sort().map((c) => [c, r[c]]));
    seen.set(k, (seen.get(k) || 0) + 1);
  }
  let dup = 0;
  for (const n of seen.values()) if (n > 1) dup += n - 1;
  return dup;
}

// Turn facts into weighted findings. severity: high (fix before load), medium, low.
function findings(profile, shape, dupRows) {
  const out = [];
  for (const c of profile) {
    if (c.mixedTypes) out.push({ severity: "high", column: c.name, issue: "mixed types", detail: c.mixedTypes.join("/") });
    if (c.missingPct >= 40) out.push({ severity: "high", column: c.name, issue: "mostly empty", detail: `${c.missingPct}% missing` });
    else if (c.missingPct > 0) out.push({ severity: "medium", column: c.name, issue: "has nulls", detail: `${c.missingPct}% missing` });
    if (c.missingTokens) out.push({ severity: "medium", column: c.name, issue: "null-like tokens", detail: `${c.missingTokens} cells like "N/A"` });
    if (c.whitespacePadded) out.push({ severity: "low", column: c.name, issue: "padded whitespace", detail: `${c.whitespacePadded} cells` });
    if (c.outlierCount) out.push({ severity: "low", column: c.name, issue: "numeric outliers", detail: `${c.outlierCount} beyond 3*IQR` });
  }
  if (shape.raggedRows) out.push({ severity: "high", column: "*", issue: "ragged rows", detail: `${shape.raggedRows} rows with wrong column count` });
  if (dupRows) out.push({ severity: "medium", column: "*", issue: "duplicate rows", detail: `${dupRows} exact duplicates` });
  if (!shape.rows) out.push({ severity: "high", column: "*", issue: "no data rows", detail: "header only or empty" });
  return out;
}

export function auditRows(rows, rawColumns) {
  const shape = rowShape(rows);
  const headers = rows.length ? Object.keys(rows[0]) : [];
  const profile = headers.map((h) => columnProfile(rows, h, rawColumns ? rawColumns[h] : undefined));
  const dupRows = duplicateRows(rows);
  const fnd = findings(profile, shape, dupRows);
  const pen = fnd.reduce((s, f) => s + (f.severity === "high" ? 12 : f.severity === "medium" ? 5 : 1), 0);
  const score = Math.max(0, 100 - pen);
  const grade = score >= 90 ? "A" : score >= 75 ? "B" : score >= 60 ? "C" : score >= 40 ? "D" : "F";
  const readyToLoad = !fnd.some((f) => f.severity === "high");
  return {
    schema: "af.data_audit.v1",
    shape,
    columns: profile,
    duplicateRows: dupRows,
    findings: fnd,
    score,
    grade,
    readyToLoad,
    verdict: readyToLoad
      ? `SAFE TO LOAD — score ${score}/100 (${grade}); ${fnd.length} advisories, no blockers`
      : `NOT SAFE — score ${score}/100 (${grade}); ${fnd.filter((f) => f.severity === "high").length} blocker(s) to fix first`,
  };
}

export function auditCsv(text, opts = {}) {
  const delim = opts.delimiter || sniffDelimiter(text);
  const lines = String(text).split(/\r?\n/).filter((l) => l.trim().length);
  const rawColumns = {};
  if (lines.length) {
    const headers = splitRow(lines[0], delim).map((h) => h.trim());
    headers.forEach((h, i) => {
      rawColumns[h] = lines.slice(1).map((ln) => splitRow(ln, delim)[i] ?? "");
    });
  }
  return { delimiter: delim, ...auditRows(csvToJson(text, delim), rawColumns) };
}

// JSON input: an array of flat objects, or {records:[...]}. Nested objects/arrays are
// stringified so the profiler stays total (it never throws on shape surprises).
export function auditJson(records) {
  const rows = (Array.isArray(records) ? records : records?.records || []).map((r) => {
    const o = {};
    for (const [k, v] of Object.entries(r || {})) o[k] = (v && typeof v === "object") ? JSON.stringify(v) : v;
    return o;
  });
  return auditRows(rows);
}
