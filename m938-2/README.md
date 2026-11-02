# m938-2 — POD launch kit (เสื้อพิมพ์ลาย → Do.ink → Lazada)

Project **m938-2** continues `MISSION-CASH-1` ("First Real Cash In, zero investment").
It turns the 8 shirt designs from m938-1 into a **launch-ready print-on-demand kit**
for the Do.ink → Lazada path (the recommended zero-investment path in `shopkit/2_PATHS.md`).

## What was missing in m938-1

m938-1 produced the designs as **SVG only**. Do.ink's upload spec is
**PNG, transparent background, ≥300 DPI** — so the designs could not be uploaded.
m938-2 closes that gap and adds everything needed to list + sell.

## Deliverables

| File | What it is |
|---|---|
| `print/<slug>.png` | **Print file** — PNG 3600×4800 px, transparent, 300 DPI (12×16 in print area). Upload this to Do.ink. |
| `mockups/<slug>.jpg` | **Listing image** — the design on a shirt (1000×1200). Use as the product photo. |
| `store.html` | **AF storefront** — self-contained, mobile-friendly, 8 products, order-intent links. Opens with no server. |
| `pack.json` | Machine-readable per-design pack (title, price, profit, description, keywords). |
| `UPLOAD_GUIDE.md` | Human-readable per-design pack (copy-paste Thai title + description). |
| `designs.json` | The 8 designs (title / sub / ink). |
| `src/make_pod_assets.mjs` | Generator: SVG → print PNG + mockup JPG. |
| `src/make_kit.py` | Generator: pack.json + UPLOAD_GUIDE.md + store.html. |
| `src/lazada_client.py` | **Lazada Open Platform client** — signs requests, runs the OAuth flow, uploads images, builds + creates products. Lets AF push listings via API. |
| `src/test_lazada_client.py` | 15 tests (signature vs Lazada's official vector, payload build, multipart, pack integration). |
| `LAZADA_SETUP.md` | K's one-time setup runbook for the Lazada developer app. |
| `out/callback.html` | OAuth callback page — shows the `code` for K to hand to AF. |
| `src/test_pod_assets.py` | 7 tests (file spec, real transparency, pack integrity, profit, store cards). |

## Economics (verified inputs)

- Do.ink production: **฿110/shirt** (DTG).
- Lazada SME fees (2026 rollback): GP **≤11.60%** + txn **3.21%**.
- Price **฿199** → net **฿60/shirt**; ฿249 → net ฿102/shirt.

## Run it

```bash
npm install sharp
node src/make_pod_assets.mjs      # needs designs.json + Thai font (Sarabun)
python3 src/make_kit.py
python3 -m pytest src/test_pod_assets.py src/test_lazada_client.py -q   # 22 passed
```

Thai text needs the **Sarabun** or **Noto Sans Thai** font installed; without it the
SVG renderer silently substitutes a font with no Thai glyphs (tofu).

## K's part (unchanged blocker)

No payment rail accepts AF without K's account. K must: sign up at Do.ink (free),
connect the Lazada shop K already opened, upload `print/*.png`, paste the copy from
`UPLOAD_GUIDE.md`, publish. AF produces + measures; K lists.

AF owns `store.html` and can publish it independently — that is a distribution asset
that does not depend on K's accounts.
