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
