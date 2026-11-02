# Lazada Open Platform — setup for K (project m938-2)

Goal: let AF create the 8 shirt listings on K's Lazada shop **through the official API**
instead of K hand-uploading each one. K does three one-time steps; after that AF can create
and update products, upload images and read orders on its own.

Official portal: https://open.lazada.com/

## Why this path

- Registering as **Personal Self-Developed** needs **only a short software description** —
  no business licence (source: Lazada Seller Service Market onboarding guide).
- A self-developed app is limited to **your own store** and ≤20 authorized users. That is
  exactly what we need: AF acting on K's one shop.
- The API key + secret stay in `/workspace/.secrets/lazada.json` (git-ignored, never printed).

## Step 1 — Register a developer account (K, ~10 min)

1. Open https://open.lazada.com/apps/user/register
2. Use K's own email (a `+` in the address is not allowed; the full name must not contain
   "lazada"; the password needs English + number + symbol, but not `!` `<` `>`).
3. Verify the email code, then complete the profile.
   - **Country:** Thailand
   - **Partner type:** `Personal Self-Developed` (the type with no licence requirement)
   - **Software description:** paste the text from the box below.
4. Submit and wait for approval (Lazada operations reviews it).

Software description to paste:

> Personal print-on-demand listing assistant. It uses the Lazada Open Platform Product API
> to create and maintain my own shop's listings (title, description, images, price, size
> variants) and the Order API to read incoming orders. It operates only on my own store.

## Step 2 — Create the app (K)

1. In the App Console, request the **application category** that includes the Product and
   Order API groups, then click **Create App**.
2. Fill in the app name, the **callback URL** (see below) and an optional 200×200 logo.
3. Open **App Overview** and copy the **App Key** and **App Secret**.
4. In **API Permission Group**, apply for the **Product** and **Order** groups (add a one-line
   business reason). Some groups are active by default; the rest need this request.

Callback URL: use a stable page K controls. The authorization redirect must match it exactly.
AF can host one on the public portfolio repo, e.g.

    https://raw.githack.com/farmmer938-lgtm/af-m938-1-portfolio/main/m938-2/out/callback.html

## Step 3 — Give AF the credentials and authorize (K)

1. Create the secrets file (the folder may not exist yet): `mkdir -p /workspace/.secrets`, then
   write `/workspace/.secrets/lazada.json` (copy `lazada.example.json` as the starting point):

```json
{
  "app_key": "PASTE_APP_KEY",
  "app_secret": "PASTE_APP_SECRET",
  "country": "th"
}
```

2. Ask AF to print the authorization URL:

```bash
python3 src/lazada_client.py auth-url "<the callback URL from step 2>"
```

3. Open that URL, log in with the **Lazada seller account**, and approve.
   The browser lands on the callback URL with `?code=...`.
4. Hand that `code` to AF, who runs:

```bash
python3 src/lazada_client.py token "<code>"
```

That stores `access_token` + `refresh_token` into `lazada.json`. From here AF can run
`whoami`, `categories`, `attributes`, `upload-images`, `build` and `create` on its own.

## What AF does next (no K needed)

```bash
python3 src/lazada_client.py whoami                     # confirm the shop
python3 src/lazada_client.py categories "เสื้อยืด"        # find the t-shirt category id
python3 src/lazada_client.py attributes <category_id>   # see required attributes
python3 src/lazada_client.py upload-images out/print/*.png   # -> Lazada image URLs
python3 src/lazada_client.py build out/pack.json <category_id>   # dry run
python3 src/lazada_client.py create out/pack.json <category_id> seller-boss   # LIVE
```

## Reference facts (verified 2026-11-02)

- Signature: sort params (exclude `sign`) → concat `key+value` → prepend API path →
  `HMAC-SHA256(app_secret)` → **uppercase hex**. Verified against Lazada's published test
  vector `4190D32361CFB9581350222F345CB77F3B19F0E31D162316848A2C1FFD5FAB4A`
  (secret `helloworld`, path `/order/get`).
- Endpoints: auth `https://auth.lazada.com/rest`; Thailand gateway
  `https://api.lazada.co.th/rest`.
- Token: `/auth/token/create` (code → access_token, short lived) and `/auth/token/refresh`.
- Images must be **Lazada inlinks**; upload the local PNG/JPG first via `/image/upload`
  (JPG/PNG, ≤1 MB) and use the returned URL in `CreateProduct`.
- `CreateProduct` payload is `{"Request":{"Product":{PrimaryCategory, Images, Attributes, Skus}}}`.

## Still K-only

The three steps above, plus the actual Lazada **seller account** and its payout/bank details.
No marketplace pays AF directly; AF prepares and pushes, K owns the account.
