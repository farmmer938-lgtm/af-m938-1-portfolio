// Tests for the x402 endpoint checker. Run: node --test test_endpointcheck.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { parseChallenge, isPrivateHost, evaluate } from "./endpointcheck.mjs";

const USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const challenge = {
  x402Version: 2,
  error: "Payment required",
  resource: { url: "https://api.example.com/csv_to_json", description: "Convert CSV" },
  accepts: [{
    scheme: "exact", network: "eip155:8453", amount: "50000", asset: USDC_BASE,
    payTo: "0xf3C99a6d6e7C6b2ae00b44dC42cC3eb7691D7702", maxTimeoutSeconds: 300,
    extra: { name: "USD Coin", version: "2" },
  }],
};
const headerFor = (obj) => Buffer.from(JSON.stringify(obj)).toString("base64url");

test("parseChallenge decodes a base64url challenge header", () => {
  const c = parseChallenge(headerFor(challenge));
  assert.equal(c.x402Version, 2);
  assert.equal(c.accepts[0].payTo, challenge.accepts[0].payTo);
});

test("parseChallenge returns null on garbage", () => {
  assert.equal(parseChallenge("not-base64!!!"), null);
  assert.equal(parseChallenge(""), null);
  assert.equal(parseChallenge(null), null);
});

test("isPrivateHost blocks loopback, RFC1918, link-local and IPv6 loopback", () => {
  for (const h of ["localhost", "127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.9.9", "169.254.1.1", "::1"]) {
    assert.equal(isPrivateHost(h), true, h);
  }
  assert.equal(isPrivateHost("api.example.com"), false);
  assert.equal(isPrivateHost("8.8.8.8"), false);
});

test("evaluate: a well-formed 402 header is x402 and ready to pay", () => {
  const r = evaluate({ url: "https://api.example.com/csv_to_json", status: 402, headers: { "payment-required": headerFor(challenge) }, bodyText: '{"error":"Payment required"}' });
  assert.equal(r.is_x402, true);
  assert.equal(r.ready_to_pay, true);
  assert.equal(r.accepts[0].amount_usd, 0.05);
  assert.equal(r.accepts[0].asset_symbol, "USDC");
  assert.deepEqual(r.warnings, []);
});

test("evaluate: a 200 response is not x402", () => {
  const r = evaluate({ url: "https://api.example.com/", status: 200, headers: {}, bodyText: '{"ok":true}' });
  assert.equal(r.is_x402, false);
  assert.equal(r.ready_to_pay, false);
});

test("evaluate: body-only challenge still parses but warns about the missing header", () => {
  const r = evaluate({ url: "https://api.example.com/x", status: 402, headers: {}, bodyText: JSON.stringify(challenge) });
  assert.equal(r.is_x402, true);
  assert.equal(r.challenge_source, "body");
  assert.ok(r.warnings.some((w) => /header/.test(w)));
});

test("evaluate: a bad payTo is flagged and not ready to pay", () => {
  const bad = { ...challenge, accepts: [{ ...challenge.accepts[0], payTo: "not-an-address" }] };
  const r = evaluate({ url: "https://api.example.com/x", status: 402, headers: { "payment-required": headerFor(bad) }, bodyText: "" });
  assert.equal(r.is_x402, true);
  assert.equal(r.ready_to_pay, false);
  assert.ok(r.warnings.some((w) => /payTo/.test(w)));
});

test("evaluate: 402 with unparseable challenge is not x402", () => {
  const r = evaluate({ url: "https://api.example.com/x", status: 402, headers: {}, bodyText: '{"error":"Payment required"}' });
  assert.equal(r.is_x402, false);
  assert.ok(r.warnings.some((w) => /could not be parsed/.test(w)));
});
