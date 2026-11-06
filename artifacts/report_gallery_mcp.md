# Saved a gallery design, made it mine, sent it through an MCP server

Run by AF (m938-2) · 2026-11-06

- **New or existing accounts.** Both accounts were already existing, not created for this run: the v0
  account and the Nitrosend account were both set up on 2026-10-31. No new sign-up was needed.

- **The design and what I changed.** I started from the gallery design **"The First-Order Perk"**
  (catalog id `welcome_offer`, category *welcome*). I kept its header/image/button/footer structure and
  changed the copy: I replaced the hero headline with my own line ("Saved from the gallery, made mine by
  AF."), rewrote the promotional body paragraph into a plain description of this run, and swapped the hero
  image for a copy ingested into my own media library. I saved the result as my own template (template
  id 27156) and sent that saved design.

- **MCP client, version and model.** The send went through the Nitrosend MCP server over streamable-HTTP
  (`initialize` then `tools/call`), calling `nitro_manage_template` to compose/save and
  `nitro_send_test_message` to send. The server identifies itself as `nitro` **v1.7.0**. The client was a
  minimal Python MCP client (protocol version 2024-11-05) driven by the OpenHands agent LLM.

- **Minutes from gallery to receipt.** About **20 minutes** from opening the gallery to the runx receipt,
  most of that spent getting the compose step to accept the design.

- **The step that slowed me most.** Composing the template. `nitro_manage_template` does not save on the
  first call — it returns a baseline `next_call.input` that must be resubmitted verbatim — and it kept
  flagging an *image binding* error because the image had to be ingested into the account first (a public
  image URL was rejected). That ingest-then-retry loop cost the most time.

- **One change I would make.** Let the template-compose tool accept a public image URL directly (or
  auto-ingest it) so a design that came from the gallery saves in a single call, instead of needing a
  separate ingest step and a second submit.

## Evidence
- Receipt (send of the saved design through the MCP server): see `receipt_ref` bound with this delivery.
- Sent template: template id 27156, subject "Saved from the gallery, made mine".
