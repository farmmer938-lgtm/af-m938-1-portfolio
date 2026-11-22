// On-chain demand verification for an x402 seller. Fetches the seller's 402 challenge to
// learn its payTo wallet, then reads that wallet's USDC Transfer logs on Base and separates
// independent buyers from self-paid volume and automated probers. Read-only: it never pays
// and never moves funds.
import { checkEndpoint } from "./endpointcheck.mjs";

const USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913";
const TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
const BASE_MAINNET = "eip155:8453";
const RPC = process.env.AF_BASE_RPC || "https://base-rpc.publicnode.com";
// ~7 days of 2s Base blocks. A shorter default once made "0 inbound" mean "0 in one day".
const WINDOW_BLOCKS = Number(process.env.AF_VERIFY_WINDOW_BLOCKS || 302400);
// publicnode rejects one eth_getLogs call above 50k blocks, so the window is scanned in chunks.
const CHUNK_BLOCKS = Number(process.env.AF_VERIFY_CHUNK_BLOCKS || 49000);

// A wallet that pays one seller hundreds of times in a week is a loop, not a buyer; a wallet
// that pays a few cents is a catalogue scout. Neither may be counted as demand.
export const LOOP_MIN_TX = Number(process.env.AF_VERIFY_LOOP_MIN_TX || 20);
export const DUST_MAX_USDC = Number(process.env.AF_VERIFY_DUST_MAX_USDC || 0.1);
export const REAL_MIN_USDC = 5;
export const REAL_MIN_PAYERS = 3;
export const REAL_MIN_SHARE = 0.5;
export const NEGLIGIBLE_MAX_USDC = 1;

export const DEMO_TARGETS = [
  { label: "bitrefill", url: "https://api.bitrefill.com/x402/invoice/pay" },
  { label: "api-xpay", url: "https://www.api-xpay.com/x402/time" },
];

const padAddress = (addr) => "0x" + String(addr).toLowerCase().replace(/^0x/, "").padStart(64, "0");

async function rpc(method, params, retries = 3) {
  let last = null;
  for (let i = 0; i < retries; i++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 20000);
    try {
      const resp = await fetch(RPC, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
        signal: ctrl.signal,
      });
      const j = await resp.json();
      if (j.error) throw new Error(j.error.message || JSON.stringify(j.error));
      return j.result;
    } catch (e) {
      last = e;
      await new Promise((r) => setTimeout(r, 400 * (i + 1)));
    } finally {
      clearTimeout(timer);
    }
  }
  throw new Error(`rpc ${method} failed: ${String(last?.message || last).slice(0, 120)}`);
}

// All USDC transfers INTO `payTo` over [latest - windowBlocks, latest], chunked for the RPC cap.
async function inboundTransfers(payTo, windowBlocks) {
  const latest = Number(await rpc("eth_blockNumber", []));
  const from = latest - windowBlocks;
  const rows = [];
  for (let start = from; start <= latest; start += CHUNK_BLOCKS) {
    const end = Math.min(start + CHUNK_BLOCKS - 1, latest);
    const logs = await rpc("eth_getLogs", [{
      address: USDC, fromBlock: "0x" + start.toString(16), toBlock: "0x" + end.toString(16),
      topics: [TRANSFER, null, padAddress(payTo)],
    }]);
    for (const lg of logs) {
      if (!lg.topics || lg.topics.length < 3) continue;
      rows.push({
        from: "0x" + lg.topics[1].slice(-40),
        to: "0x" + lg.topics[2].slice(-40),
        atomic: BigInt(lg.data),
        block: Number(lg.blockNumber),
        tx: lg.transactionHash,
      });
    }
  }
  return { latest, from, rows };
}

// Pure classifier: no network. `transfers` = [{from, atomic}] already filtered to payTo.
export function classify({ payTo, transfers }) {
  const self = String(payTo).toLowerCase();
  const usd = (a) => Number(a) / 1e6;
  const total = transfers.reduce((s, t) => s + t.atomic, 0n);
  const external = transfers.filter((t) => String(t.from).toLowerCase() !== self);

  const byPayer = new Map();
  for (const t of external) {
    const k = String(t.from).toLowerCase();
    const cur = byPayer.get(k) || { atomic: 0n, tx: 0 };
    byPayer.set(k, { atomic: cur.atomic + t.atomic, tx: cur.tx + 1 });
  }
  const payers = [...byPayer.entries()]
    .map(([addr, v]) => ({ addr, atomic: v.atomic, tx: v.tx, loop: v.tx >= LOOP_MIN_TX }))
    .sort((a, b) => (b.atomic > a.atomic ? 1 : b.atomic < a.atomic ? -1 : 0));

  const isGenuine = (p) => !p.loop && p.atomic > BigInt(Math.round(DUST_MAX_USDC * 1e6));
  const genuine = payers.filter(isGenuine);
  const loopAtomic = payers.filter((p) => p.loop).reduce((s, p) => s + p.atomic, 0n);
  const genuineAtomic = genuine.reduce((s, p) => s + p.atomic, 0n);
  const externalAtomic = external.reduce((s, t) => s + t.atomic, 0n);
  const genuineShare = externalAtomic > 0n ? Number((genuineAtomic * 10000n) / externalAtomic) / 10000 : 0;

  let verdict;
  if (transfers.length === 0) verdict = "NO_SETTLEMENT";
  else if (external.length === 0) verdict = "SELF_PAY";
  else if (genuine.length === 0) verdict = loopAtomic > 0n ? "SELF_PAY" : "NEGLIGIBLE";
  else if (usd(genuineAtomic) < NEGLIGIBLE_MAX_USDC) verdict = "NEGLIGIBLE";
  else if (genuineShare >= REAL_MIN_SHARE && genuine.length >= REAL_MIN_PAYERS && usd(genuineAtomic) >= REAL_MIN_USDC) verdict = "REAL";
  else verdict = "MIXED";

  const reason =
    `${transfers.length} inbound USDC transfer(s) in 7d: ${external.length} external, ` +
    `${payers.length} distinct external payer(s); ${genuine.length} behave like independent buyers ` +
    `($${usd(genuineAtomic).toFixed(2)} of $${usd(total).toFixed(2)} = ${(genuineShare * 100).toFixed(0)}% genuine). ` +
    `Not counted: self-transfers, wallets paying this seller ${LOOP_MIN_TX}+ times (loops), ` +
    `and payments of $${DUST_MAX_USDC} or less (catalogue scouts).`;

  return {
    verdict, genuineShare,
    settled: {
      usdc: usd(total), transfers: transfers.length,
      external_transfers: external.length, payers: payers.length,
      genuine_payers: genuine.length, genuine_usdc: usd(genuineAtomic),
      self_usdc: usd(total - externalAtomic), loop_usdc: usd(loopAtomic),
    },
    payers: payers.slice(0, 20).map((p) => ({
      address: p.addr, usdc: usd(p.atomic), transfers: p.tx, genuine: isGenuine(p),
    })),
    reason,
  };
}

function pickRail(accepts) {
  const evm = accepts.filter((a) => /^0x[0-9a-f]{40}$/i.test(String(a.payTo || "")));
  return evm.find((a) => String(a.network) === BASE_MAINNET && String(a.asset || "").toLowerCase() === USDC)
    || evm.find((a) => String(a.network) === BASE_MAINNET)
    || null;
}

export async function verifySeller(rawUrl) {
  const url = String(rawUrl || "").trim();
  const probe = await checkEndpoint(url);
  if (!probe.ok) return { ok: false, url, schema: "af.seller_verify.v1", error: probe.error || "unreachable" };
  if (!probe.is_x402) {
    return { ok: false, url, schema: "af.seller_verify.v1",
      error: "not an x402 seller: no well-formed 402 challenge", probe };
  }
  const rail = pickRail(probe.accepts);
  if (!rail) {
    return { ok: false, url, schema: "af.seller_verify.v1",
      error: "no Base mainnet payTo in the 402 challenge (only eip155:8453 is scanned)", probe };
  }

  const { latest, from, rows } = await inboundTransfers(rail.payTo, WINDOW_BLOCKS);
  const out = classify({ payTo: rail.payTo, transfers: rows });
  return {
    ok: true, schema: "af.seller_verify.v1", url, payTo: rail.payTo,
    network: rail.network, asset: rail.asset,
    window: { days: 7, blocks: WINDOW_BLOCKS, from_block: from, to_block: latest },
    ...out,
    method: "402 challenge -> payTo -> USDC Transfer logs on Base -> per-payer behaviour",
    note: out.verdict === "REAL"
      ? "Independent payers moved real money; this seller's demand is not self-paid."
      : "Do not treat a catalogue's payer count as revenue; this verdict is read from the chain.",
  };
}
