import test from "node:test";
import assert from "node:assert/strict";
import { classify, DEMO_TARGETS, LOOP_MIN_TX, DUST_MAX_USDC } from "./sellerverify.mjs";

const PAY_TO = "0xf3c99a6d6e7c6b2ae00b44dc42cc3eb7691d7702";
const buyer = (n) => "0x" + n.toString(16).padStart(40, "0");
const usdc = (n) => BigInt(Math.round(n * 1e6));
const t = (from, amount) => ({ from, to: PAY_TO, atomic: usdc(amount) });

test("no transfers is NO_SETTLEMENT", () => {
  const r = classify({ payTo: PAY_TO, transfers: [] });
  assert.equal(r.verdict, "NO_SETTLEMENT");
  assert.equal(r.settled.usdc, 0);
});

test("transfers only from the payTo wallet are SELF_PAY", () => {
  const r = classify({ payTo: PAY_TO, transfers: [t(PAY_TO, 1), t(PAY_TO.toUpperCase().replace("0X", "0x"), 2)] });
  assert.equal(r.verdict, "SELF_PAY");
});

test("one buyer paying a few cents is NEGLIGIBLE, not demand", () => {
  const r = classify({ payTo: PAY_TO, transfers: [t(buyer(1), 0.01)] });
  assert.equal(r.verdict, "NEGLIGIBLE");
});

test("many independent buyers with real money is REAL", () => {
  const r = classify({ payTo: PAY_TO, transfers: [t(buyer(1), 4), t(buyer(2), 3), t(buyer(3), 2.5)] });
  assert.equal(r.verdict, "REAL");
  assert.ok(r.genuineShare > 0.99);
});

test("one wallet looping hundreds of payments is SELF_PAY even with large volume", () => {
  const loop = Array.from({ length: LOOP_MIN_TX + 5 }, () => t(buyer(9), 1));
  const r = classify({ payTo: PAY_TO, transfers: loop });
  assert.equal(r.verdict, "SELF_PAY");
  assert.equal(r.settled.genuine_payers, 0);
});

test("a loop plus a small real buyer is MIXED", () => {
  const loop = Array.from({ length: LOOP_MIN_TX }, () => t(buyer(9), 1));
  const r = classify({ payTo: PAY_TO, transfers: [...loop, t(buyer(1), 0.5), t(buyer(2), 0.5), t(buyer(3), 0.5)] });
  assert.equal(r.verdict, "MIXED");
});

test("dust-only payers never reach the genuine count", () => {
  const r = classify({ payTo: PAY_TO, transfers: [t(buyer(1), DUST_MAX_USDC), t(buyer(2), DUST_MAX_USDC)] });
  assert.equal(r.settled.genuine_payers, 0);
});

test("demo targets are https and distinct", () => {
  assert.ok(DEMO_TARGETS.length >= 2);
  for (const d of DEMO_TARGETS) assert.match(d.url, /^https:\/\//);
  assert.equal(new Set(DEMO_TARGETS.map((d) => d.url)).size, DEMO_TARGETS.length);
});
