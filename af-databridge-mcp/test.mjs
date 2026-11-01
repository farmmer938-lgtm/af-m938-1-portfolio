import assert from 'node:assert';
import { csvToJson, sniffDelimiter, infer } from './src/databridge.mjs';
import { score } from './src/kpi.mjs';
let n = 0;
const t = (name, fn) => { fn(); n++; console.log('  ok', name); };

t('sniff semicolon', () => assert.equal(sniffDelimiter('a;b;c\n1;2;3'), ';'));
t('sniff comma', () => assert.equal(sniffDelimiter('a,b,c\n1,2,3'), ','));
t('type inference', () => { assert.equal(infer('12'), 12); assert.equal(infer('4.50'), 4.5); assert.equal(infer('true'), true); assert.equal(infer('x'), 'x'); });
t('quoted comma', () => assert.deepEqual(csvToJson('sku;name;price\nA1;"Widget, small";4.50'), [{ sku: 'A1', name: 'Widget, small', price: 4.5 }]));
t('blank rows skipped', () => assert.equal(csvToJson('a,b\n1,2\n\n').length, 1));
t('kpi higher-is-better', () => assert.equal(score([{ name: 'u', value: 100, target: 100 }]).score, 1));
t('kpi lower-is-better', () => assert.equal(score([{ name: 'l', value: 50, target: 100, direction: 'lower' }]).score, 1));
t('kpi weighting', () => {
  const r = score([{ name: 'a', value: 100, target: 100, weight: 3 }, { name: 'b', value: 0, target: 100, weight: 1 }]);
  assert.equal(r.score, 0.75);
});
t('kpi empty', () => assert.equal(score([]).score, 0));
console.log(`\n${n} passed`);
