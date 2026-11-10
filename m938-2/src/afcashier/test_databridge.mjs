// Tests for the DataBridge SQL emitter. Run: node --test test_databridge.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { csvToJson, csvToSql, score } from "./databridge.mjs";

test("csvToJson infers types and sniffs the delimiter", () => {
  assert.deepEqual(csvToJson("a;b\n1;true"), [{ a: 1, b: true }]);
  assert.deepEqual(csvToJson('x,y\n"a,b",2'), [{ x: "a,b", y: 2 }]);
});

test("csvToSql emits a typed CREATE TABLE and quoted INSERTs (postgres)", () => {
  const r = csvToSql("name,age,active\nAnn,31,true\nBob,45,false", { table: "people" });
  assert.equal(r.dialect, "postgres");
  assert.equal(r.rowCount, 2);
  assert.deepEqual(r.columns.map((c) => c.type), ["text", "bigint", "boolean"]);
  assert.match(r.ddl, /CREATE TABLE "people"/);
  assert.match(r.dml, /VALUES\n  \('Ann', 31, TRUE\),\n  \('Bob', 45, FALSE\);/);
});

test("csvToSql escapes single quotes and uses backticks for mysql", () => {
  const r = csvToSql("note\nit's ok", { dialect: "mysql", table: "t" });
  assert.match(r.ddl, /`note` TEXT/);
  assert.match(r.dml, /'it''s ok'/);
});

test("csvToSql maps booleans to 0/1 for sqlite", () => {
  const r = csvToSql("flag\ntrue\nfalse", { dialect: "sqlite", table: "t" });
  assert.match(r.dml, /\(1\),\n  \(0\);/);
});

test("csvToSql rejects an unknown dialect and handles an empty body", () => {
  assert.throws(() => csvToSql("a\n1", { dialect: "oracle" }), /dialect/);
  assert.deepEqual(csvToSql("", {}).rowCount, 0);
});

test("score normalises higher- and lower-is-better metrics", () => {
  const r = score([
    { name: "uptime", value: 99.5, target: 99.9, direction: "higher", weight: 1 },
    { name: "latency", value: 100, target: 50, direction: "lower", weight: 1 },
  ]);
  assert.equal(r.breakdown.length, 2);
  assert.ok(r.score > 0 && r.score <= 1);
});
