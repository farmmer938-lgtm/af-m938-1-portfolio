// AF x402 cashier — sells the DataBridge tool (CSV<->JSON + KPI scoring) per call,
// settles USDC on Base mainnet straight to AF's own wallet. No account, no API key,
// no human in the loop: an agent hits the endpoint, gets a 402 with the price,
// signs an EIP-3009 transfer, retries, and gets the result.
import express from "express";
import { paymentMiddleware, x402ResourceServer } from "@x402/express";
import { ExactEvmScheme } from "@x402/evm/exact/server";
import { HTTPFacilitatorClient } from "@x402/core/server";
import { csvToJson, score } from "./databridge.mjs";

const PAY_TO = process.env.AF_PAY_TO || "0xf3C99a6d6e7C6b2ae00b44dC42cC3eb7691D7702";
const PRICE = process.env.AF_PRICE || "$0.05";
const NET = "eip155:8453"; // Base mainnet

const app = express();
app.use(express.json());

const facilitator = new HTTPFacilitatorClient({ url: "https://facilitator.payai.network" });
const resourceServer = new x402ResourceServer(facilitator)
  .register(NET, new ExactEvmScheme());

app.use(paymentMiddleware({
  "POST /csv_to_json": {
    accepts: [{ scheme: "exact", price: PRICE, network: NET, payTo: PAY_TO }],
    description: "Convert CSV text to typed JSON (delimiter sniffing, quoted fields, number/bool inference).",
    mimeType: "application/json",
  },
  "POST /kpi_score": {
    accepts: [{ scheme: "exact", price: PRICE, network: NET, payTo: PAY_TO }],
    description: "Score weighted KPIs to 0..100 with higher/lower-is-better normalisation.",
    mimeType: "application/json",
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
