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

// CSV -> runnable SQL (CREATE TABLE + INSERT). A pipeline builder otherwise has to infer
// column types and quote identifiers by hand for every file, which is exactly the kind of
// repetitive step an agent wants to buy rather than write.
const SQL_TYPES = {
  postgres: { int: 'bigint', float: 'double precision', bool: 'boolean', text: 'text' },
  mysql: { int: 'BIGINT', float: 'DOUBLE', bool: 'BOOLEAN', text: 'TEXT' },
  sqlite: { int: 'INTEGER', float: 'REAL', bool: 'INTEGER', text: 'TEXT' },
};

function columnType(values) {
  const present = values.filter((v) => v !== '' && v !== null && v !== undefined);
  if (!present.length) return 'text';
  if (present.every((v) => typeof v === 'number' && Number.isInteger(v))) return 'int';
  if (present.every((v) => typeof v === 'number')) return 'float';
  if (present.every((v) => typeof v === 'boolean')) return 'bool';
  return 'text';
}

function sqlIdent(name, dialect) {
  const clean = String(name).replace(/[^A-Za-z0-9_]/g, '_') || 'col';
  if (dialect === 'mysql') return '`' + clean + '`';
  return '"' + clean + '"';
}

function sqlLiteral(v, type, dialect) {
  if (v === '' || v === null || v === undefined) return 'NULL';
  if (type === 'int' || type === 'float') return String(v);
  if (type === 'bool') {
    if (dialect === 'sqlite') return v ? '1' : '0';
    return v ? 'TRUE' : 'FALSE';
  }
  return "'" + String(v).replace(/'/g, "''") + "'";
}

export function csvToSql(text, opts = {}) {
  const dialect = (opts.dialect || 'postgres').toLowerCase();
  if (!SQL_TYPES[dialect]) throw new Error("dialect must be one of: postgres, mysql, sqlite");
  const table = String(opts.table || 'data');
  const rows = csvToJson(text, opts.delimiter);
  if (!rows.length) return { dialect, table, columns: [], rowCount: 0, ddl: '', dml: '' };

  const headers = Object.keys(rows[0]);
  const types = headers.map((h) => columnType(rows.map((r) => r[h])));
  const t = SQL_TYPES[dialect];
  const cols = headers.map((h, i) => `${sqlIdent(h, dialect)} ${t[types[i]]}`);
  const ddl = `CREATE TABLE ${sqlIdent(table, dialect)} (\n  ${cols.join(',\n  ')}\n);`;
  const values = rows.map((r) =>
    '  (' + headers.map((h, i) => sqlLiteral(r[h], types[i], dialect)).join(', ') + ')');
  const dml = `INSERT INTO ${sqlIdent(table, dialect)} (${headers.map((h) => sqlIdent(h, dialect)).join(', ')}) VALUES\n${values.join(',\n')};`;
  return {
    dialect, table, rowCount: rows.length,
    columns: headers.map((h, i) => ({ name: h, type: t[types[i]], inferred: types[i] })),
    ddl, dml,
  };
}
