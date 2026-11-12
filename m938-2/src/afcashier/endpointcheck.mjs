// x402 endpoint checker: given a URL, make one live request and report whether the host
// answers with a well-formed x402 402 challenge — the thing an agent must verify before it
// is willing to pay. Pure helpers are exported for tests; the network call is the only
// side effect. It never pays and never moves funds.
import { lookup } from "node:dns/promises";
import net from "node:net";

const TIMEOUT_MS = 12000;
const MAX_BYTES = 200_000;

const KNOWN_ASSETS = {
  "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": { symbol: "USDC", decimals: 6, network: "eip155:8453" },
  "0x036cbd53842c5426634e7929541ec2318f3dcf7e": { symbol: "USDC", decimals: 6, network: "eip155:84532" },
};
const EVM_RE = /^0x[0-9a-f]{40}$/i;

export function isPrivateHost(hostname) {
  const h = String(hostname || "").toLowerCase().replace(/^\[|\]$/g, "");
  if (h === "localhost" || h.endsWith(".localhost") || h === "::1") return true;
  if (net.isIPv4(h)) {
    const p = h.split(".").map(Number);
    return p[0] === 10 || p[0] === 127 || p[0] === 0 || p[0] >= 224 ||
           (p[0] === 172 && p[1] >= 16 && p[1] <= 31) ||
           (p[0] === 192 && p[1] === 168) || (p[0] === 169 && p[1] === 254);
  }
  if (net.isIPv6(h)) return h === "::1" || h.startsWith("fc") || h.startsWith("fd") || h.startsWith("fe80");
  return false;
}

// The x402 v2 challenge travels as base64url JSON in the Payment-Required header.
export function parseChallenge(headerValue) {
  if (!headerValue || typeof headerValue !== "string") return null;
  try {
    const b64 = headerValue.replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const obj = JSON.parse(Buffer.from(padded, "base64").toString("utf8"));
    return obj && typeof obj === "object" ? obj : null;
  } catch {
    return null;
  }
}

// Pure: turn a raw HTTP outcome into a verdict. No network.
export function evaluate({ url, status, headers = {}, bodyText = "", elapsedMs = 0 }) {
  const h = {};
  for (const [k, v] of Object.entries(headers)) h[String(k).toLowerCase()] = v;
  const hdr = h["payment-required"] || h["x-payment-required"] || null;

  let bodyJson = null;
  try { bodyJson = bodyText ? JSON.parse(bodyText) : null; } catch { /* not json */ }
  let challenge = parseChallenge(hdr);
  let challengeSource = challenge ? "payment-required-header" : null;
  if (!challenge && bodyJson && (bodyJson.accepts || bodyJson.x402Version)) {
    challenge = bodyJson;
    challengeSource = "body";
  }

  const accepts = Array.isArray(challenge?.accepts) ? challenge.accepts : [];
  const picks = accepts.map((a) => {
    const asset = String(a.asset || "").toLowerCase();
    const known = KNOWN_ASSETS[asset];
    const dec = known?.decimals ?? 6;
    const amount = a.amount ?? a.maxAmountRequired;
    const usd = amount != null && /^\d+$/.test(String(amount)) ? Number(amount) / 10 ** dec : null;
    return {
      scheme: a.scheme ?? null, network: a.network ?? null, asset: a.asset ?? null,
      payTo: a.payTo ?? null, amount_atomic: amount != null ? String(amount) : null,
      amount_usd: usd, asset_symbol: known?.symbol ?? null,
    };
  });

  const validPayTo = picks.length > 0 && picks.every((p) => EVM_RE.test(String(p.payTo || "")));
  const hasMainnet = picks.some((p) => String(p.network || "") === "eip155:8453");
  const checks = {
    http_402: status === 402,
    payment_required_header: !!hdr,
    parseable_challenge: !!challenge,
    has_accepts: picks.length > 0,
    valid_pay_to: validPayTo,
    base_mainnet_option: hasMainnet,
    known_stablecoin: picks.some((p) => !!p.asset_symbol),
  };
  const is_x402 = checks.http_402 && checks.parseable_challenge && checks.has_accepts;
  const ready_to_pay = is_x402 && checks.valid_pay_to;

  const warnings = [];
  if (is_x402 && !hdr) warnings.push("challenge is only in the body, not the Payment-Required header");
  if (is_x402 && !validPayTo) warnings.push("payTo is not a valid EVM address");
  if (is_x402 && !hasMainnet) warnings.push("no Base mainnet (eip155:8453) option");
  if (is_x402 && !checks.known_stablecoin) warnings.push("asset is not a recognised stablecoin");
  if (!is_x402 && checks.http_402) warnings.push("returned 402 but the challenge could not be parsed");

  return {
    ok: true, url, reachable: true, status,
    is_x402, ready_to_pay,
    x402_version: challenge?.x402Version ?? null,
    challenge_source: challengeSource,
    accepts: picks,
    resource: challenge?.resource ?? null,
    checks, warnings, elapsed_ms: elapsedMs,
  };
}

async function readCapped(resp) {
  const reader = resp.body?.getReader?.();
  if (!reader) return "";
  const chunks = []; let n = 0;
  while (n < MAX_BYTES) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value); n += value.length;
    if (n >= MAX_BYTES) { try { await reader.cancel(); } catch { /* ignore */ } break; }
  }
  return Buffer.concat(chunks.map((c) => Buffer.from(c))).slice(0, MAX_BYTES).toString("utf8");
}

export async function checkEndpoint(rawUrl, { method = "GET", body = null } = {}) {
  const started = Date.now();
  let u;
  try { u = new URL(String(rawUrl || "")); }
  catch { return { ok: false, url: String(rawUrl || ""), reachable: false, error: "invalid url" }; }
  if (u.protocol !== "https:") return { ok: false, url: u.href, reachable: false, error: "https required" };
  if (isPrivateHost(u.hostname)) return { ok: false, url: u.href, reachable: false, error: "private or loopback host rejected" };
  try {
    const addrs = await lookup(u.hostname, { all: true });
    if (addrs.some((a) => isPrivateHost(a.address))) {
      return { ok: false, url: u.href, reachable: false, error: "host resolves to a private address" };
    }
  } catch {
    return { ok: false, url: u.href, reachable: false, error: "dns lookup failed" };
  }

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const m = String(method || "GET").toUpperCase();
    const resp = await fetch(u.href, {
      method: m, redirect: "manual", signal: ctrl.signal,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body && m !== "GET" && m !== "HEAD" ? JSON.stringify(body) : undefined,
    });
    const headers = {}; resp.headers.forEach((v, k) => { headers[k] = v; });
    const bodyText = await readCapped(resp);
    return evaluate({ url: u.href, status: resp.status, headers, bodyText, elapsedMs: Date.now() - started });
  } catch (e) {
    return { ok: false, url: u.href, reachable: false, error: e?.name === "AbortError" ? "timed out" : String(e?.message || e) };
  } finally {
    clearTimeout(timer);
  }
}
