// Demand measurement for the x402 storefront.
//
// The storefront is the only demand lever AF fully controls, yet before 2026-11-16 it could
// not tell whether any external buyer ever reached the paywall — the only traffic on record
// was AF's own tests. This module turns "is there real demand?" into a number: every request
// to a paid or trial endpoint is logged, and loopback/health hits are excluded so the count
// reflects buyers, not AF.

export function isLocal(ip) {
  return ip === "127.0.0.1" || ip === "::1" || ip === "::ffff:127.0.0.1";
}

// A hit is external when it did not originate on the loopback interface. AF's own smoke tests
// always come from loopback, so this is the line between "a buyer looked" and "AF looked".
export function summarizeDemand(rows) {
  const external = rows.filter((r) => !r.local);
  const byPath = {};
  for (const r of external) byPath[r.path] = (byPath[r.path] || 0) + 1;
  return {
    total_hits: rows.length,
    external_hits: external.length,
    external_unique_ips: [...new Set(external.map((r) => r.ip))].length,
    by_path: byPath,
    last_external: external.length ? external[external.length - 1] : null,
  };
}
