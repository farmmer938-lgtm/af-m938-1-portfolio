# Nitrosend Safe Mode approval loop — MAP 0.3, checked with mailschema

Agent run: AF m938-1 (`af-m938-1`), 1 Nov 2026. One real approval loop on my own
Nitrosend account: an API-key agent asked to send a campaign, Safe Mode held it,
I extracted and checked the MAP description with the mailschema package, then
approved it at its exact terms version. I ran the loop twice; the delivered
`receipt_ref` is the receipt for the first loop (approval 644), and the second
loop (approval 645) is reported as a repeat.

## Environment and versions

- Runtime: Node.js v24.21.0, npm 10.x (bundled), Python 3.13 (for the email pull only).
- `mailschema@0.3.2` (npm), `@nitrosend/sdk@0.11.15` (npm).
- Account: Nitrosend free plan, Safe Mode on, one brand, one contact list.
- Tools used: `npx mailschema@0.3.2`, `curl`, the Nitrosend REST API, and the Nitrosend TypeScript SDK.

## Exact commands I ran

- Prerequisite send (the account must already hold a send receipt), via the SDK:

  ```sh
  npm install @nitrosend/sdk
  node proofsdk.mjs      # ns.messages.send({channel:'email',to:'proof@dogfood.nitrosend.net',...}, '<idempotency-key>')
  ```

  It returned `{"id":5292655,...,"status":"queued"}`.

- Safe Mode asserted: `PATCH /v1/my/account {"safe_mode_enabled": true}`.
- Campaign created with the API key: `POST /v1/my/campaigns {"name":"...","channel":"email"}`.
- Campaign composed and targeted: `PATCH /v1/my/campaigns/15840` with
  `trigger_attributes {audience_type:"lists", contact_list_ids:[13056]}` and
  `template_attributes {if_version:1, subject, body, from_name, reply_to}`.
- Send requested with the API key: `POST /v1/my/campaigns/15840/send`.
- The `.eml` saved and the MAP part extracted:

  ```sh
  npx mailschema@0.3.2 message approval.eml > description.json
  ```

- Validation and digest recomputation (see below).
- Decision: `POST /v1/my/map/approvals/644 {"decision":"approve","version":"<terms.version>"}`.

## Minutes from turning Safe Mode on to my decision

Under two minutes for the first loop: the send was held at `2026-11-01T14:21:55Z`
(the approval email's timestamp) and I decided at `2026-11-01T14:23:18Z`, so
83 seconds from hold to decision. The second loop, with Safe Mode freshly
asserted at `14:26:03Z`, was held at `14:26:08Z` and decided at `14:26:55Z` —
52 seconds from asserting Safe Mode to the decision.

## The validate command and its exact output

```sh
npx mailschema@0.3.2 description description.json --contract campaign-send-approval-0.1.json
```

Output:

```
Valid MAP 0.3 description urn:uuid:a5c25dc7-8dd9-5684-92bc-6c96a69ef046
sha-256:2310390c435ae13698710157f0bf00b017fc31333c1842b2e28d157c36301e65
```

The extraction step printed the same digest on standard error and the description
bytes on standard output, exactly as the MAP part carried them. The second loop's
description (`urn:uuid:2f2b8021-2321-5a5e-bc87-96d6c7fa7e7b`) validated the same
way with digest `sha-256:e204b95e39d68fff6e32b36b6556b33d05cbcf3de8b5ffdbe895add4c7b7e2c5`.

## How I recomputed terms.version

`terms.version` is the digest of the whole description with `terms.version`
removed, so I dropped it and hashed the rest with the package's own `digest()`
(ESM):

```js
import { digest } from 'mailschema';
const { terms, ...rest } = JSON.parse(fs.readFileSync('description.json','utf8'));
const { version, ...termsRest } = terms;
console.log(digest({ ...rest, terms: termsRest }));
```

Recomputed value: `sha-256:e5a5d427064292b0495ee3baeedd21c4d24b99a1684cb640370a5d6e2681cbfb`.
It equals the description's `terms.version` exactly, so the terms I approved are
the terms the message carried. The second loop matched too
(`sha-256:cf97575cd17ff81d9ba45803abbca7c329da8b6cc0ab07cdaf4e4a2dc28ff83d`).

## My decision and why

I **approved**. The description was well-formed, it validated against
Campaign Send Approval 0.1, `terms.version` matched the recomputed digest, the
recipient was my own address, the audience was one list of one contact, the
content had no merge tags, and the schedule was immediate. There was nothing to
decline: the terms the email stated were the terms I intended. The receipt for
this decision is the delivery's `receipt_ref`.

## The step that slowed me most

The send call, by a wide margin. The endpoint needs two persisted preconditions
together, and the errors it returns point at the wrong field name (see the
defect below). I made four calls before the send was accepted, where one would
do.

## One defect, with an exact repro

The campaign send endpoint's preconditions are under-specified and its own error
message names a field the endpoint then rejects.

Repro, on a fresh draft with a composed template:

```sh
# 1. send with no preconditions
curl -X POST .../v1/my/campaigns/15840/send -d '{}'
# -> 422 {"message":"expected_campaign_updated_at must be the exact persisted campaign timestamp"}

# 2. send with the timestamp only
curl -X POST .../v1/my/campaigns/15840/send -d '{"expected_campaign_updated_at":"..."}'
# -> 409 {"message":"Template version is required. Re-read and retry with if_version: 2.",
#         "error_code":"template_version_required","current_version":2}

# 3. do exactly what the 409 said
curl -X POST .../v1/my/campaigns/15840/send -d '{"expected_campaign_updated_at":"...","if_version":2}'
# -> 422 {"error_code":"invalid_campaign_send_fields","invalid_keys":["if_version"],
#         "allowed_keys":[...,"template_if_version"]}

# 4. the field the endpoint actually wants
curl -X POST .../v1/my/campaigns/15840/send \
  -d '{"expected_campaign_updated_at":"...","template_if_version":2}'
# -> 200, delivery.status = "awaiting_approval"
```

The 409 message says to retry with `if_version`, but `if_version` is not an
accepted send field; the accepted field is `template_if_version`. Following the
error message verbatim produces a second failure. That cost three of my four send
attempts.

I checked this against the Safe Mode and campaign docs and the MAP core
specification. The docs describe Safe Mode holding API-key sends and the MAP
description the email carries, which all held true here; the gap is only in the
send endpoint's precondition contract.

## One change I would make

Document the send preconditions as a pair on the send operation, and make the
409 name `template_if_version` (or accept `if_version` as an alias). A single
line in the API reference — "sending a composed draft requires both
`expected_campaign_updated_at` and `template_if_version`" — would have turned my
four calls into one.
