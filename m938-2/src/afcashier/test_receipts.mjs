// Tests for signed settlement receipts. Run: node --test test_receipts.mjs
// Set AF_SIGNER_KEY before launching if you want the signer to be a specific key; the
// tests default to a fixed test key and never write to the production receipt log.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const KEY = process.env.AF_SIGNER_KEY || "0x" + "11".repeat(32);
process.env.AF_SIGNER_KEY = KEY;
// Isolate the log BEFORE importing the module: it reads the env at import time, and a
// shared log both pollutes the real one and makes these tests order-dependent.
process.env.AF_RECEIPT_LOG = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "af-receipts-")), "receipts.jsonl");

const { recoverMessageAddress } = await import("viem");
const { canonicalReceipt, record, reputation, readReceipts, signerAddress } = await import("./receipts.mjs");

test("canonical JSON is key-order independent", () => {
  const a = canonicalReceipt({ b: 1, a: 2, signature: "0xdead" });
  const b = canonicalReceipt({ a: 2, b: 1, signature: "0xbeef" });
  assert.equal(a, b);
  assert.equal(a, '{"a":2,"b":1}');
});

test("a receipt is signed by the advertised signer", async () => {
  process.env.AF_SIGNER_KEY = KEY;
  const r = await record({
    tool: "csv_to_json",
    result: { success: true, payer: "0xabc", transaction: "0xfeed", network: "eip155:8453" },
    requirements: { maxAmountRequired: "50000", payTo: "0xf3C99a6d6e7C6b2ae00b44dC42cC3eb7691D7702",
      asset: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", extra: { decimals: 6 } },
  });
  assert.ok(r.signature);
  assert.equal(r.amountUsdc, 0.05);
  assert.equal(r.tool, "csv_to_json");
  const recovered = await recoverMessageAddress({ message: canonicalReceipt(r), signature: r.signature });
  assert.equal(recovered.toLowerCase(), (r.signer || "").toLowerCase());
  assert.equal(recovered.toLowerCase(), (signerAddress() || "").toLowerCase());
});

test("a tampered receipt no longer recovers the signer", async () => {
  const r = await record({ tool: "kpi_score", result: { success: true, payer: "0xabc" }, requirements: { maxAmountRequired: "50000" } });
  const forged = { ...r, amountUsdc: 9999 };
  const recovered = await recoverMessageAddress({ message: canonicalReceipt(forged), signature: r.signature });
  assert.notEqual(recovered.toLowerCase(), (r.signer || "").toLowerCase());
});

test("reputation aggregates the receipt log", async () => {
  await record({ tool: "csv_to_sql", result: { success: true, payer: "0xdup" }, requirements: { maxAmountRequired: "80000", extra: { decimals: 6 } } });
  await record({ tool: "csv_to_sql", result: { success: true, payer: "0xdup" }, requirements: { maxAmountRequired: "80000", extra: { decimals: 6 } } });
  const rep = reputation();
  assert.ok(rep.receipts >= 4);
  assert.equal(rep.tools.csv_to_sql >= 2, true);
  assert.equal(rep.totalUsdc > 0, true);
  assert.ok(readReceipts(1000).length >= rep.receipts - 1);
});
