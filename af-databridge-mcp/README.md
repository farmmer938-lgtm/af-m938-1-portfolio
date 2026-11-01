<!-- mcp-name: io.github.farmmer938-lgtm/af-databridge -->
# AF DataBridge MCP

A zero-dependency Model Context Protocol server with two tools:

| Tool | What it does |
|---|---|
| `csv_to_json` | Converts CSV text to JSON. Sniffs the delimiter (`,` `;` tab `|`), handles quoted fields, and infers numbers/booleans. |
| `kpi_score` | Scores weighted KPIs 0..1 with higher-is-better or lower-is-better normalisation. |

No dependencies. No network calls. Runs on Node 18+.

## Install and run

```bash
node server.mjs          # speaks JSON-RPC 2.0 over stdio
```

Client config (e.g. Claude Desktop, Cursor, Cline):

```json
{ "mcpServers": { "af-databridge": { "command": "node", "args": ["/path/to/af-databridge-mcp/server.mjs"] } } }
```

## Example

Input CSV (semicolon-delimited, quoted comma, mixed types):

```
sku;name;price;in_stock
A1;"Widget, small";4.50;true
B2;Gadget;12;false
```

`csv_to_json` returns:

```json
[
  { "sku": "A1", "name": "Widget, small", "price": 4.5, "in_stock": true },
  { "sku": "B2", "name": "Gadget", "price": 12, "in_stock": false }
]
```

## Tests

```bash
node test.mjs     # 9 passed
```

Verified: `sniffDelimiter` picks `;` and `,` correctly, quoted commas survive, blank rows are skipped, type inference maps `12` to `12`, `4.50` to `4.5`, `true` to `true`, and KPI weighting is exact (0.75 for 3:1 weights at 100%/0%).

## License

MIT
