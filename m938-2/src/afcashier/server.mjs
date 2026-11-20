// AF x402 cashier — sells the DataBridge tool (CSV<->JSON + KPI scoring) per call,
// settles USDC on Base mainnet straight to AF's own wallet. No account, no API key,
// no human in the loop: an agent hits the endpoint, gets a 402 with the price,
// signs an EIP-3009 transfer, retries, and gets the result.
import express from "express";
import fs from "node:fs";
import { spawn } from "node:child_process";
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
import { verifySeller, DEMO_TARGETS } from "./sellerverify.mjs";
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
// Demand forensics: the only product here that checks a claim against settled money rather than
// against a catalogue's self-reported counters. Priced above the data tools because a buyer uses it
// to decide whether to spend hundreds of dollars with an unverified seller.
const VERIFY_PRICE = process.env.AF_VERIFY_PRICE || "$1";
// LLM inference: the one x402 category with proven repeat demand (a competing gateway took
// $11,500 from 18 buyers in 8 days — see artifacts/market_intel/x402_revenue_census.json).
// Agents buy it mid-task because they cannot finish without a completion. Priced under the
// incumbent so a cost-sensitive agent picks us.
const LLM_PRICE = process.env.AF_LLM_PRICE || "$0.01";
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
app.use(express.json({ limit: "2mb" }));
// A body-parser rejection is a 400 before any route runs, so it never reaches a handler and
// never reaches the demand log. Record it: a buyer whose payload we cannot parse is a lost sale.
app.use((err, req, res, next) => {
  if (err && (err.type === "entity.parse.failed" || err.status === 400)) {
    try { fs.appendFileSync("/workspace/.af-llm-reject.log",
      JSON.stringify({ ts: new Date().toISOString(), kind: "body_parse", path: req.path,
        method: req.method, ua: req.headers["user-agent"], ct: req.headers["content-type"],
        len: req.headers["content-length"], msg: String(err.message).slice(0, 200) }) + "\n"); } catch {}
    return res.status(400).json({ ok: false, error: "body must be valid JSON" });
  }
  next(err);
});

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
const DEMAND_PATHS = /^\/(csv_to_json|kpi_score|csv_to_sql|audit|x402_check|llm|seller_verify|trial\/.*)$/;
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


// LLM inference is the one x402 category with proven repeat demand, so the free trial here is
// deliberately capped rather than absent: an agent can prove the call works before it pays.
const LLM_BRIDGE = path.join(path.dirname(fileURLToPath(import.meta.url)), "llm_bridge.py");
const LLM_TRIAL_MAX_CHARS = Number(process.env.AF_LLM_TRIAL_MAX_CHARS || 2000);

function normalizeMessages(body) {
  if (!body || typeof body !== "object") return null;
  const candidates = [body.messages, body.body?.messages, body.input?.messages, body.input?.body?.messages];
  for (const c of candidates) if (Array.isArray(c) && c.length) return c;
  const text = body.prompt ?? body.input ?? body.body?.prompt;
  if (typeof text === "string" && text.trim()) return [{ role: "user", content: text }];
  return null;
}

function runLlm(messages, model, cb) {
  const payload = JSON.stringify({ messages, model });
  const child = spawn("python3", [LLM_BRIDGE], { stdio: ["pipe", "pipe", "pipe"] });
  let out = "", err = "";
  const timer = setTimeout(() => child.kill("SIGKILL"), 70_000);
  child.stdout.on("data", (d) => { out += d; });
  child.stderr.on("data", (d) => { err += d; });
  child.on("close", () => {
    clearTimeout(timer);
    let parsed = null;
    try { parsed = JSON.parse(out.trim() || "{}"); } catch { /* fall through */ }
    if (!parsed) return cb({ status: 502, body: { ok: false, error: "inference bridge failed", detail: (err || out).slice(0, 200) } });
    if (!parsed.ok) return cb({ status: 502, body: parsed });
    cb(null, parsed);
  });
  child.stdin.end(payload);
}

app.get("/llm/trial", (req, res) => {
  let messages = null;
  if (typeof req.query.messages === "string") {
    try { messages = JSON.parse(req.query.messages); } catch { /* fall through */ }
  }
  if (!Array.isArray(messages) && typeof req.query.prompt === "string" && req.query.prompt.trim()) {
    messages = [{ role: "user", content: req.query.prompt }];
  }
  if (!Array.isArray(messages) || !messages.length) {
    return res.status(400).json({ ok: false,
      error: "pass ?prompt=your question",
      example: `${PUBLIC}/llm/trial?prompt=What%20is%2017*23%3F` });
  }
  const chars = messages.reduce((n, m) => n + String(m?.content ?? "").length, 0);
  if (chars > LLM_TRIAL_MAX_CHARS) {
    return res.status(413).json({ ok: false, error: `trial caps the prompt at ${LLM_TRIAL_MAX_CHARS} chars`,
      ...upgrade("llm", LLM_PRICE) });
  }
  trialLog("llm", true, `${chars}ch`);
  runLlm(messages, req.query.model, (e, out) => {
    if (e) return res.status(e.status).json(e.body);
    res.json({ ...out, trial: true, upgrade: upgrade("llm", LLM_PRICE) });
  });
});

app.post("/llm/trial", (req, res) => {
  const messages = normalizeMessages(req.body);
  if (!messages) {
    return res.status(400).json({ ok: false, error: "send {messages:[{role,content}]} (or {prompt:'...'})" });
  }
  const chars = messages.reduce((n, m) => n + String(m?.content ?? "").length, 0);
  if (chars > LLM_TRIAL_MAX_CHARS) {
    return res.status(413).json({ ok: false, error: `trial caps the prompt at ${LLM_TRIAL_MAX_CHARS} chars`,
      ...upgrade("llm", LLM_PRICE) });
  }
  trialLog("llm", true, `${chars}ch`);
  runLlm(messages, req.body?.model, (e, out) => {
    if (e) return res.status(e.status).json(e.body);
    res.json({ ...out, trial: true, ...upgrade("llm", LLM_PRICE) });
  });
});

app.use(paymentMiddleware({
  "POST /llm": {
    accepts: acceptsFor(LLM_PRICE),
    resource: `${PUBLIC}/llm`,
    description: "OpenAI-compatible chat completion, paid per call in USDC on Base. Send {messages:[...]} and get {choices:[...]} back. No account, no API key, no rate-limit signup.",
    mimeType: "application/json",
    serviceName: "AF Inference",
    tags: ["llm", "ai", "chat", "inference", "openai-compatible", "completion"],
    extensions: declareDiscoveryExtension({
      method: "POST",
      bodyType: "json",
      input: { messages: [{ role: "user", content: "What is 17*23? Reply with the number only." }] },
      inputSchema: {
        type: "object",
        required: ["messages"],
        properties: {
          messages: {
            type: "array",
            description: "OpenAI chat messages, oldest first",
            items: {
              type: "object",
              required: ["role", "content"],
              properties: {
                role: { type: "string", enum: ["system", "user", "assistant"] },
                content: { type: "string" },
              },
            },
          },
          temperature: { type: "number", description: "Sampling temperature, 0-2" },
          max_tokens: { type: "integer", description: "Upper bound on reply length" },
        },
      },
      output: { example: { ok: true, model: "yqcloud", choices: [{ message: { role: "assistant", content: "391" } }] } },
    }),
  },
  "GET /llm": {
    accepts: acceptsFor(LLM_PRICE),
    resource: `${PUBLIC}/llm`,
    description: "OpenAI-compatible chat completion by GET: pass ?prompt=... (or ?messages=<url-encoded JSON>) and receive {choices:[...]}. Paid per call in USDC on Base, no account or API key.",
    mimeType: "application/json",
    serviceName: "AF Inference",
    tags: ["llm", "ai", "chat", "inference", "openai-compatible", "completion", "get"],
    extensions: declareDiscoveryExtension({
      method: "GET",
      input: { prompt: "What is 17*23? Reply with the number only." },
      inputSchema: {
        type: "object",
        properties: {
          prompt: { type: "string", description: "The question to answer" },
          messages: { type: "string", description: "Alternative: URL-encoded JSON array of chat messages" },
          model: { type: "string", description: "Optional model override" },
        },
      },
      output: { example: { ok: true, model: "yqcloud", choices: [{ message: { role: "assistant", content: "391" } }] } },
    }),
  },
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
  "POST /seller_verify": {
    accepts: acceptsFor(VERIFY_PRICE),
    resource: `${PUBLIC}/seller_verify`,
    description: "On-chain demand verification for any x402 seller: reads the seller's payTo wallet on Base and separates independent buyers from self-paid volume.",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["x402", "trust", "verification", "due-diligence", "onchain"],
    extensions: declareDiscoveryExtension({
      method: "POST",
      bodyType: "json",
      input: { url: "https://api.bitrefill.com/x402/invoice/pay" },
      inputSchema: {
        properties: {
          url: { type: "string", description: "The x402 seller endpoint to verify (http/https)." },
        },
        required: ["url"],
      },
      output: { example: { ok: true, schema: "af.seller_verify.v1", verdict: "REAL", genuineShare: 1 } },
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
  "GET /seller_verify": {
    accepts: acceptsFor(VERIFY_PRICE),
    resource: `${PUBLIC}/seller_verify`,
    description: "On-chain demand verification for any x402 seller. GET returns the contract; POST with {url} runs it. Separates independent buyers from self-paid volume by reading the seller's payTo wallet on Base.",
    mimeType: "application/json",
    serviceName: "AF DataBridge",
    tags: ["x402", "trust", "verification", "due-diligence", "onchain"],
    extensions: declareDiscoveryExtension({
      method: "GET",
      output: { example: { ok: true, endpoint: "/seller_verify", method: "POST", verdicts: ["REAL","MIXED","SELF_PAY","NEGLIGIBLE","NO_SETTLEMENT"] } },
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
    "/llm": {
      post: {
        operationId: "llm_chat_completion",
        summary: "OpenAI-compatible chat completion, paid per call in USDC on Base",
        description: "POST {messages:[{role,content}], model?} and receive {choices:[{message:{role,content}}]}. No account, no API key. Priced at $0.01 per call, settled in USDC on Base via x402.",
        tags: ["AI", "LLM", "Inference"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "0.01" }, protocols: [{ x402: {} }] },
        requestBody: {
          required: true,
          content: { "application/json": { schema: {
            type: "object", required: ["messages"], properties: {
              messages: { type: "array", items: { type: "object", properties: {
                role: { type: "string" }, content: { type: "string" } }, required: ["role", "content"] } },
              model: { type: "string" },
            },
          } } },
        },
        responses: {
          200: { description: "Completion", content: { "application/json": { schema: { type: "object" } } } },
          402: { description: "Payment Required" },
        },
      },
    },
    "/x402/leaderboard": {
      get: {
        operationId: "x402_revenue_leaderboard",
        summary: "Chain-truth revenue ranking of x402 sellers on Base (top 50, free sample)",
        description: "Every other x402 directory republishes what sellers claim. This ranks what their wallets actually received in USDC, measured from Transfer logs. The full 769-wallet census with per-wallet evidence is available through POST /seller_verify.",
        tags: ["Discovery", "MarketData"],
        responses: {
          200: { description: "Top-50 sellers by genuine on-chain USDC received", content: { "application/json": { schema: { type: "object" } } } },
        },
      },
    },
    "/seller_verify": {
      post: {
        operationId: "seller_verify",
        summary: "Verify whether an x402 seller's demand is real money or self-paid volume (on-chain)",
        tags: ["Trust", "Verification"],
        "x-payment-info": { price: { mode: "fixed", currency: "USD", amount: "1" }, protocols: [{ x402: {} }] },
        requestBody: {
          required: true,
          content: { "application/json": { schema: {
            type: "object", required: ["url"], properties: {
              url: { type: "string", description: "The x402 seller endpoint to verify." },
            },
          } } },
        },
        responses: {
          200: { description: "Verdict with the on-chain evidence behind it", content: { "application/json": { schema: {
            type: "object", properties: {
              ok: { type: "boolean" }, verdict: { type: "string" }, reason: { type: "string" },
              genuineShare: { type: "number" }, settled: { type: "object" },
              genuine: { type: "object" }, selfPay: { type: "object" },
              evidence: { type: "array", items: { type: "object" } },
            }, required: ["ok", "verdict"],
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
                   ["audit", "Data-quality audit of CSV/JSON: score, grade, ready-to-load verdict, per-column findings.", AUDIT_PRICE],
                   ["llm", "OpenAI-compatible chat completion. Send {messages:[...]}, get {choices:[...]} back. No account, no API key.", LLM_PRICE],
                   ["seller_verify", "Chain-truth revenue verification for an x402 seller URL: settled vs self-paid vs negligible, with evidence.", VERIFY_PRICE]]) {
    for (const rail of rails) {
      resources.push({ resource: `${PUBLIC}/${r[0]}`, method: "POST", price: r[2],
                       network: rail.net, payTo: rail.payTo, description: r[1] });
      // /llm also answers a paid GET (?prompt=...). Catalogues that recorded the verb they
      // first probed list it as GET, and a scout buys the verb the listing declares, so both
      // verbs must be payable and both must be published.
      if (r[0] === "llm") {
        resources.push({ resource: `${PUBLIC}/llm`, method: "GET", price: r[2],
                         network: rail.net, payTo: rail.payTo,
                         description: "Same completion over GET: ?prompt=... or ?messages=<url-encoded JSON>." });
      }
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
  csv_to_json: {
    price: PRICE, body: { csv: "a,b\n1,true", delimiter: "," },
    output: { ok: true, rows: [{ a: 1, b: true }] },
    requestSchema: { type: "object", required: ["csv"], properties: {
      csv: { type: "string", description: "CSV text with a header row" },
      delimiter: { type: "string", description: "Optional , ; | or tab; auto-sniffed when omitted" } } },
    responseSchema: { type: "object", properties: { ok: { type: "boolean" },
      rows: { type: "array", items: { type: "object" }, description: "Typed rows: numbers and booleans inferred" } } },
  },
  kpi_score: {
    price: PRICE, body: { metrics: [{ name: "uptime", value: 99.5, target: 99.9, direction: "higher", weight: 1 }] },
    output: { ok: true, score: { score: 0.99, breakdown: [] } },
    requestSchema: { type: "object", required: ["metrics"], properties: { metrics: { type: "array", items: {
      type: "object", required: ["name", "value", "target"], properties: {
        name: { type: "string" }, value: { type: "number" }, target: { type: "number" },
        direction: { type: "string", enum: ["higher", "lower"] }, weight: { type: "number" } } } } } },
    responseSchema: { type: "object", properties: { ok: { type: "boolean" }, score: { type: "object", properties: {
      score: { type: "number", description: "0..1 normalised" }, breakdown: { type: "array", items: { type: "object" } } } } } },
  },
  csv_to_sql: {
    price: SQL_PRICE, body: { csv: "name,age\nAnn,31", table: "people", dialect: "postgres" },
    output: { ok: true, sql: { dialect: "postgres", ddl: "CREATE TABLE ...", dml: "INSERT INTO ..." } },
    requestSchema: { type: "object", required: ["csv"], properties: { csv: { type: "string" },
      table: { type: "string" }, dialect: { type: "string", enum: ["postgres", "mysql", "sqlite"] },
      delimiter: { type: "string" } } },
    responseSchema: { type: "object", properties: { ok: { type: "boolean" }, sql: { type: "object", properties: {
      dialect: { type: "string" }, ddl: { type: "string" }, dml: { type: "string" },
      columns: { type: "array", items: { type: "object" } } } } } },
  },
  x402_check: {
    price: CHECK_PRICE, body: { url: "https://example.com/paid-route", method: "GET" },
    output: { ok: true, is_x402: true, ready_to_pay: true, accepts: [] },
    requestSchema: { type: "object", required: ["url"], properties: { url: { type: "string" },
      method: { type: "string", enum: ["GET", "POST"] }, body: { type: "object" } } },
    responseSchema: { type: "object", properties: { ok: { type: "boolean" }, is_x402: { type: "boolean" },
      ready_to_pay: { type: "boolean" }, accepts: { type: "array", items: { type: "object" } },
      warnings: { type: "array", items: { type: "string" } } } },
  },
  seller_verify: {
    price: VERIFY_PRICE, body: { url: "https://api.bitrefill.com/x402/invoice/pay" },
    output: { ok: true, schema: "af.seller_verify.v1", verdict: "REAL", genuineShare: 1,
      settled: { usdc: 18923.05, tx: 148, distinctSenders: 133 } },
    requestSchema: { type: "object", required: ["url"], properties: {
      url: { type: "string", description: "The x402 seller endpoint to verify, e.g. https://seller.example/paid-route" } } },
    responseSchema: { type: "object", properties: { ok: { type: "boolean" }, schema: { type: "string" },
      payTo: { type: "string" }, verdict: { type: "string", enum: ["REAL", "MIXED", "SELF_PAY", "NEGLIGIBLE", "NO_SETTLEMENT"] },
      reason: { type: "string" }, genuineShare: { type: "number" },
      settled: { type: "object" }, genuine: { type: "object" }, selfPay: { type: "object" },
      evidence: { type: "array", items: { type: "object" } } } },
  },
  audit: {
    price: AUDIT_PRICE, body: { csv: "id,name\n1,ann\n2,bob" },
    output: { ok: true, report: { schema: "af.data_audit.v1", score: 73, grade: "C", findings: [] } },
    requestSchema: { type: "object", properties: { csv: { type: "string" },
      json: { type: "array", items: { type: "object" } }, delimiter: { type: "string" } } },
    responseSchema: { type: "object", properties: { ok: { type: "boolean" }, report: { type: "object", properties: {
      schema: { type: "string" }, score: { type: "number" }, grade: { type: "string" },
      readyToLoad: { type: "boolean" }, findings: { type: "array", items: { type: "object" } } } } } },
  },
};
for (const [name, c] of Object.entries(CONTRACTS)) {
  app.get(`/${name}`, (req, res) => {
    res.json({
      ok: true, schema: "af.tool_contract.v1",
      endpoint: `/${name}`, method: "POST", contentType: "application/json",
      price: c.price, network: NET, payTo: PAY_TO, asset: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
      body: c.body, output: c.output,
      // A buyer's agent must be able to integrate from this one response: exact request
      // shape, exact response shape, and a runnable curl it can copy.
      requestSchema: c.requestSchema,
      responseSchema: c.responseSchema,
      curl: `curl -X POST ${PUBLIC}/${name} -H 'Content-Type: application/json' -d '${JSON.stringify(c.body)}'`,
      note: "POST this body to the same URL to run the tool. GET only describes it.",
    });
  });
}


// Free lead magnet: the only chain-truth revenue ranking of x402 sellers on Base. The full
// 769-wallet census (with per-wallet evidence) is the paid /seller_verify product; this top-50
// view exists so a prober can see the method works before paying for anything.
const LEADERBOARD_FILE = path.join(path.dirname(fileURLToPath(import.meta.url)), "x402_leaderboard.json");
app.get("/x402/leaderboard", (_req, res) => {
  try {
    res.json({ ok: true, schema: "af.x402.leaderboard.v1", ...JSON.parse(fs.readFileSync(LEADERBOARD_FILE, "utf8")) });
  } catch (e) {
    res.status(503).json({ ok: false, error: "leaderboard not built", detail: String(e.message || e).slice(0, 120) });
  }
});


// Paid LLM inference. The buyer pays first (middleware above), so a failed completion must
// not silently return 200 — it returns 502 with the provider error so the caller can retry
// or dispute, and the receipt still proves what they paid for.
app.get("/llm", (req, res) => {
  let messages = null;
  if (typeof req.query.messages === "string") {
    try { messages = JSON.parse(req.query.messages); } catch { /* fall through to prompt */ }
  }
  if (!Array.isArray(messages) && typeof req.query.prompt === "string" && req.query.prompt.trim()) {
    messages = [{ role: "user", content: req.query.prompt }];
  }
  if (!Array.isArray(messages) || !messages.length) {
    return res.status(400).json({ ok: false,
      error: "pass ?prompt=your question (or ?messages=<url-encoded JSON array>)",
      example: `${PUBLIC}/llm?prompt=What%20is%2017*23%3F` });
  }
  runLlm(messages, req.query.model, (e, out) => {
    if (e) return res.status(e.status).json(e.body);
    res.json(out);
  });
});

app.post("/llm", (req, res) => {
  const messages = normalizeMessages(req.body);
  if (!messages) {
    try { fs.appendFileSync("/workspace/.af-llm-reject.log",
      JSON.stringify({ ts: new Date().toISOString(), ct: req.headers["content-type"], ua: req.headers["user-agent"],
        raw: JSON.stringify(req.body).slice(0, 1500) }) + "\n"); } catch {}
    return res.status(400).json({ ok: false, error: "send {messages:[{role,content}]} (or {prompt:'...'})" });
  }
  runLlm(messages, req.body?.model, (e, out) => {
    if (e) return res.status(e.status).json(e.body);
    res.json(out);
  });
});

app.post("/seller_verify", async (req, res) => {
  const url = String(req.body?.url || "").trim();
  if (!/^https?:\/\//i.test(url)) {
    return res.status(400).json({ ok: false, error: "body.url must be an http(s) URL of an x402 seller" });
  }
  try {
    const out = await verifySeller(url);
    res.status(out.ok ? 200 : 422).json(out);
  } catch (e) {
    res.status(502).json({ ok: false, error: "verification failed", detail: String(e.message || e).slice(0, 160) });
  }
});

// Free sample: the method applied to three sellers whose answers are already known, so a buyer can
// judge the classifier before paying for it.
// Warming this at boot keeps the free sample instant: the on-chain walk takes ~18s cold, and a
// prober that waits that long decides the seller is dead.
let examplesCache = null;
async function warmExamples() {
  const rows = [];
  for (const t of DEMO_TARGETS) {
    try {
      const r = await verifySeller(t.url);
      rows.push({ label: t.label, url: t.url, verdict: r.verdict, genuineShare: r.genuineShare,
        settledUsdc: r.settled?.usdc, reason: r.reason });
    } catch (e) {
      rows.push({ label: t.label, url: t.url, verdict: "ERROR", reason: String(e.message || e).slice(0, 120) });
    }
  }
  examplesCache = rows;
  return rows;
}

app.get("/seller_verify/examples", async (_req, res) => {
  if (!examplesCache) {
    return res.json({ ok: true, schema: "af.seller_verify.examples.v1", warming: true,
      note: "First computation in progress; retry in a few seconds." });
  }
  res.json({ ok: true, schema: "af.seller_verify.examples.v1",
    note: "Free. POST /seller_verify with any seller URL to run the same check on one you care about.",
    examples: examplesCache });
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
warmExamples().then((r) => console.log("[seller_verify] examples warmed:", r.map((x) => x.verdict).join(","))).catch((e) => console.log("[seller_verify] warm failed:", String(e).slice(0, 120)));
