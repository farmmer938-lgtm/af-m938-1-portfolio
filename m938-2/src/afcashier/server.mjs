// AF x402 cashier — sells the DataBridge tool (CSV<->JSON + KPI scoring) per call,
// settles USDC on Base mainnet straight to AF's own wallet. No account, no API key,
// no human in the loop: an agent hits the endpoint, gets a 402 with the price,
// signs an EIP-3009 transfer, retries, and gets the result.
import express from "express";
import { paymentMiddleware, x402ResourceServer } from "@x402/express";
import { ExactEvmScheme } from "@x402/evm/exact/server";
import { HTTPFacilitatorClient } from "@x402/core/server";
import { bazaarResourceServerExtension, declareDiscoveryExtension } from "@x402/extensions/bazaar";
import { csvToJson, score } from "./databridge.mjs";

const PAY_TO = process.env.AF_PAY_TO || "0xf3C99a6d6e7C6b2ae00b44dC42cC3eb7691D7702";
const PRICE = process.env.AF_PRICE || "$0.05";
const NET = "eip155:8453"; // Base mainnet
// Public base URL, used as the canonical resource id that CDP Bazaar indexes.
const PUBLIC = process.env.AF_PUBLIC_URL || "https://work-1-mbagwhmoyaqtbyvu.prod-runtime.all-hands.dev";

const app = express();
app.use(express.json());

const facilitator = new HTTPFacilitatorClient({ url: "https://facilitator.payai.network" });
const resourceServer = new x402ResourceServer(facilitator)
  .register(NET, new ExactEvmScheme())
  .registerExtension(bazaarResourceServerExtension);

app.use(paymentMiddleware({
  "POST /csv_to_json": {
    accepts: [{ scheme: "exact", price: PRICE, network: NET, payTo: PAY_TO }],
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
    accepts: [{ scheme: "exact", price: PRICE, network: NET, payTo: PAY_TO }],
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
}, resourceServer));

app.get("/", (_req, res) => res.json({
  name: "AF DataBridge (x402)",
  tools: { "POST /csv_to_json": PRICE, "POST /kpi_score": PRICE },
  network: NET, payTo: PAY_TO,
}));
app.post("/csv_to_json", (req, res) => {
  try { res.json({ ok: true, rows: csvToJson(String(req.body?.csv ?? "")) }); }
  catch (e) { res.status(400).json({ ok: false, error: String(e.message || e) }); }
});
app.post("/kpi_score", (req, res) => {
  try { res.json({ ok: true, score: score(req.body?.metrics ?? []) }); }
  catch (e) { res.status(400).json({ ok: false, error: String(e.message || e) }); }
});

const PORT = process.env.PORT || 12000;
app.listen(PORT, () => console.log("AF cashier on :" + PORT + " payTo=" + PAY_TO + " price=" + PRICE));
