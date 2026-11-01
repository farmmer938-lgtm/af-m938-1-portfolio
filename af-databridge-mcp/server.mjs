#!/usr/bin/env node
// AF DataBridge MCP server — zero-dependency Model Context Protocol server (stdio, JSON-RPC 2.0).
import { createInterface } from 'node:readline';
import { csvToJson, sniffDelimiter } from './src/databridge.mjs';
import { score } from './src/kpi.mjs';

const TOOLS = [
  {
    name: 'csv_to_json',
    description: 'Convert CSV text to JSON. Sniffs the delimiter (, ; tab |) and infers number/boolean types.',
    inputSchema: {
      type: 'object',
      properties: {
        csv: { type: 'string', description: 'CSV content, with a header row.' },
        delimiter: { type: 'string', description: 'Optional explicit delimiter; omit to auto-sniff.' },
      },
      required: ['csv'],
    },
  },
  {
    name: 'kpi_score',
    description: 'Score a set of weighted KPIs (0..1) with lower/higher-is-better normalisation.',
    inputSchema: {
      type: 'object',
      properties: {
        metrics: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              name: { type: 'string' }, value: { type: 'number' },
              target: { type: 'number' }, direction: { type: 'string', enum: ['higher', 'lower'] },
              weight: { type: 'number' },
            },
            required: ['name', 'value', 'target'],
          },
        },
      },
      required: ['metrics'],
    },
  },
];

function call(name, args) {
  if (name === 'csv_to_json') {
    const rows = csvToJson(args.csv, args.delimiter);
    return { content: [{ type: 'text', text: JSON.stringify(rows, null, 2) }] };
  }
  if (name === 'kpi_score') {
    const r = score(args.metrics);
    return { content: [{ type: 'text', text: JSON.stringify(r, null, 2) }] };
  }
  throw new Error('unknown tool: ' + name);
}

const rl = createInterface({ input: process.stdin });
rl.on('line', (line) => {
  if (!line.trim()) return;
  let msg;
  try { msg = JSON.parse(line); } catch { return; }
  const { id, method, params } = msg;
  const reply = (result) => process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id, result }) + '\n');
  const fail = (code, message) => process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id, error: { code, message } }) + '\n');
  try {
    if (method === 'initialize') {
      reply({ protocolVersion: '2024-11-05', capabilities: { tools: {} },
        serverInfo: { name: 'af-databridge', version: '1.0.0' } });
    } else if (method === 'notifications/initialized') {
      // no reply for notifications
    } else if (method === 'tools/list') {
      reply({ tools: TOOLS });
    } else if (method === 'tools/call') {
      reply(call(params.name, params.arguments || {}));
    } else if (id !== undefined) {
      fail(-32601, 'method not found: ' + method);
    }
  } catch (e) {
    fail(-32603, String(e && e.message || e));
  }
});
