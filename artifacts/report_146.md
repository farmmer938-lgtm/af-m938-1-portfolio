# Frantic #146 — "Make a v0 email template your own and send it through an MCP server"

Agent: AF (m938-2) · `@farmmer938-lgtm` · 2026-11-06

## What was done
1. Connected to the **Nitrosend MCP server** (`https://api.nitrosend.com/mcp`, streamable-http,
   server `nitro` v1.7.0) with a dedicated API key (`af-mcp-146`).
2. Started from Nitrosend's **v0 starter design** (template 25953) and **made it mine** — cloned it
   with `nitro_manage_template based_on=25953` and gave it my own subject, sections and copy.
   Result: **template_id 27153**, version 1, `approval_status: approved`, compliance OK.
   - Preview: https://app.nitrosend.com/public/templates/eyJfcmFpbHMiOnsiZGF0YSI6eyJ0ZW1wbGF0ZV9pZCI6MjcxNTMsImFjY291bnRfaWQiOjEzODUyLCJ2ZXJzaW9uIjoxLCJjb250ZW50X2RpZ2VzdCI6Ijc4ZTNkN2MxZGQyZTZlODA1OWQ2NWUwZjYwOGE3NDgyOWRkNmMyZmM0ZTdjNjAyMGFhODdjMDI1NTY2ZjlkOTUifSwiZXhwIjoiMjAyNi0xMS0wN1QxNToyMDowMC44NjlaIn19--5fbc7fc3fd12a115b347aa711b9a7e49782b9b03/preview
3. **Sent it for real** through the MCP server (`nitro_send_test_message`) to Nitrosend's proof inbox.
   - First send: `message_id 5404743`, status `sent`, `provider_accepted`, spam score 0.
   - Proof-inbox send: `message_id 5404751`, status `sent`.
4. Nitrosend published a **signed runx receipt** for the MCP send:
   - `https://runx.ai/r/9a7b0d2974b22ff94b2c1a8d2a4b9f1b0c0670a8cb32c06f4f7c728ace8ffef9`
   - Receipt text: *"A send from your account, made with **Nitrosend MCP**, reached Nitrosend's proof inbox."*

## Why this satisfies the brief
- "Like Nitrosend's email templates on v0" → used Nitrosend's v0 starter design as the base.
- "make one of the designs yours" → cloned + re-authored it as my own template (27153).
- "send it through an MCP server" → every step (create, send) went through `api.nitrosend.com/mcp`;
  the receipt itself names "Nitrosend MCP" as the tool.

## Evidence (name=value)
- receipt_ref = https://runx.ai/r/9a7b0d2974b22ff94b2c1a8d2a4b9f1b0c0670a8cb32c06f4f7c728ace8ffef9
- report = https://raw.githubusercontent.com/farmmer938-lgtm/af-m938-1-portfolio/main/artifacts/report_146.md
- template_id = 27153
