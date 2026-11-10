// Signed settlement receipts. Every paid call appends one receipt to a JSONL log and
// returns it to the buyer inside the response, signed with AF's own wallet key (EIP-191).
// Anyone can then verify, offline and without trusting AF, that AF really was paid:
//   recover(canonical JSON of the receipt) == the address in `signer`.
// This is the trust primitive AF sells alongside its data tools: proof, not assertion.
import fs from "node:fs";
import path from "node:path";
import { privateKeyToAccount } from "viem/accounts";

const KEY = process.env.AF_SIGNER_KEY || "";
const LOG = process.env.AF_RECEIPT_LOG || "/workspace/.af-receipts.jsonl";
const account = KEY ? privateKeyToAccount(KEY.startsWith("0x") ? KEY : "0x" + KEY) : null;

export function signerAddress() {
  return account ? account.address : null;
}

// Stable key order so the signed bytes are reproducible by any verifier.
function canonical(obj) {
  if (Array.isArray(obj)) return "[" + obj.map(canonical).join(",") + "]";
  if (obj && typeof obj === "object") {
    return "{" + Object.keys(obj).sort()
      .map((k) => JSON.stringify(k) + ":" + canonical(obj[k])).join(",") + "}";
  }
  return JSON.stringify(obj);
}

export function canonicalReceipt(receipt) {
  const { signature, ...rest } = receipt;
  return canonical(rest);
}

export function readReceipts(limit = 50) {
  try {
    const lines = fs.readFileSync(LOG, "utf8").split("\n").filter(Boolean);
    return lines.slice(-limit).map((l) => JSON.parse(l));
  } catch {
    return [];
  }
}

export function reputation() {
  const all = readReceipts(10000);
  const payers = new Set();
  const tools = {};
  let totalUsdc = 0;
  for (const r of all) {
    if (r.payer) payers.add(r.payer.toLowerCase());
    tools[r.tool] = (tools[r.tool] || 0) + 1;
    totalUsdc += Number(r.amountUsdc || 0);
  }
  return {
    signer: signerAddress(),
    receipts: all.length,
    uniquePayers: payers.size,
    totalUsdc: +totalUsdc.toFixed(6),
    tools,
    firstSeen: all.length ? all[0].ts : null,
    lastSeen: all.length ? all[all.length - 1].ts : null,
    verify: "Each receipt is signed with EIP-191 (personal_sign) over its canonical JSON (sorted keys, signature excluded). Recover the address and compare it to `signer`; and confirm txHash on the receipt's network.",
  };
}

// Called from the x402 onAfterSettle hook. Never throws: a failed receipt must not
// fail a payment that already settled on-chain.
export async function record({ tool, result, requirements, payer }) {
  const now = new Date().toISOString();
  const amountRaw = requirements?.maxAmountRequired || requirements?.amount || null;
  const decimals = requirements?.extra?.decimals ?? 6;
  const receipt = {
    id: "af_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
    ts: now,
    tool: tool || "unknown",
    payer: payer || result?.payer || null,
    payTo: requirements?.payTo || null,
    network: result?.network || requirements?.network || null,
    asset: requirements?.asset || null,
    amountRaw: amountRaw ? String(amountRaw) : null,
    amountUsdc: amountRaw ? Number(amountRaw) / 10 ** decimals : null,
    txHash: result?.transaction || result?.txHash || null,
    success: result?.success !== false,
    signer: signerAddress(),
  };
  try {
    if (account) receipt.signature = await account.signMessage({ message: canonicalReceipt(receipt) });
  } catch (e) {
    receipt.signature = null;
    receipt.signError = String(e.message || e).slice(0, 120);
  }
  try {
    fs.appendFileSync(LOG, JSON.stringify(receipt) + "\n");
  } catch (e) {
    console.error("[receipts] append failed:", e.message);
  }
  return receipt;
}
