// Tests for demand measurement. Run: node --test test_demand.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { isLocal, summarizeDemand } from "./demand.mjs";

test("isLocal flags loopback in v4, v6 and v4-mapped form", () => {
  assert.equal(isLocal("127.0.0.1"), true);
  assert.equal(isLocal("::1"), true);
  assert.equal(isLocal("::ffff:127.0.0.1"), true);
  assert.equal(isLocal("10.1.0.230"), false);
  assert.equal(isLocal("203.0.113.7"), false);
});

test("summarizeDemand excludes AF's own loopback tests from the buyer count", () => {
  const rows = [
    { path: "/audit", ip: "127.0.0.1", local: true },
    { path: "/audit", ip: "::ffff:127.0.0.1", local: true },
    { path: "/audit", ip: "203.0.113.7", local: false },
    { path: "/csv_to_json", ip: "203.0.113.7", local: false },
    { path: "/csv_to_json", ip: "198.51.100.9", local: false },
  ];
  const s = summarizeDemand(rows);
  assert.equal(s.total_hits, 5);
  assert.equal(s.external_hits, 3);
  assert.equal(s.external_unique_ips, 2);
  assert.deepEqual(s.by_path, { "/audit": 1, "/csv_to_json": 2 });
  assert.equal(s.last_external.ip, "198.51.100.9");
});

test("summarizeDemand reports zero demand when only AF has looked", () => {
  const s = summarizeDemand([{ path: "/audit", ip: "127.0.0.1", local: true }]);
  assert.equal(s.external_hits, 0);
  assert.equal(s.external_unique_ips, 0);
  assert.equal(s.last_external, null);
});

test("summarizeDemand handles an empty log", () => {
  const s = summarizeDemand([]);
  assert.equal(s.total_hits, 0);
  assert.equal(s.external_hits, 0);
  assert.deepEqual(s.by_path, {});
});
