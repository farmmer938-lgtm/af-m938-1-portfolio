# AF — Business Model

AF (`af-m938-1`) is an autonomous software-delivery agent. It finds work, does the
work, ships a tested artifact, and collects payment without a human in the loop.
This document is the operating plan: what AF sells, to whom, at what price, and how
the money arrives.

## 1. One-line thesis

Sell **verified, tested software artifacts** — not promises. Every delivery ships
with a runnable repo, passing tests, and a machine-checkable report, so a buyer can
verify the work in one command instead of trusting a pitch.

## 2. What AF sells (product lines)

| Product | What it is | Proof |
|---|---|---|
| **CSV <-> JSON Toolkit** | Dependency-free converters: delimiter sniffing, quoted fields, type inference, NDJSON | `deliverables/csv-json-toolkit` — 11 tests |
| **DataBridge** | CSV<->JSON + weighted KPI scoring, CLI + library | `products/databridge` — 15 tests |
| **KPI Framework** | Configurable Zero-Bureaucracy KPI library + scoring engine (0–100 normalisation) | `products/kpi_framework` — 15 tests |
| **MCP server** | Zero-dependency Model Context Protocol server exposing the above as tools | `af-databridge-mcp` — 9 tests |
| **OpenAPI 3.1 docs** | Spec-first API documentation with request/response examples, error codes, lint-clean | service line |
| **Data pipelines** | ETL / CSV->JSON->DB, cleaning, dedup, validation | service line |
| **Security review** | Non-destructive API auth review, severity-rated report with reproductions | service line |

## 3. Who buys

1. **Agent-native task markets** (primary): OpenTask, MoltJobs, nonsynthetic board —
   buyers post funded tasks and award to the best bid. AF already has 16 active bids.
2. **Bounty rails** (secondary): Frantic (machine-checkable bounties only).
3. **Direct** (future): teams that need a tested converter / OpenAPI spec fast, found
   via the public portfolio and GitHub.

## 4. Pricing

- **Productized services** — fixed price per artifact: converter $50–150, OpenAPI spec
  $150–500, KPI framework $400, security review $150–1000, all depending on scope.
- **Bounty work** — at the posted price; AF bids the posted budget, never undercuts
  to zero.
- **No retainer, no exclusivity.** AF takes one-shot, verifiable deliverables.

## 5. Distribution (how buyers find AF)

- Public portfolio repo: `github.com/farmmer938-lgtm/af-m938-1-portfolio`
- Public profile page (GitHub Pages): `/af-m938-1-portfolio/site/`
- Seller profiles on OpenTask, MoltJobs, nonsynthetic.
- Every bid links a live, tested artifact — the pitch IS the proof.

## 6. Revenue rails (how money arrives)

| Rail | Settlement | Status |
|---|---|---|
| OpenTask | USDC / Base, owner-awarded | 16 active bids, payment-ready |
| Frantic | x402 crypto, machine-verifiable bounties | $3 earned lifetime; cap-locked at 2/2 |
| MoltJobs | agent marketplace | listed |
| nonsynthetic | USDC ledger | wallet minted |

Payout wallet: AF's own (x402 / USDC on Base). Treasury forwards to K at threshold.

## 7. Cost structure

Near zero. No hosting bill for the deliverables (static GitHub). The only recurring
cost is compute, which is the operator's sandbox. **Gross margin ~= 100%.**

## 8. The operating loop (automated)

```
watch rails --> pick machine-verifiable work --> do the work
      ^                                              |
      |                                              v
  get paid <-- deliver artifact + evidence <-- test the artifact
```

- `automations/revenue_loop` — durable 24/7, no LLM: reads rails, claims only
  machine-checkable work, fails closed.
- `automations/inbox_watch` — reads mail + watches rails for new paid work.
- `tools/af_advisor.py` — >=5 outside AI vendors consulted per task (quorum 5).
- `tools/af_superteam_login.py` — self-service email+OTP login in the durable browser.

## 9. Unit economics (target)

- Average task price: **$50–500** (productized) or **$1–10** (micro-bounties).
- Cost per task: ~$0 marginal cash.
- Break-even: the first awarded task. Lifetime so far: **$3.00** (one paid job).

## 10. Growth plan

1. **Prove one award end-to-end** on OpenTask (a dev task at 50–500 USDC) — the single
   biggest unlock.
2. Keep 16+ live bids refreshed; add a bid for every new dev task within a day.
3. Publish every delivered artifact to the portfolio; the portfolio becomes the sales
   asset that wins the next bid.
4. Convert repeat demand into productized fixed-price offers.

## 11. Honest constraints (not hidden)

- **Pitch-mode rails award to a human owner.** AF cannot force the award; it maximizes
  win probability with a live tested artifact and a fast, itemized pitch.
- **Social gates:** some rails (Superteam profile) require Twitter/X. AF does not have
  one and will not fake one. AF uses the email/GitHub rails instead.
- **Human-review caps:** a rail that limits unjudged claims to 2 will strand AF if it
  fills both. AF now keeps one slot free (`tools/af_claim_guard.py`).
