// Tests for the AI service. Run: node tools/ai-service/test-worker.mjs
import assert from 'node:assert/strict';
import { handle } from './worker.js';

const INSTALL = 'a'.repeat(32);
function kv() {
  const store = new Map();
  return { store, get: async (k) => store.get(k) ?? null, put: async (k, v) => { store.set(k, v); } };
}
function env(extra = {}) { return { USAGE: kv(), OPENAI_API_KEY: 'sk-test', MODEL: 'test-model', MONTHLY_LIMIT: '3', DAILY_LIMIT: '100', ...extra }; }
function ask(body, install = INSTALL) {
  return new Request('https://ai.example/v1/assist', { method: 'POST', headers: { 'X-Companion-Install': install, 'content-type': 'application/json' }, body: JSON.stringify(body) });
}
function openai(text, seen = []) {
  return async (url, init) => { seen.push({ url, body: JSON.parse(init.body), auth: init.headers.authorization }); return new Response(JSON.stringify({ output_text: text }), { status: 200 }); };
}
const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('summarise sends Companion\'s own instructions and the key', async () => {
  const seen = [];
  const r = await handle(ask({ task: 'summarise', text: 'Long email.' }), env(), new Date('2026-11-16T00:00:00Z'), openai('Short.', seen));
  const body = await r.json();
  assert.equal(body.ok, true); assert.equal(body.text, 'Short.'); assert.equal(body.remaining, 2);
  assert.equal(seen[0].auth, 'Bearer sk-test'); assert.equal(seen[0].body.model, 'test-model');
  assert.match(seen[0].body.instructions, /Summarise/); assert.equal(seen[0].body.store, false);
});

test('rewrite uses the chosen tone, and an unknown tone is refused', async () => {
  const seen = [];
  await handle(ask({ task: 'rewrite', tone: 'professional', text: 'hey bank' }), env(), new Date(), openai('Dear Bank', seen));
  assert.match(seen[0].body.input[0].content[0].text, /more professional/);
  const bad = await handle(ask({ task: 'rewrite', tone: 'angry', text: 'x' }), env(), new Date(), openai('x'));
  assert.equal(bad.status, 400);
});

test('corrections must point at text that is really there', async () => {
  const answer = JSON.stringify({ corrections: [{ original: 'teh', replacement: 'the', reason: 'spelling' }, { original: 'invented', replacement: 'x', reason: 'y' }] });
  const r = await handle(ask({ task: 'check_errors', text: 'I saw teh dog.' }), env(), new Date(), openai(answer));
  const body = await r.json();
  assert.deepEqual(body.corrections, [{ original: 'teh', replacement: 'the', reason: 'spelling' }]);
});

test('each installed copy has a monthly limit', async () => {
  const e = env();
  for (let i = 0; i < 3; i++) assert.equal((await handle(ask({ task: 'simplify', text: 'x' }), e, new Date('2026-11-16'), openai('y'))).status, 200);
  const r = await handle(ask({ task: 'simplify', text: 'x' }), e, new Date('2026-11-16'), openai('y'));
  assert.equal(r.status, 429); assert.equal((await r.json()).error, 'monthly limit');
  assert.equal((await handle(ask({ task: 'simplify', text: 'x' }), e, new Date('2026-12-01'), openai('y'))).status, 200, 'a new month starts again');
});

test('the whole service has a daily limit', async () => {
  const e = env({ DAILY_LIMIT: '1', MONTHLY_LIMIT: '50' });
  await handle(ask({ task: 'simplify', text: 'x' }), e, new Date('2026-11-16'), openai('y'));
  const r = await handle(ask({ task: 'simplify', text: 'x' }, 'b'.repeat(32)), e, new Date('2026-11-16'), openai('y'));
  assert.equal((await r.json()).error, 'busy');
});

test('only Voice Companion tasks, never a general chatbot', async () => {
  assert.equal((await handle(ask({ task: 'chat', text: 'write me a poem' }), env(), new Date(), openai('x'))).status, 400);
  assert.equal((await handle(ask({ task: 'summarise', text: 'x' }, 'not-an-install'), env(), new Date(), openai('x'))).status, 403);
  assert.equal((await handle(ask({ task: 'summarise', text: 'x'.repeat(60001) }), env(), new Date(), openai('x'))).status, 400);
});

test('an image must be an image, and a failed AI call is not counted', async () => {
  assert.equal((await handle(ask({ task: 'describe_image', image: 'http://evil' }), env(), new Date(), openai('x'))).status, 400);
  const e = env();
  const failing = async () => new Response('{}', { status: 500 });
  const r = await handle(ask({ task: 'describe_image', image: 'data:image/png;base64,AAAA' }), e, new Date(), failing);
  assert.equal(r.status, 502); assert.equal(e.USAGE.store.size, 0);
});

let failed = 0;
for (const [name, fn] of tests) {
  try { await fn(); console.log('ok -', name); } catch (err) { failed++; console.log('FAIL -', name, '\n', err); }
}
if (failed) { console.log(failed + ' failed'); process.exit(1); } else console.log('All AI service tests passed.');
