// Tests for the BlindScan AI service. Run: node tools/blindscan-ai/test-worker.mjs
import assert from 'node:assert/strict';
import { handle, INSTRUCTIONS } from './worker.js';

const INSTALL = 'b'.repeat(32);
const env = { OPENAI_API_KEY: 'sk-test', MODEL: 'test-model' };
function ask(body, install = INSTALL) {
  return new Request('https://ai.example/v1/ask', { method: 'POST', headers: { 'X-BlindScan-Install': install, 'content-type': 'application/json' }, body: JSON.stringify(body) });
}
function openai(text, seen = [], status = 200) {
  return async (url, init) => {
    seen.push({ url, body: JSON.parse(init.body), auth: init.headers.authorization });
    return new Response(JSON.stringify(status === 200 ? { output_text: text } : { error: { code: 'insufficient_quota', message: 'quota' } }), { status });
  };
}
const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('asks with BlindScan\'s instructions, the key, the document and the photo', async () => {
  const seen = [];
  const r = await handle(ask({ document: 'Amount due: $84.17', question: 'How much?', image: 'data:image/jpeg;base64,AAAA',
    history: [{ question: 'Who from?', answer: 'City Water.' }] }), env, openai('ANSWER: $84.17\nQUOTE: Amount due: $84.17\nCHECK: OK', seen));
  const body = await r.json();
  assert.equal(body.ok, true); assert.match(body.text, /QUOTE/);
  assert.equal(seen[0].url, 'https://api.openai.com/v1/responses');
  assert.equal(seen[0].auth, 'Bearer sk-test'); assert.equal(seen[0].body.model, 'test-model');
  assert.equal(seen[0].body.instructions, INSTRUCTIONS); assert.equal(seen[0].body.store, false);
  const parts = seen[0].body.input[0].content;
  assert.match(parts[0].text, /Amount due: \$84\.17/); assert.match(parts[0].text, /Earlier question: Who from\?/);
  assert.match(parts[0].text, /QUESTION: How much\?$/);
  assert.equal(parts[1].type, 'input_image');
});

test('works without a photo', async () => {
  const seen = [];
  await handle(ask({ document: 'Hello', question: 'What?' }), env, openai('ANSWER: x\nQUOTE: Hello\nCHECK: OK', seen));
  assert.equal(seen[0].body.input[0].content.length, 1);
});

test('only BlindScan may ask', async () => {
  const r = await handle(ask({ document: 'x', question: 'y' }, 'nope'), env, openai('x'));
  assert.equal(r.status, 403);
});

test('bad requests are refused before OpenAI is called', async () => {
  const seen = [];
  for (const b of [{ question: 'y' }, { document: 'x' }, { document: 'x', question: 'y', image: 'http://evil' },
    { document: 'x', question: 'y', history: 'no' }, { document: 'x'.repeat(200001), question: 'y' }]) {
    const r = await handle(ask(b), env, openai('x', seen));
    assert.equal(r.status, 400);
  }
  assert.equal(seen.length, 0);
});

test('OpenAI refusing (spending limit) says so plainly', async () => {
  const r = await handle(ask({ document: 'x', question: 'y' }), env, openai('', [], 429));
  assert.equal(r.status, 503); const b = await r.json(); assert.equal(b.error, 'unavailable'); assert.match(b.detail, /insufficient_quota/);
});

test('health and unknown paths', async () => {
  assert.equal((await handle(new Request('https://ai.example/v1/health'), env)).status, 200);
  assert.equal((await handle(new Request('https://ai.example/v1/chat', { method: 'POST' }), env)).status, 404);
});

let failed = 0;
for (const [name, fn] of tests) {
  try { await fn(); console.log('ok   ' + name); } catch (e) { failed++; console.log('FAIL ' + name + '\n' + e.stack); }
}
if (failed) { console.log(failed + ' failed'); process.exit(1); }
console.log('All ' + tests.length + ' BlindScan AI tests passed.');
