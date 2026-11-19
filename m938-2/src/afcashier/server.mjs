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
import { classifyIp, summarizeDemand } from "./demand.mjs";

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
const ART_DIR = process.env.AF_ART_DIR || "/workspace/project/AX_MASTER_BRAIN/artifacts/art_studio";
const ART_PRICE = process.env.AF_ART_PRICE || "$0.50";
const APK_PRICE = process.env.AF_APK_PRICE || "$0.90";
const THEME_PRICE = process.env.AF_THEME_PRICE || "$0.50";
const STICKER_PRICE = process.env.AF_STICKER_PRICE || "$0.25";
const WORK_DIR = process.env.AF_WORK_DIR
  || path.join(path.dirname(fileURLToPath(import.meta.url)), "work");

const app = express();
app.use(express.json());

// DEMAND MEASUREMENT (vendor quorum 2026-11-16, 5/5): AF could not tell whether any external
// buyer ever hit the paywall — the only traffic on record was AF's own tests. Every request
// to a paid or trial endpoint is logged with the client IP + user-agent so "is there real
// demand?" is a number, not a guess. Loopback/health hits are flagged so they never inflate it.
const DEMAND_LOG = process.env.AF_DEMAND_LOG || "/workspace/.af-demand.log";
function demandLog(req) {
  try {
    // Classify from the SOCKET address only. X-Forwarded-For is client-supplied and spoofable,
    // so trusting it would let anyone fake a public IP and fake "demand".
    const ip = req.socket?.remoteAddress || "";
    // The platform ingress proxies EVERY external request as a private 10.x address, so a socket
    // address alone cannot tell a real buyer from internal traffic. The unambiguous external
    // signal is a PAYMENT ATTEMPT: x402 v2 clients send PAYMENT-SIGNATURE when they try to pay.
    const payAttempt = Boolean(req.headers["payment-signature"] || req.headers["x-payment"]);
    fs.appendFileSync(DEMAND_LOG, JSON.stringify({
      ts: new Date().toISOString(), method: req.method, path: req.path,
      ip, cls: classifyIp(ip), pay: payAttempt,
      ua: String(req.headers["user-agent"] || "").slice(0, 160),
    }) + "\n");
  } catch { /* logging must never break the response */ }
}
const DEMAND_PATHS = /^\/(csv_to_json|kpi_score|csv_to_sql|audit|x402_check|trial\/.*)$/;
app.use((req, _res, next) => { if (DEMAND_PATHS.test(req.path)) demandLog(req); next(); });

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

// ART STUDIO — free shop window, paid full-resolution delivery.
// The thumbnails and gallery are free on purpose: a buyer must be able to see the work
// before paying. Only the 4096px master file sits behind the x402 paywall.
const ART_THUMB = /^\/art\/([a-z]+)\/([a-z0-9-]+)\/thumb\.png$/;
const ART_FULL = /^\/art\/([a-z]+)\/([a-z0-9-]+)\/art\.png$/;
const artFile = (coll, slug, name) => {
  const f = path.join(ART_DIR, coll, slug, name);
  if (!f.startsWith(ART_DIR) || !fs.existsSync(f) || !fs.statSync(f).isFile()) return null;
  return f;
};
app.get("/art", (_req, res) => {
  const f = path.join(ART_DIR, "gallery", "index.html");
  if (!fs.existsSync(f)) return res.status(404).send("gallery not built");
  res.type("text/html").send(fs.readFileSync(f));
});
app.get("/art/catalog.json", (_req, res) => {
  const f = path.join(ART_DIR, "gallery", "index.json");
  if (!fs.existsSync(f)) return res.status(404).json({ error: "catalog not built" });
  res.type("application/json").send(fs.readFileSync(f));
});
const ART_FREE = /^\/art\/(themes|stickers)\/([a-z0-9-]+)\/(preview\.png|[a-z0-9-]+-thumb\.png)$/;
// K's own copy. A token in the path keeps it out of crawlers without an account system;
// the file set is the same one the paid routes serve, so nothing is duplicated.
const K_TOKEN = process.env.AF_K_TOKEN || "k-7f3a91c4";
app.get("/k/:token/art/themes/:slug/:name", (req, res) => {
  if (req.params.token !== K_TOKEN) return res.status(404).json({ error: "not found" });
  const f = artFile("themes", req.params.slug, req.params.name);
  if (!f) return res.status(404).json({ error: "not found" });
  res.type(req.params.name.endsWith(".json") ? "application/json" : "image/png")
     .setHeader("X-Art-License", "AF Commercial License v1");
  res.send(fs.readFileSync(f));
});
app.get("/k/:token/art/stickers/:src/:name", (req, res) => {
  if (req.params.token !== K_TOKEN) return res.status(404).json({ error: "not found" });
  const f = artFile("stickers", req.params.src, req.params.name);
  if (!f) return res.status(404).json({ error: "not found" });
  res.type("image/png").send(fs.readFileSync(f));
});
app.get("/k/:token/app", (req, res) => {
  if (req.params.token !== K_TOKEN) return res.status(404).json({ error: "not found" });
  const f = path.join(ART_DIR, "gallery", "app.html");
  if (!fs.existsSync(f)) return res.status(404).send("not built");
  res.type("text/html").send(fs.readFileSync(f));
});
app.get("/k/:token", (req, res) => {
  if (req.params.token !== K_TOKEN) return res.status(404).json({ error: "not found" });
  const f = path.join(ART_DIR, "gallery", "k.html");
  if (!fs.existsSync(f)) return res.status(404).send("not built");
  res.type("text/html").send(fs.readFileSync(f));
});
// No-install path: a JPEG saves straight into the phone's Photos with zero OS warnings.
// This exists because sideloading an APK triggers scary Play Protect dialogs, and K's
// directive is no upfront spend, so Play Store distribution ($25) is off the table.
app.get("/k/:token/wall", (req, res) => {
  if (req.params.token !== K_TOKEN) return res.status(404).json({ error: "not found" });
  const f = path.join(ART_DIR, "gallery", "wall.html");
  if (!fs.existsSync(f)) return res.status(404).send("not built");
  res.type("text/html").send(fs.readFileSync(f));
});
app.get("/k/:token/img/:name", (req, res) => {
  if (req.params.token !== K_TOKEN) return res.status(404).json({ error: "not found" });
  const name = String(req.params.name).replace(/[^a-z0-9.-]/gi, "");
  if (!name.endsWith(".jpg")) return res.status(404).json({ error: "not found" });
  const f = path.join(ART_DIR, "mobile_jpg", name);
  if (!fs.existsSync(f)) return res.status(404).json({ error: "not built" });
  res.setHeader("Content-Type", "image/jpeg");
  res.setHeader("Cache-Control", "public, max-age=86400");
  res.send(fs.readFileSync(f));
});

// APK delivery. Content-Disposition: attachment is the whole point — without it Android
// Chrome opens a viewer instead of saving the file, and the buyer has to hunt in Downloads.
app.get("/k/:token/app/:name", (req, res) => {
  if (req.params.token !== K_TOKEN) return res.status(404).json({ error: "not found" });
  const name = String(req.params.name).replace(/[^a-z0-9.-]/gi, "");
  if (!name.endsWith(".apk")) return res.status(404).json({ error: "not found" });
  const f = path.join(ART_DIR, "apk", name);
  if (!fs.existsSync(f)) return res.status(404).json({ error: "not built" });
  res.setHeader("Content-Type", "application/vnd.android.package-archive");
  res.setHeader("Content-Disposition", `attachment; filename="${name}"`);
  res.setHeader("Content-Length", String(fs.statSync(f).size));
  fs.createReadStream(f).pipe(res);
});
app.get("/art/themes", (_req, res) => {
  const f = path.join(ART_DIR, "gallery", "themes.html");
  if (!fs.existsSync(f)) return res.status(404).send("storefront not built");
  res.type("text/html").send(fs.readFileSync(f));
});
app.get(ART_FREE, (req, res) => {
  const f = artFile(req.params[0], req.params[1], req.params[2]);
  if (!f) return res.status(404).json({ error: "not found" });
  res.type("image/png").send(fs.readFileSync(f));
});
app.get(ART_THUMB, (req, res) => {
  const f = artFile(req.params[0], req.params[1], "thumb.png");
  if (!f) return res.status(404).json({ error: "not found" });
  res.type("image/png").send(fs.readFileSync(f));
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
  "GET /art/:collection/:slug/art.png": {
    accepts: acceptsFor(ART_PRICE),
    resource: `${PUBLIC}/art/:collection/:slug/art.png`,
    description: "Full-resolution 4096x4096 PNG master of an original algorithmic artwork, with commercial licence.",
    mimeType: "image/png",
    serviceName: "AF Art Studio",
    tags: ["art", "image", "generative", "print", "license"],
    extensions: declareDiscoveryExtension({
      method: "GET",
      output: { example: { note: "binary PNG image, 4096x4096" } },
    }),
  },
  "GET /art/themes/*": {
    accepts: acceptsFor(THEME_PRICE),
    resource: `${PUBLIC}/art/themes/*`,
    description: "Phone theme bundle: 2160x4680 wallpaper, lockscreen, adaptive icon layers, accent palette. Commercial licence.",
    mimeType: "image/png",
    serviceName: "AF Art Studio",
    tags: ["theme", "wallpaper", "android", "phone", "art"],
    extensions: declareDiscoveryExtension({ method: "GET", output: { example: { note: "PNG or theme.json" } } }),
  },
  "GET /art/wallpapers/*": {
    accepts: acceptsFor(APK_PRICE),
    resource: `${PUBLIC}/art/wallpapers/*`,
    description: "All 12 phone themes at full 2160x4680 master resolution, one ZIP, no app install needed. Commercial licence.",
    mimeType: "application/zip",
    serviceName: "AF Art Studio",
    tags: ["wallpaper", "theme", "android", "zip", "art"],
    extensions: declareDiscoveryExtension({ method: "GET", output: { example: { note: "ZIP of PNG masters" } } }),
  },
  "GET /art/app/*": {
    accepts: acceptsFor(APK_PRICE),
    resource: `${PUBLIC}/art/app/*`,
    description: "AF Art Studio Android app: 12 phone themes bundled offline, one-tap wallpaper set. Commercial licence.",
    mimeType: "application/vnd.android.package-archive",
    serviceName: "AF Art Studio",
    tags: ["android", "app", "apk", "theme", "wallpaper"],
    extensions: declareDiscoveryExtension({ method: "GET", output: { example: { note: "signed APK" } } }),
  },
  "GET /art/stickers/*": {
    accepts: acceptsFor(STICKER_PRICE),
    resource: `${PUBLIC}/art/stickers/*`,
    description: "Transparent PNG sticker (512px, real alpha) cut from an original artwork. Commercial licence.",
    mimeType: "image/png",
    serviceName: "AF Art Studio",
    tags: ["sticker", "png", "transparent", "art", "chat"],
    extensions: declareDiscoveryExtension({ method: "GET", output: { example: { note: "512px RGBA PNG" } } }),
  },
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
  "GET /csv_to_json": {
    accepts: acceptsFor(),
    resource: `${PUBLIC}/csv_to_json`,
    description: "Convert CSV text to typed JSON (delimiter sniffing, quoted fields, number/bool inference). GET returns this endpoint's machine-readable contract (method, input schema, example, price); send POST with a JSON body to run it.",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["csv","json","data","etl","converter"],
    extensions: declareDiscoveryExtension({
      method: "GET",
      output: { example: { ok: true, endpoint: "/csv_to_json", method: "POST", inputSchema: {}, example: {} } },
    }),
  },
  "GET /kpi_score": {
    accepts: acceptsFor(),
    resource: `${PUBLIC}/kpi_score`,
    description: "Score weighted KPIs to 0..100 with higher/lower-is-better normalisation. GET returns this endpoint's machine-readable contract (method, input schema, example, price); send POST with a JSON body to run it.",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["kpi","metrics","scoring","analytics"],
    extensions: declareDiscoveryExtension({
      method: "GET",
      output: { example: { ok: true, endpoint: "/kpi_score", method: "POST", inputSchema: {}, example: {} } },
    }),
  },
  "GET /csv_to_sql": {
    accepts: acceptsFor(SQL_PRICE),
    resource: `${PUBLIC}/csv_to_sql`,
    description: "Convert CSV text to runnable SQL: CREATE TABLE with inferred column types plus INSERT statements. GET returns this endpoint's machine-readable contract (method, input schema, example, price); send POST with a JSON body to run it.",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["csv","sql","etl","database","schema","ddl"],
    extensions: declareDiscoveryExtension({
      method: "GET",
      output: { example: { ok: true, endpoint: "/csv_to_sql", method: "POST", inputSchema: {}, example: {} } },
    }),
  },
  "GET /x402_check": {
    accepts: acceptsFor(CHECK_PRICE),
    resource: `${PUBLIC}/x402_check`,
    description: "Check whether an endpoint answers with a well-formed x402 402 challenge before you pay it. GET returns this endpoint's machine-readable contract (method, input schema, example, price); send POST with a JSON body to run it.",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["x402","endpoint","verify","health","payment","discovery"],
    extensions: declareDiscoveryExtension({
      method: "GET",
      output: { example: { ok: true, endpoint: "/x402_check", method: "POST", inputSchema: {}, example: {} } },
    }),
  },
  "GET /audit": {
    accepts: acceptsFor(AUDIT_PRICE),
    resource: `${PUBLIC}/audit`,
    description: "Data-quality audit: deterministic report (shape, types, nulls, duplicates, outliers) with a 0-100 score. GET returns this endpoint's machine-readable contract (method, input schema, example, price); send POST with a JSON body to run it.",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["data","quality","audit","csv","json","validation","etl"],
    extensions: declareDiscoveryExtension({
      method: "GET",
      output: { example: { ok: true, endpoint: "/audit", method: "POST", inputSchema: {}, example: {} } },
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

// Demand truth: how many EXTERNAL (non-loopback) hits each paid/trial endpoint has had.
// A number > 0 with a real 402 → there is demand; 0 after distribution → the problem is
// demand, not visibility. This is the falsification test, served as data.
app.get("/demand.json", (_req, res) => {
  let rows = [];
  try { rows = fs.readFileSync(DEMAND_LOG, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)); }
  catch { rows = []; }
  // Legacy rows (before the socket-address fix) only carried a boolean `local`; classify them
  // honestly rather than letting them masquerade as demand.
  rows = rows.map((r) => r.cls ? r : { ...r, cls: r.local ? "loopback" : classifyIp(r.ip) });
  const summary = summarizeDemand(rows);
  const payAttempts = rows.filter((r) => r.pay).length;
  res.json({
    note: "The platform ingress proxies every external request as a private 10.x address, so a "
      + "socket address cannot separate a real buyer from internal traffic. The one unambiguous "
      + "external signal is a PAYMENT ATTEMPT (x402 PAYMENT-SIGNATURE header). Treat "
      + "external_hits as a weak hint and payment_attempts as the real test of demand.",
    ...summary,
    payment_attempts: payAttempts,
    demand_verdict: payAttempts > 0 ? "PAYMENT ATTEMPTED (real demand)" : "NO PAYMENT ATTEMPT (demand unproven)",
  });
});

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
    "/art/themes/{slug}/{file}": {
      get: {
        operationId: "art_theme_file",
        summary: "Phone theme file: 2160x4680 wallpaper, lockscreen, adaptive icon layer, or theme.json",
        tags: ["Art"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.50" }, protocols: [{ x402: {} }] },
        parameters: [
          { name: "slug", in: "path", required: true, schema: { type: "string", example: "orbits-obsidian-01" } },
          { name: "file", in: "path", required: true, schema: { type: "string", example: "wallpaper.png",
            enum: ["wallpaper.png", "wallpaper-1080x2340.png", "lockscreen.png", "icon-background.png", "icon-foreground.png", "theme.json"] } },
        ],
        responses: { "200": { description: "The requested PNG or theme.json (commercial licence)",
          content: { "image/png": { schema: { type: "string", format: "binary" } },
                     "application/json": { schema: { type: "object" } } } },
          "402": { description: "Payment Required" } },
      },
    },
    "/art/wallpapers/{name}": {
      get: {
        operationId: "art_wallpapers_zip",
        summary: "All 12 phone themes at full 2160x4680 master resolution in one ZIP (no app needed)",
        tags: ["Art"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.90" }, protocols: [{ x402: {} }] },
        parameters: [
          { name: "name", in: "path", required: true, schema: { type: "string",
            enum: ["af-art-studio-everything.zip"] } },
        ],
        responses: { "200": { description: "ZIP archive of PNG masters",
          content: { "application/zip": { schema: { type: "string", format: "binary" } } } },
          "402": { description: "Payment Required" } },
      },
    },
    "/art/app/{name}": {
      get: {
        operationId: "art_app_android",
        summary: "AF Art Studio Android app: 12 phone themes bundled offline, one-tap wallpaper set",
        tags: ["Art"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.90" }, protocols: [{ x402: {} }] },
        parameters: [
          { name: "name", in: "path", required: true, schema: { type: "string",
            enum: ["af-art-studio-full.apk", "af-art-studio-free.apk"] } },
        ],
        responses: { "200": { description: "Signed Android APK",
          content: { "application/vnd.android.package-archive": { schema: { type: "string", format: "binary" } } } },
          "402": { description: "Payment Required" } },
      },
    },
    "/art/stickers/{slug}/{file}": {
      get: {
        operationId: "art_sticker",
        summary: "Transparent 512px PNG sticker (real alpha channel) cut from an original artwork",
        tags: ["Art"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.25" }, protocols: [{ x402: {} }] },
        parameters: [
          { name: "slug", in: "path", required: true, schema: { type: "string", example: "orbits-obsidian-01" } },
          { name: "file", in: "path", required: true, schema: { type: "string", example: "orbits-obsidian-01-circle.png" } },
        ],
        responses: { "200": { description: "RGBA PNG sticker",
          content: { "image/png": { schema: { type: "string", format: "binary" } } } },
          "402": { description: "Payment Required" } },
      },
    },
    "/art/{collection}/{slug}/art.png": {
      get: {
        operationId: "art_master",
        summary: "Full-resolution 4096x4096 PNG master of an original algorithmic artwork",
        tags: ["Art"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.50" }, protocols: [{ x402: {} }] },
        parameters: [
          { name: "collection", in: "path", required: true, schema: { type: "string", example: "orbits" } },
          { name: "slug", in: "path", required: true, schema: { type: "string", example: "orbits-obsidian-01" } },
        ],
        responses: { "200": { description: "4096x4096 PNG master (commercial licence)",
          content: { "image/png": { schema: { type: "string", format: "binary" } } } },
          "402": { description: "Payment Required" } },
      },
    },
    "/csv_to_json": {
      get: {
        operationId: "csv_to_json_contract",
        summary: "Machine-readable contract for /csv_to_json (what to POST, what you get back)",
        tags: ["Discovery"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.05" }, protocols: [{ x402: {} }] },
        responses: {
          200: { description: "Contract: method, body example, output example, price, network", content: { "application/json": { schema: { type: "object" } } } },
          402: { description: "Payment Required" },
        },
      },
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
      get: {
        operationId: "kpi_score_contract",
        summary: "Machine-readable contract for /kpi_score (what to POST, what you get back)",
        tags: ["Discovery"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.05" }, protocols: [{ x402: {} }] },
        responses: {
          200: { description: "Contract: method, body example, output example, price, network", content: { "application/json": { schema: { type: "object" } } } },
          402: { description: "Payment Required" },
        },
      },
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
      get: {
        operationId: "csv_to_sql_contract",
        summary: "Machine-readable contract for /csv_to_sql (what to POST, what you get back)",
        tags: ["Discovery"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.08" }, protocols: [{ x402: {} }] },
        responses: {
          200: { description: "Contract: method, body example, output example, price, network", content: { "application/json": { schema: { type: "object" } } } },
          402: { description: "Payment Required" },
        },
      },
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
      get: {
        operationId: "x402_check_contract",
        summary: "Machine-readable contract for /x402_check (what to POST, what you get back)",
        tags: ["Discovery"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.08" }, protocols: [{ x402: {} }] },
        responses: {
          200: { description: "Contract: method, body example, output example, price, network", content: { "application/json": { schema: { type: "object" } } } },
          402: { description: "Payment Required" },
        },
      },
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
      get: {
        operationId: "audit_contract",
        summary: "Machine-readable contract for /audit (what to POST, what you get back)",
        tags: ["Discovery"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "49" }, protocols: [{ x402: {} }] },
        responses: {
          200: { description: "Contract: method, body example, output example, price, network", content: { "application/json": { schema: { type: "object" } } } },
          402: { description: "Payment Required" },
        },
      },
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
  for (const rail of rails) {
    for (const a of [
      [`${PUBLIC}/art/{collection}/{slug}/art.png`, ART_PRICE,
       "Full-resolution 4096x4096 PNG master of an original algorithmic artwork (commercial licence)."],
      [`${PUBLIC}/art/themes/{slug}/{file}`, THEME_PRICE,
       "Phone theme bundle: 2160x4680 wallpaper, lockscreen, adaptive icon layers, accent palette."],
      [`${PUBLIC}/art/wallpapers/{name}`, APK_PRICE,
       "All 12 phone themes, full 2160x4680 masters, one ZIP. No app needed."],
      [`${PUBLIC}/art/app/{name}`, APK_PRICE,
       "AF Art Studio Android app (APK): 12 phone themes offline, one-tap wallpaper set."],
      [`${PUBLIC}/art/stickers/{slug}/{file}`, STICKER_PRICE,
       "Transparent 512px PNG sticker (real alpha channel) cut from an original artwork."],
    ]) {
      resources.push({ resource: a[0], method: "GET", price: a[1],
                       network: rail.net, payTo: rail.payTo, description: a[2] });
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

// Discovery contract. Probers and buyers probe with GET before they pay; answering 404 made
// every catalogue treat AF as a dead seller. GET is a real, priced resource that returns the
// endpoint's contract, so a GET probe always meets a well-formed 402 and can quote AF.
const CONTRACTS = {
  csv_to_json: { price: PRICE, body: { csv: "a,b\n1,true", delimiter: "," },
    output: { ok: true, rows: [{ a: 1, b: true }] } },
  kpi_score: { price: PRICE, body: { metrics: [{ name: "uptime", value: 99.5, target: 99.9, direction: "higher", weight: 1 }] },
    output: { ok: true, score: { score: 0.99, breakdown: [] } } },
  csv_to_sql: { price: SQL_PRICE, body: { csv: "name,age\nAnn,31", table: "people", dialect: "postgres" },
    output: { ok: true, sql: { dialect: "postgres", ddl: "CREATE TABLE ...", dml: "INSERT INTO ..." } } },
  x402_check: { price: CHECK_PRICE, body: { url: "https://example.com/paid-route", method: "GET" },
    output: { ok: true, is_x402: true, ready_to_pay: true, accepts: [] } },
  audit: { price: AUDIT_PRICE, body: { csv: "id,name\n1,ann\n2,bob" },
    output: { ok: true, report: { schema: "af.data_audit.v1", score: 73, grade: "C", findings: [] } } },
};
for (const [name, c] of Object.entries(CONTRACTS)) {
  app.get(`/${name}`, (req, res) => {
    res.json({
      ok: true, endpoint: `/${name}`, method: "POST", contentType: "application/json",
      price: c.price, network: NET, payTo: PAY_TO,
      body: c.body, output: c.output,
      note: "POST this body to the same URL to run the tool. GET only describes it.",
    });
  });
}

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

const ART_THEME_PAID = /^\/art\/themes\/([a-z0-9-]+)\/(wallpaper|wallpaper-1080x2340|lockscreen|icon-background|icon-foreground|theme)(\.png|\.json)?$/;
app.get(ART_THEME_PAID, (req, res) => {
  const name = req.params[1].endsWith(".json") ? "theme.json" : `${req.params[1]}.png`;
  const f = artFile("themes", req.params[0], name);
  if (!f) return res.status(404).json({ error: "not found", asked: name });
  res.type(name.endsWith(".json") ? "application/json" : "image/png");
  res.setHeader("X-Art-License", "AF Commercial License v1 - unlimited commercial use");
  res.send(fs.readFileSync(f));
});

app.get(ART_FULL, (req, res) => {
  const f = artFile(req.params[0], req.params[1], "art.png");
  if (!f) return res.status(404).json({ error: "not found" });
  const meta = artFile(req.params[0], req.params[1], "meta.json");
  res.type("image/png");
  res.setHeader("X-Art-License", "AF Commercial License v1 - unlimited commercial use");
  if (meta) {
    // HTTP headers are latin-1 only; the metadata carries em dashes and a licence blurb.
    const safe = JSON.stringify(JSON.parse(fs.readFileSync(meta, "utf8")))
      .replace(/[^\x20-\x7E]/g, "-").slice(0, 900);
    res.setHeader("X-Art-Meta", safe);
  }
  res.send(fs.readFileSync(f));
});

const ART_STICKER_PAID = /^\/art\/stickers\/([a-z0-9-]+)\/([a-z0-9-]+\.png)$/;
app.get(ART_STICKER_PAID, (req, res) => {
  const f = artFile("stickers", req.params[0], req.params[1]);
  if (!f) return res.status(404).json({ error: "not found" });
  res.type("image/png");
  res.setHeader("X-Art-License", "AF Commercial License v1 - unlimited commercial use");
  res.send(fs.readFileSync(f));
});

// The paid APK. A buyer pays once and gets the installable app, which is the friction-free path
// K asked for: no per-file downloads, no moving images through Photos.
app.get("/art/app/:name", (req, res) => {
  const name = String(req.params.name).replace(/[^a-z0-9.-]/gi, "");
  if (!name.endsWith(".apk")) return res.status(404).json({ error: "not found" });
  const f = path.join(ART_DIR, "apk", name);
  if (!fs.existsSync(f)) return res.status(404).json({ error: "not built" });
  res.setHeader("Content-Type", "application/vnd.android.package-archive");
  res.setHeader("Content-Disposition", `attachment; filename="${name}"`);
  res.setHeader("Content-Length", String(fs.statSync(f).size));
  res.setHeader("X-Art-License", "AF Commercial License v1 - unlimited commercial use");
  fs.createReadStream(f).pipe(res);
});

// Premium no-install delivery: the full 2160x4680 masters as one ZIP, paid, no app involved.
app.get("/art/wallpapers/:name", (req, res) => {
  const name = String(req.params.name).replace(/[^a-z0-9.-]/gi, "");
  if (!name.endsWith(".zip")) return res.status(404).json({ error: "not found" });
  const f = path.join(ART_DIR, "bundles", name);
  if (!fs.existsSync(f)) return res.status(404).json({ error: "not built" });
  res.setHeader("Content-Type", "application/zip");
  res.setHeader("Content-Disposition", `attachment; filename="${name}"`);
  res.setHeader("Content-Length", String(fs.statSync(f).size));
  res.setHeader("X-Art-License", "AF Commercial License v1 - unlimited commercial use");
  fs.createReadStream(f).pipe(res);
});

// Registered last on purpose: GET (paywalled contract) and POST (paid tool) must match first.
// A prober that gets 404 concludes the seller is gone; 405 proves the resource exists.
for (const name of Object.keys(CONTRACTS)) {
  app.all(`/${name}`, (req, res) => {
    res.set("Allow", "GET, HEAD, POST").status(405).json({
      ok: false, error: "method not allowed", endpoint: `/${name}`,
      allowed: ["GET", "HEAD", "POST"], hint: "GET describes the tool, POST runs it",
    });
  });
}

const PORT = process.env.PORT || 12000;
app.listen(PORT, () => console.log("AF cashier on :" + PORT + " payTo=" + PAY_TO + " price=" + PRICE));
