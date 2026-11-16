// Tests for demand measurement. Run: node --test test_demand.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { classifyIp, looksCrawler, summarizeDemand } from "./demand.mjs";

test("classifyIp: loopback forms", () => {
  assert.equal(classifyIp("127.0.0.1"), "loopback");
  assert.equal(classifyIp("::1"), "loopback");
  assert.equal(classifyIp("::ffff:127.0.0.1"), "loopback");
  assert.equal(classifyIp("127.5.5.5"), "loopback");
});

test("classifyIp: private ranges (ingress/sandbox) are NOT public", () => {
  for (const ip of ["10.1.0.230", "10.0.0.1", "172.16.0.1", "172.31.255.1", "192.168.1.1", "169.254.1.1", "100.64.0.1"]) {
    assert.equal(classifyIp(ip), "private", ip);
  }
});

test("classifyIp: routable addresses are public", () => {
  for (const ip of ["203.0.113.7", "8.8.8.8", "198.51.100.9", "2001:4860:4860::8888"]) {
    assert.equal(classifyIp(ip), "public", ip);
  }
});

test("classifyIp: 172.32 is public, 172.15 is public (outside /12)", () => {
  assert.equal(classifyIp("172.32.0.1"), "public");
  assert.equal(classifyIp("172.15.0.1"), "public");
});

test("summarizeDemand: only PUBLIC socket addresses count as external demand", () => {
  const rows = [
    { path: "/audit", cls: "loopback", ua: "curl" },        // AF's own test
    { path: "/audit", cls: "private", ua: "node" },          // ingress / AF tooling
    { path: "/audit", cls: "private", ua: "node" },
    { path: "/audit", cls: "public", ua: "curl/8.14.1" },    // a real external client
    { path: "/csv_to_json", cls: "public", ua: "python-requests" },
  ];
  const s = summarizeDemand(rows);
  assert.equal(s.total_hits, 5);
  assert.equal(s.external_hits, 2);
  assert.equal(s.private_hits, 2);
  assert.equal(s.loopback_hits, 1);
  assert.deepEqual(s.by_path, { "/audit": 1, "/csv_to_json": 1 });
  assert.equal(s.last_external.path, "/csv_to_json");
});

test("summarizeDemand: the 55 private hits are NOT demand (regression guard)", () => {
  // Reproduces the 2026-11-16 mistake: 55 non-loopback hits, all private 10.1.x.x.
  const rows = Array.from({ length: 55 }, () => ({ path: "/audit", cls: "private", ua: "node" }));
  const s = summarizeDemand(rows);
  assert.equal(s.external_hits, 0);
  assert.equal(s.private_hits, 55);
});

test("summarizeDemand: crawler UAs are external but flagged", () => {
  const s = summarizeDemand([
    { path: "/audit", cls: "public", ua: "Mozilla/5.0 (compatible; Amazonbot/0.1)" },
    { path: "/audit", cls: "public", ua: "curl/8.14.1" },
  ]);
  assert.equal(s.external_hits, 2);
  assert.equal(s.crawler_hits, 1);
  assert.equal(looksCrawler("Googlebot/2.1"), true);
  assert.equal(looksCrawler("curl/8.14.1"), false);
});

test("summarizeDemand: empty log", () => {
  const s = summarizeDemand([]);
  assert.equal(s.total_hits, 0);
  assert.equal(s.external_hits, 0);
  assert.equal(s.last_external, null);
});
