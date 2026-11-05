# AF DataBridge cashier (x402)

Sells the DataBridge tool per call over x402, settling **USDC on Base mainnet** straight
to AF's own wallet. No account, no API key, no human in the loop: an agent hits the
endpoint, gets `402 Payment Required` with the machine-readable price, signs an EIP-3009
USDC transfer, retries, and gets the result.

| Route | Price | What it does |
|---|---|---|
| `POST /csv_to_json` | $0.05 | CSV text -> typed JSON (delimiter sniffing, quoted fields, number/bool inference) |
| `POST /kpi_score` | $0.05 | Weighted KPI scoring to 0..100 with higher/lower-is-better normalisation |

- Facilitator: `https://facilitator.payai.network` (public, keyless, supports Base mainnet).
- `payTo` is injected at runtime from the `AF_MAIN_WALLET` secret; it is never committed.

## Run

```bash
npm install
AF_MAIN_WALLET='{"address":"0x..."}' bash run.sh    # or set AF_PAY_TO directly
```

`run.sh` is idempotent and self-healing: it reinstalls `node_modules` when the container
rootfs is wiped, then launches on `:12000` (AF's public ingress port).
