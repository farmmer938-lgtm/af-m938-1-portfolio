// Demand measurement for the x402 storefront.
//
// The storefront is AF's only demand lever it fully controls, yet before 2026-11-16 it could
// not tell whether any external buyer ever reached the paywall — the only traffic on record
// was AF's own tests. This module turns "is there real demand?" into a number.
//
// HARD LESSON (2026-11-16): the first cut counted any non-127.0.0.1 hit as "external" and
// reported 55 external hits. They were ALL private 10.1.x.x addresses — the sandbox ingress and
// AF's own tooling. That is exactly the self-deception the vendor quorum (5/5) warned about:
// a metric that flatters you. The rule now is fail-closed:
//   * classification uses the SOCKET address only — never the client-supplied X-Forwarded-For
//     (which any caller can spoof to fake a public IP);
//   * only a ROUTABLE (public) socket address counts as a confirmed external buyer;
//   * private/loopback hits are reported separately and never inflate the demand number.

const V4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;

// "loopback" | "private" | "public" | "unknown"
export function classifyIp(ip) {
  if (!ip) return "unknown";
  const v = String(ip).replace(/^::ffff:/, "");
  if (v === "127.0.0.1" || v === "::1" || v === "::") return "loopback";
  const m = v.match(V4);
  if (m) {
    const a = +m[1], b = +m[2];
    if (a === 127) return "loopback";
    if (a === 10) return "private";
    if (a === 172 && b >= 16 && b <= 31) return "private";
    if (a === 192 && b === 168) return "private";
    if (a === 169 && b === 254) return "private"; // link-local
    if (a === 100 && b >= 64 && b <= 127) return "private"; // CGNAT
    if (a === 0 || a >= 224) return "private"; // unspecified / multicast / reserved
    return "public";
  }
  if (/^f[cd][0-9a-f]{2}:/i.test(v) || /^fe80:/i.test(v)) return "private"; // ULA / link-local
  return "public";
}

const CRAWLER = /bot|crawler|spider|slurp|scan|http-client|headless/i;
export function looksCrawler(ua) { return CRAWLER.test(String(ua || "")); }

// rows: { path, cls, ua }. Only cls === "public" is a confirmed external buyer.
export function summarizeDemand(rows) {
  const byClass = { loopback: 0, private: 0, public: 0, unknown: 0 };
  const byPath = {};
  let crawler = 0, lastExternal = null;
  for (const r of rows) {
    const cls = r.cls || "unknown";
    byClass[cls] = (byClass[cls] || 0) + 1;
    if (cls === "public") {
      byPath[r.path] = (byPath[r.path] || 0) + 1;
      lastExternal = r;
      if (looksCrawler(r.ua)) crawler += 1;
    }
  }
  return {
    total_hits: rows.length,
    external_hits: byClass.public,          // CONFIRMED routable clients only
    private_hits: byClass.private,          // ingress / sandbox / AF tooling — NOT buyers
    loopback_hits: byClass.loopback,        // AF's own tests
    crawler_hits: crawler,                  // external but not a buyer
    by_path: byPath,
    last_external: lastExternal,
  };
}
