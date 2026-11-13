// Tests for the data-quality audit engine. Run: node --test test_audit.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { auditCsv, auditJson, auditRows } from "./audit.mjs";

test("a clean file scores high and is safe to load", () => {
  const r = auditCsv("id,name\n1,ann\n2,bob\n3,cid");
  assert.equal(r.readyToLoad, true);
  assert.ok(r.score >= 90, `score ${r.score}`);
  assert.equal(r.grade, "A");
  assert.equal(r.findings.length, 0);
});

test("mixed-type column is a high blocker and drops the grade", () => {
  const r = auditCsv("id,v\n1,10\n2,20\n3,abc");
  assert.equal(r.readyToLoad, false);
  const f = r.findings.find((x) => x.issue === "mixed types");
  assert.ok(f && f.severity === "high" && f.column === "v");
  assert.match(r.verdict, /NOT SAFE/);
});

test("duplicate rows and nulls are detected and counted", () => {
  const r = auditCsv("id,name\n1,ann\n1,ann\n2,");
  assert.equal(r.duplicateRows, 1);
  const nulls = r.findings.find((x) => x.issue === "has nulls");
  assert.ok(nulls && nulls.column === "name");
  assert.ok(r.findings.some((x) => x.issue === "duplicate rows"));
});

test("null-like tokens and padded whitespace are flagged low/medium", () => {
  const r = auditCsv("a\nN/A\n  x  \ny");
  assert.ok(r.findings.some((x) => x.issue === "null-like tokens"));
  assert.ok(r.findings.some((x) => x.issue === "padded whitespace"));
});

test("a mostly-empty column is a high blocker", () => {
  const r = auditCsv("a,b\n1,\n2,\n3,\n4,\n5,x");
  const f = r.findings.find((x) => x.issue === "mostly empty");
  assert.ok(f && f.severity === "high" && f.column === "b");
});

test("auditJson accepts an array of records and a {records:[...]} wrapper", () => {
  const a = auditJson([{ id: 1, v: "x" }, { id: 2, v: "y" }]);
  const b = auditJson({ records: [{ id: 1, v: "x" }, { id: 2, v: "y" }] });
  assert.equal(a.shape.rows, 2);
  assert.equal(b.shape.rows, 2);
  assert.equal(a.grade, "A");
});

test("auditJson stringifies nested objects so it never throws", () => {
  const r = auditJson([{ id: 1, meta: { a: 1 } }, { id: 2, meta: { a: 2 } }]);
  assert.equal(r.shape.rows, 2);
  assert.equal(r.findings.length, 0);
});

test("header-only input is reported as no data rows, not a crash", () => {
  const r = auditRows([]);
  assert.equal(r.shape.rows, 0);
  assert.ok(r.findings.some((x) => x.issue === "no data rows"));
  assert.equal(r.readyToLoad, false);
});

test("score is bounded 0..100 and grade maps from score", () => {
  const messy = "a,b,c\n1,,x\n1,,y\n1,,z\n1,,N/A\n1,,  q  ";
  const r = auditCsv(messy);
  assert.ok(r.score >= 0 && r.score <= 100);
  assert.ok(["A", "B", "C", "D", "F"].includes(r.grade));
});

test("numeric outliers beyond 3*IQR are flagged", () => {
  const rows = [{ v: 10 }, { v: 11 }, { v: 10 }, { v: 12 }, { v: 11 }, { v: 10 }, { v: 11 }, { v: 12 }, { v: 100000 }];
  const r = auditRows(rows);
  assert.ok(r.findings.some((x) => x.issue === "numeric outliers"));
});
