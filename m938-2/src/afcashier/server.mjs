// AF x402 cashier — sells the DataBridge tool (CSV<->JSON + KPI scoring) per call,
// settles USDC on Base mainnet straight to AF's own wallet. No account, no API key,
// no human in the loop: an agent hits the endpoint, gets a 402 with the price,
// signs an EIP-3009 transfer, retries, and gets the result.
import express from "express";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { paymentMiddleware, x402ResourceServer } from "@x402/express";
import { ExactEvmScheme } from "@x402/evm/exact/server";
import { ExactSvmScheme } from "@x402/svm/exact/server";
import { HTTPFacilitatorClient } from "@x402/core/server";
import { bazaarResourceServerExtension, declareDiscoveryExtension } from "@x402/extensions/bazaar";
import { csvToJson, csvToSql, score } from "./databridge.mjs";
import { auditCsv, auditJson } from "./audit.mjs";
import { checkEndpoint } from "./endpointcheck.mjs";
import { record, reputation, readReceipts, signerAddress } from "./receipts.mjs";

const PAY_TO = process.env.AF_PAY_TO || "0xf3C99a6d6e7C6b2ae00b44dC42cC3eb7691D7702";
const PRICE = process.env.AF_PRICE || "$0.05";
// The SQL emitter does more work per call (type inference + identifier quoting + literal
// escaping for three dialects), so it is priced above the plain converter.
const SQL_PRICE = process.env.AF_SQL_PRICE || "$0.08";
// Endpoint checking makes one live outbound call, so it is priced like the SQL emitter.
const CHECK_PRICE = process.env.AF_CHECK_PRICE || "$0.08";
// The data-quality audit is the hero SKU (vendor consult 2026-11-13, 4/6 chose it): a
// deterministic "is this file safe to load?" report, priced at $49 to sell self-serve.
const AUDIT_PRICE = process.env.AF_AUDIT_PRICE || "$49";
const NET = "eip155:8453"; // Base mainnet
// Solana mainnet (CAIP-2). PayAI is Solana-first and sponsors the network fee, so a buyer
// needs only USDC — no SOL, and AF needs no gas to be paid. AF's Solana payout address comes
// from its own key (secrets/af_solana.json); the EVM address can't receive SPL tokens.
const SVM_NET = process.env.AF_SVM_NETWORK || "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp";
const SVM_PAY_TO = process.env.AF_SVM_PAY_TO || null;
// Public base URL, used as the canonical resource id that CDP Bazaar indexes. The host
// embeds the container RUNTIME_ID, so derive it from the live environment when no explicit
// override is set; a hardcoded host goes stale on restart and buyers then hit a dead URL.
const PUBLIC = process.env.AF_PUBLIC_URL
  || (process.env.RUNTIME_URL ? "https://work-1-" + process.env.RUNTIME_URL.replace(/^https?:\/\//, "") : null)
  || "https://work-1-mbagwhmoyaqtbyvu.prod-runtime.all-hands.dev";
// Directory whose contents are served verbatim at /.well-known/* (control proofs etc).
const WELLKNOWN_DIR = process.env.AF_WELLKNOWN_DIR
  || path.join(path.dirname(fileURLToPath(import.meta.url)), "well-known");
// Public work samples (evidence pages) served at /work/*. Bids cite these URLs, so a
// buyer must be able to fetch them; a 404 here silently voids AF's proof-of-work claim.
const WORK_DIR = process.env.AF_WORK_DIR
  || path.join(path.dirname(fileURLToPath(import.meta.url)), "work");

const app = express();
app.use(express.json());

const facilitator = new HTTPFacilitatorClient({ url: "https://facilitator.payai.network" });
const resourceServer = new x402ResourceServer(facilitator)
  .register(NET, new ExactEvmScheme())
  .registerExtension(bazaarResourceServerExtension);
if (SVM_PAY_TO) resourceServer.register(SVM_NET, new ExactSvmScheme());

// Payment options offered per resource: Base (USDC, EIP-3009) and — when AF has a Solana
// payout address — Solana (USDC, facilitator-sponsored fee). Buyers pick whichever rail
// their wallet already holds USDC on.
const acceptsFor = (price = PRICE) => {
  const a = [{ scheme: "exact", price, network: NET, payTo: PAY_TO }];
  if (SVM_PAY_TO) a.push({ scheme: "exact", price, network: SVM_NET, payTo: SVM_PAY_TO });
  return a;
};

// FOOT-IN-THE-DOOR free trial (closing technique; 6/6 vendor quorum 2026-11-13). Developers
// don't read pitches, they run code. A free, CAPPED call removes all payment risk so the
// first integration happens with zero friction, with the paid endpoint one step away. The
// cap (rows/chars) keeps it a taste, not a free tier. Registered BEFORE paymentMiddleware so
// it never hits the paywall. Every hit is logged so AF can measure real demand.
const TRIAL_MAX_ROWS = Number(process.env.AF_TRIAL_MAX_ROWS || 50);
const TRIAL_MAX_CHARS = Number(process.env.AF_TRIAL_MAX_CHARS || 8000);

function trialLog(tool, ok, note) {
  try {
    fs.appendFileSync("/workspace/.af-trial.log",
      `${new Date().toISOString()} ${tool} ok=${ok} ${note || ""}\n`);
  } catch { /* logging must never break the response */ }
}
function csvTrialGate(body) {
  const csv = String(body?.csv ?? "");
  if (!csv) return "csv is required";
  if (csv.length > TRIAL_MAX_CHARS) return `trial caps input at ${TRIAL_MAX_CHARS} chars; the paid endpoint has no limit`;
  const rows = csv.split(/\r?\n/).filter((l) => l.trim()).length;
  if (rows > TRIAL_MAX_ROWS) return `trial caps at ${TRIAL_MAX_ROWS} rows; the paid endpoint has no limit`;
  return null;
}
const upgrade = (name, price) => ({
  endpoint: `${PUBLIC}/${name}`, price, network: NET,
  note: "same output, no input cap, payable per call over x402 (no account, no API key)",
});

app.post("/trial/csv_to_json", (req, res) => {
  const err = csvTrialGate(req.body);
  if (err) { trialLog("csv_to_json", false, err); return res.status(400).json({ ok: false, error: err, upgrade: upgrade("csv_to_json", PRICE) }); }
  try {
    const rows = csvToJson(String(req.body?.csv ?? ""));
    trialLog("csv_to_json", true, `rows=${rows.length}`);
    res.json({ ok: true, trial: true, rows, upgrade: upgrade("csv_to_json", PRICE) });
  } catch (e) { trialLog("csv_to_json", false, String(e.message || e)); res.status(400).json({ ok: false, error: String(e.message || e) }); }
});
app.post("/trial/kpi_score", (req, res) => {
  try {
    const s = score(req.body?.metrics ?? []);
    trialLog("kpi_score", true);
    res.json({ ok: true, trial: true, score: s, upgrade: upgrade("kpi_score", PRICE) });
  } catch (e) { trialLog("kpi_score", false, String(e.message || e)); res.status(400).json({ ok: false, error: String(e.message || e) }); }
});

// Free, CAPPED taste of the audit. Capped to a small CSV so the paid $49 audit is the
// full-file product; the sample report is enough for a buyer to see exactly what they get.
const AUDIT_TRIAL_MAX_ROWS = Number(process.env.AF_AUDIT_TRIAL_MAX_ROWS || 20);
app.post("/trial/audit", (req, res) => {
  const csv = String(req.body?.csv ?? "");
  if (!csv) { trialLog("audit", false, "no csv"); return res.status(400).json({ ok: false, error: "csv is required", upgrade: upgrade("audit", AUDIT_PRICE) }); }
  const rows = csv.split(/\r?\n/).filter((l) => l.trim()).length;
  if (rows > AUDIT_TRIAL_MAX_ROWS) {
    trialLog("audit", false, `rows=${rows}`);
    return res.status(400).json({ ok: false, error: `trial caps at ${AUDIT_TRIAL_MAX_ROWS} rows; the paid audit has no limit`, upgrade: upgrade("audit", AUDIT_PRICE) });
  }
  try {
    const report = auditCsv(csv);
    trialLog("audit", true, `grade=${report.grade}`);
    res.json({ ok: true, trial: true, report, upgrade: upgrade("audit", AUDIT_PRICE) });
  } catch (e) { trialLog("audit", false, String(e.message || e)); res.status(400).json({ ok: false, error: String(e.message || e) }); }
});

app.use(paymentMiddleware({
  "POST /csv_to_json": {
    accepts: acceptsFor(),
    resource: `${PUBLIC}/csv_to_json`,
    description: "Convert CSV text to typed JSON (delimiter sniffing, quoted fields, number/bool inference).",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["csv", "json", "data", "etl", "converter"],
    extensions: declareDiscoveryExtension({
      method: "POST",
      bodyType: "json",
      input: { csv: "a,b\n1,true" },
      inputSchema: { properties: { csv: { type: "string" }, delimiter: { type: "string" } }, required: ["csv"] },
      output: { example: { ok: true, rows: [{ a: 1, b: true }] } },
    }),
  },
  "POST /kpi_score": {
    accepts: acceptsFor(),
    resource: `${PUBLIC}/kpi_score`,
    description: "Score weighted KPIs to 0..100 with higher/lower-is-better normalisation.",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["kpi", "metrics", "scoring", "analytics"],
    extensions: declareDiscoveryExtension({
      method: "POST",
      bodyType: "json",
      input: { metrics: [{ name: "uptime", value: 99.5, target: 99.9, direction: "higher", weight: 1 }] },
      inputSchema: {
        properties: {
          metrics: {
            type: "array",
            items: {
              type: "object",
              properties: {
                name: { type: "string" }, value: { type: "number" }, target: { type: "number" },
                direction: { type: "string", enum: ["higher", "lower"] }, weight: { type: "number" },
              },
              required: ["name", "value", "target"],
            },
          },
        },
        required: ["metrics"],
      },
      output: { example: { ok: true, score: { score: 0.99, breakdown: [] } } },
    }),
  },
  "POST /csv_to_sql": {
    accepts: acceptsFor(SQL_PRICE),
    resource: `${PUBLIC}/csv_to_sql`,
    description: "Convert CSV text to runnable SQL: CREATE TABLE with inferred column types plus INSERT statements, for postgres, mysql or sqlite.",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["csv", "sql", "etl", "database", "schema", "ddl"],
    extensions: declareDiscoveryExtension({
      method: "POST",
      bodyType: "json",
      input: { csv: "name,age,active\nAnn,31,true", table: "people", dialect: "postgres" },
      inputSchema: {
        properties: {
          csv: { type: "string" },
          table: { type: "string" },
          dialect: { type: "string", enum: ["postgres", "mysql", "sqlite"] },
          delimiter: { type: "string" },
        },
        required: ["csv"],
      },
      output: { example: { ok: true, sql: { dialect: "postgres", ddl: "CREATE TABLE ...", dml: "INSERT INTO ...", columns: [] } } },
    }),
  },
  "POST /x402_check": {
    accepts: acceptsFor(CHECK_PRICE),
    resource: `${PUBLIC}/x402_check`,
    description: "Check whether an endpoint answers with a well-formed x402 402 challenge before you pay it: parses the Payment-Required header, lists the accepts (scheme, network, asset, payTo, amount), and says if it is ready to pay.",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["x402", "endpoint", "verify", "health", "payment", "discovery"],
    extensions: declareDiscoveryExtension({
      method: "POST",
      bodyType: "json",
      input: { url: "https://example.com/paid-route", method: "GET" },
      inputSchema: {
        properties: {
          url: { type: "string", description: "https URL of the x402 endpoint to check." },
          method: { type: "string", enum: ["GET", "POST"], description: "HTTP method to probe with. Defaults to GET." },
          body: { type: "object", description: "Optional JSON body for a POST probe." },
        },
        required: ["url"],
      },
      output: { example: { ok: true, url: "https://example.com/paid-route", is_x402: true, ready_to_pay: true, accepts: [] } },
    }),
  },
  "POST /audit": {
    accepts: acceptsFor(AUDIT_PRICE),
    resource: `${PUBLIC}/audit`,
    description: "Data-quality audit: a deterministic report (shape, per-column type consistency, nulls, duplicates, outliers, whitespace) with a 0-100 score, letter grade and a ready-to-load verdict, for CSV or JSON. Accepts up to ~1MB per call.",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["data", "quality", "audit", "csv", "json", "validation", "etl"],
    extensions: declareDiscoveryExtension({
      method: "POST",
      bodyType: "json",
      input: { csv: "id,name,score\n1,ann,10\n2,bob,\n2,bob,\n3,N/A,30" },
      inputSchema: {
        properties: {
          csv: { type: "string", description: "CSV text to audit (with a header row). Provide csv OR json." },
          json: { type: "array", description: "Array of flat JSON objects to audit. Provide csv OR json." },
          delimiter: { type: "string", description: "Optional explicit delimiter; omit to auto-sniff." },
        },
      },
      output: { example: { ok: true, report: { schema: "af.data_audit.v1", score: 73, grade: "C", readyToLoad: false, findings: [] } } },
    }),
  },
}, resourceServer));

// Receipts are signed in the settlement hook: funds have already moved on-chain, so a
// failure here is logged, never thrown (it must not fail a settled payment).
const toolFor = (ctx) => {
  const r = ctx?.requirements?.resource ?? ctx?.paymentPayload?.resource ?? ctx?.resource;
  // `resource` can be a string or an object like { url }.
  const url = typeof r === "string" ? r : r?.url || r?.resource;
  if (url) return String(url).split("/").filter(Boolean).pop() || "unknown";
  const t = ctx?.transportContext;
  const p = t?.request?.path || t?.req?.path || t?.path;
  return p ? String(p).split("/").filter(Boolean).pop() : "unknown";
};
resourceServer.onAfterSettle(async (ctx) => {
  try {
    await record({
      tool: toolFor(ctx),
      result: ctx.result,
      requirements: ctx.requirements,
      payer: ctx.result?.payer,
    });
  } catch (e) {
    console.error("[receipts] hook error:", e.message);
  }
});

// Free, machine-readable proof of AF's own track record. An agent can check this before
// paying: it is signed data, so the buyer does not have to take AF's word for it.
app.get("/receipts.json", (req, res) => {
  const limit = Math.min(Number(req.query.limit) || 50, 1000);
  res.json({ signer: signerAddress(), count: readReceipts(1000).length, receipts: readReceipts(limit) });
});
app.get("/reputation.json", (_req, res) => res.json(reputation()));

app.get("/", (_req, res) => res.json({
  name: "AF DataBridge (x402)",
  tools: { "POST /csv_to_json": PRICE, "POST /kpi_score": PRICE, "POST /csv_to_sql": SQL_PRICE, "POST /x402_check": CHECK_PRICE, "POST /audit": AUDIT_PRICE },
  hero: { "POST /audit": `data-quality audit (${AUDIT_PRICE}) — deterministic report + 0-100 score + ready-to-load verdict` },
  try_free: {
    note: "First call is FREE and needs no payment — try before you pay.",
    "POST /trial/csv_to_json": `free (<= ${TRIAL_MAX_ROWS} rows)`,
    "POST /trial/kpi_score": "free",
    "POST /trial/audit": `free (<= ${AUDIT_TRIAL_MAX_ROWS} rows)`,
  },
  network: NET, payTo: PAY_TO,
  rails: SVM_PAY_TO ? { base: PAY_TO, solana: SVM_PAY_TO } : { base: PAY_TO },
  proof: {
    note: "AF signs a receipt for every settled call. Verify offline; do not trust the claim.",
    receipts: "/receipts.json", reputation: "/reputation.json",
    verifier: "tools/af_verify_receipts.py in github.com/farmmer938-lgtm/AX_MASTER_BRAIN",
  },
}));

app.get("/favicon.ico", (_req, res) => {
  res.type("image/svg+xml").send(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#0b0f19"/><text x="16" y="22" font-family="monospace" font-size="16" fill="#4ade80" text-anchor="middle">AF</text></svg>'
  );
});

// OpenAPI is the canonical discovery contract x402scan/agents read. Served from the
// public origin so a registration probe resolves the same document buyers will fetch.
app.get("/openapi.json", (_req, res) => res.json({
  openapi: "3.1.0",
  info: {
    title: "AF DataBridge",
    version: "1.0.0",
    description: "Pay-per-call data utilities by AF: a data-quality audit (CSV/JSON), CSV to typed JSON, CSV to runnable SQL, weighted KPI scoring, and x402 endpoint checks. Pay USDC on Base (x402); no account or API key.",
    "x-guidance": "Hero product: POST /audit with {\"csv\":\"id,name\\n1,ann\\n2,\"} returns a deterministic data-quality report (score 0-100, grade, ready-to-load verdict, per-column findings). Call POST /csv_to_json with {\"csv\":\"a,b\\n1,true\"} for typed rows. Call POST /kpi_score with {\"metrics\":[{\"name\":\"uptime\",\"value\":99.5,\"target\":99.9,\"direction\":\"higher\",\"weight\":1}]} for a weighted score. /audit is $49 per call; the others are $0.05-$0.08; all settle in USDC on Base via x402, and an unpaid call returns 402 with the terms in the PAYMENT-REQUIRED header.",
    contact: { email: "farmmer938@gmail.com" },
  },
  paths: {
    "/csv_to_json": {
      post: {
        operationId: "csv_to_json",
        summary: "Convert CSV text to typed JSON",
        tags: ["Data"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.05" }, protocols: [{ x402: {} }] },
        requestBody: {
          required: true,
          content: { "application/json": { schema: {
            type: "object",
            properties: {
              csv: { type: "string", minLength: 1, description: "CSV content with a header row." },
              delimiter: { type: "string", description: "Optional explicit delimiter; omit to auto-sniff (, ; tab |)." },
            },
            required: ["csv"],
          } } },
        },
        responses: {
          200: { description: "Typed JSON rows", content: { "application/json": { schema: {
            type: "object", properties: { ok: { type: "boolean" }, rows: { type: "array", items: { type: "object" } } }, required: ["ok", "rows"],
          } } } },
          402: { description: "Payment Required" },
        },
      },
    },
    "/kpi_score": {
      post: {
        operationId: "kpi_score",
        summary: "Score weighted KPIs to 0..1",
        tags: ["Analytics"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.05" }, protocols: [{ x402: {} }] },
        requestBody: {
          required: true,
          content: { "application/json": { schema: {
            type: "object",
            properties: { metrics: { type: "array", items: {
              type: "object",
              properties: {
                name: { type: "string" }, value: { type: "number" }, target: { type: "number" },
                direction: { type: "string", enum: ["higher", "lower"] }, weight: { type: "number" },
              },
              required: ["name", "value", "target"],
            } } },
            required: ["metrics"],
          } } },
        },
        responses: {
          200: { description: "Weighted score with breakdown", content: { "application/json": { schema: {
            type: "object", properties: { ok: { type: "boolean" }, score: { type: "object" } }, required: ["ok", "score"],
          } } } },
          402: { description: "Payment Required" },
        },
      },
    },
    "/csv_to_sql": {
      post: {
        operationId: "csv_to_sql",
        summary: "Convert CSV text to runnable SQL (DDL + INSERT)",
        tags: ["Data"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.08" }, protocols: [{ x402: {} }] },
        requestBody: {
          required: true,
          content: { "application/json": { schema: {
            type: "object",
            properties: {
              csv: { type: "string", minLength: 1, description: "CSV content with a header row." },
              table: { type: "string", description: "Table name to create. Defaults to 'data'." },
              dialect: { type: "string", enum: ["postgres", "mysql", "sqlite"], description: "SQL dialect. Defaults to postgres." },
              delimiter: { type: "string", description: "Optional explicit delimiter; omit to auto-sniff." },
            },
            required: ["csv"],
          } } },
        },
        responses: {
          200: { description: "CREATE TABLE + INSERT SQL", content: { "application/json": { schema: {
            type: "object", properties: { ok: { type: "boolean" }, sql: { type: "object" } }, required: ["ok", "sql"],
          } } } },
          402: { description: "Payment Required" },
        },
      },
    },
    "/x402_check": {
      post: {
        operationId: "x402_check",
        summary: "Check an endpoint answers with a well-formed x402 402 challenge",
        tags: ["x402", "Verify"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.08" }, protocols: [{ x402: {} }] },
        requestBody: {
          required: true,
          content: { "application/json": { schema: {
            type: "object",
            properties: {
              url: { type: "string", description: "https URL of the x402 endpoint to check." },
              method: { type: "string", enum: ["GET", "POST"], description: "HTTP method to probe with. Defaults to GET." },
              body: { type: "object", description: "Optional JSON body for a POST probe." },
            },
            required: ["url"],
          } } },
        },
        responses: {
          200: { description: "Verdict with parsed accepts and warnings", content: { "application/json": { schema: {
            type: "object", properties: {
              ok: { type: "boolean" }, url: { type: "string" }, is_x402: { type: "boolean" },
              ready_to_pay: { type: "boolean" }, accepts: { type: "array", items: { type: "object" } },
              warnings: { type: "array", items: { type: "string" } },
            }, required: ["ok", "is_x402"],
          } } } },
          402: { description: "Payment Required" },
        },
      },
    },
    "/audit": {
      post: {
        operationId: "audit",
        summary: "Data-quality audit of CSV or JSON (hero product)",
        tags: ["Data", "Quality"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "49" }, protocols: [{ x402: {} }] },
        requestBody: {
          required: true,
          content: { "application/json": { schema: {
            type: "object",
            properties: {
              csv: { type: "string", description: "CSV text to audit (with a header row). Provide csv OR json." },
              json: { type: "array", items: { type: "object" }, description: "Array of flat JSON objects to audit. Provide csv OR json." },
              delimiter: { type: "string", description: "Optional explicit delimiter; omit to auto-sniff (, ; tab |)." },
            },
          } } },
        },
        responses: {
          200: { description: "Deterministic data-quality report", content: { "application/json": { schema: {
            type: "object", properties: {
              ok: { type: "boolean" }, input: { type: "string" },
              report: { type: "object", properties: {
                schema: { type: "string" }, score: { type: "number" }, grade: { type: "string" },
                readyToLoad: { type: "boolean" }, verdict: { type: "string" },
                shape: { type: "object" }, columns: { type: "array", items: { type: "object" } },
                findings: { type: "array", items: { type: "object" } },
              } },
            }, required: ["ok", "report"],
          } } } },
          402: { description: "Payment Required" },
        },
      },
    },
  },
}));
// x402 discovery manifest. Indexers (x402scan, Bazaar crawlers) probe this well-known
// path to enumerate a host's paid resources without guessing endpoints.
app.get("/.well-known/x402", (_req, res) => {
  const rails = [{ net: NET, payTo: PAY_TO }];
  if (SVM_PAY_TO) rails.push({ net: SVM_NET, payTo: SVM_PAY_TO });
  const resources = [];
  for (const r of [["csv_to_json", "Convert CSV text to typed JSON.", PRICE],
                   ["kpi_score", "Score weighted KPIs to 0..1.", PRICE],
                   ["csv_to_sql", "Convert CSV text to runnable SQL (postgres/mysql/sqlite).", SQL_PRICE],
                   ["x402_check", "Check an endpoint answers with a well-formed x402 402 challenge.", CHECK_PRICE],
                   ["audit", "Data-quality audit of CSV/JSON: score, grade, ready-to-load verdict, per-column findings.", AUDIT_PRICE]]) {
    for (const rail of rails) {
      resources.push({ resource: `${PUBLIC}/${r[0]}`, method: "POST", price: r[2],
                       network: rail.net, payTo: rail.payTo, description: r[1] });
    }
  }
  res.json({ x402Version: 1, resources, openapi: `${PUBLIC}/openapi.json`,
             contact: "farmmer938@gmail.com" });
});
// Serve control proofs (OpenTask supplier ownership, and any other well-known files)
// from disk under WELLKNOWN_DIR. The proof must be published verbatim at the exact
// challenge URL, so this route mirrors the request path onto the filesystem.
app.get(/^\/\.well-known\/.+/, (req, res) => {
  const rel = req.path.replace(/^\/\.well-known\//, "");
  const file = path.join(WELLKNOWN_DIR, path.normalize(rel));
  if (!file.startsWith(WELLKNOWN_DIR) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    return res.status(404).json({ error: "not found" });
  }
  res.type("application/json").send(fs.readFileSync(file));
});

app.get(/^\/work\/.+/, (req, res) => {
  const rel = req.path.replace(/^\/work\//, "");
  const file = path.join(WORK_DIR, path.normalize(rel));
  if (!file.startsWith(WORK_DIR) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    return res.status(404).json({ error: "not found" });
  }
  res.type(path.extname(file) || "text/plain").send(fs.readFileSync(file));
});

app.post("/csv_to_json", (req, res) => {
  try { res.json({ ok: true, rows: csvToJson(String(req.body?.csv ?? "")) }); }
  catch (e) { res.status(400).json({ ok: false, error: String(e.message || e) }); }
});
app.post("/csv_to_sql", (req, res) => {
  try {
    res.json({ ok: true, sql: csvToSql(String(req.body?.csv ?? ""), {
      dialect: req.body?.dialect, table: req.body?.table, delimiter: req.body?.delimiter,
    }) });
  } catch (e) { res.status(400).json({ ok: false, error: String(e.message || e) }); }
});
app.post("/kpi_score", (req, res) => {
  try { res.json({ ok: true, score: score(req.body?.metrics ?? []) }); }
  catch (e) { res.status(400).json({ ok: false, error: String(e.message || e) }); }
});
app.post("/x402_check", async (req, res) => {
  try {
    const r = await checkEndpoint(String(req.body?.url ?? ""), {
      method: req.body?.method, body: req.body?.body ?? null,
    });
    res.status(r.ok ? 200 : 400).json(r);
  } catch (e) { res.status(400).json({ ok: false, error: String(e.message || e) }); }
});
app.post("/audit", (req, res) => {
  try {
    const body = req.body || {};
    if (body.json !== undefined && body.json !== null) {
      return res.json({ ok: true, input: "json", report: auditJson(body.json) });
    }
    const csv = String(body.csv ?? "");
    if (!csv) return res.status(400).json({ ok: false, error: "provide csv (string) or json (array)" });
    res.json({ ok: true, input: "csv", report: auditCsv(csv, { delimiter: body.delimiter }) });
  } catch (e) { res.status(400).json({ ok: false, error: String(e.message || e) }); }
});

const PORT = process.env.PORT || 12000;
app.listen(PORT, () => console.log("AF cashier on :" + PORT + " payTo=" + PAY_TO + " price=" + PRICE));
