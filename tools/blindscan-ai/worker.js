// BlindScan AI service (Cloudflare Worker).
//
// Answers "Ask a question" in BlindScan, Will's free Android document scanner
// (github.com/giantpos0-oss/BlindScan), using the same OpenAI account as Voice
// Companion, so BlindScan users need no key of their own (Will, November 23, 2026).
// Only BlindScan's own question task is offered, with its instructions kept here,
// so the key cannot be used as a general chatbot. No per-user limits (Will,
// November 23, 2026): the OpenAI spending limit is the stop.
//
// POST /v1/ask   {document, question, history?: [{question, answer}], image?: "data:image/jpeg;base64,..."}
//   headers: X-BlindScan-Install (random id per installed copy), X-BlindScan-Version
// GET  /v1/health

export const INSTRUCTIONS = [
  'You answer questions about a document that a blind person scanned with their phone camera.',
  'You get the text the phone read from the page, and usually a photo of the page too.',
  'Use only the document. Never use outside knowledge and never guess.',
  'Reply in exactly this form, with these three labels on their own lines:',
  'ANSWER: a short, direct answer in one to three plain sentences, for listening. No markdown, no lists.',
  'QUOTE: the exact words copied from the scanned text that show the answer, word for word, at most about forty words. For several separate places, join them with " ... ".',
  'CHECK: OK if the photo agrees with the scanned text for everything in your answer. If the photo shows a different number, name, date, amount or word than the scanned text for anything in your answer, write what the photo shows and what the scan says, for example: The photo shows $64.17 where the scan says $84.17. If there is no photo, write OK.',
  'When the photo and the scan disagree, base the ANSWER on the photo, but still copy the QUOTE from the scanned text.',
  'If the document does not contain the answer, reply exactly:',
  "ANSWER: The document doesn't say.",
  'QUOTE: NONE',
  'CHECK: OK',
  'Copy names, dates, amounts, prices and numbers exactly as written.',
].join('\n');

const LIMITS = { document: 200000, question: 2000, answer: 1000, image: 8 * 1024 * 1024, history: 4 };

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

export function problem(body) {
  if (typeof body.document !== 'string' || !body.document.trim()) return 'no document';
  if (body.document.length > LIMITS.document) return 'document too long';
  if (typeof body.question !== 'string' || !body.question.trim()) return 'no question';
  if (body.question.length > LIMITS.question) return 'question too long';
  if (body.history !== undefined) {
    if (!Array.isArray(body.history) || body.history.length > LIMITS.history) return 'bad history';
    for (const t of body.history) {
      if (!t || typeof t.question !== 'string' || typeof t.answer !== 'string') return 'bad history';
      if (t.question.length > LIMITS.question || t.answer.length > LIMITS.answer) return 'bad history';
    }
  }
  if (body.image !== undefined && body.image !== null) {
    if (typeof body.image !== 'string' || !/^data:image\/(png|jpe?g|webp);base64,/.test(body.image)) return 'bad image';
    if (body.image.length > LIMITS.image) return 'image too large';
  }
  return null;
}

export function buildInput(body) {
  let text = 'SCANNED TEXT:\n' + body.document + '\nEND OF SCANNED TEXT\n\n';
  for (const t of body.history || []) {
    text += 'Earlier question: ' + t.question + '\nEarlier answer: ' + t.answer + '\n\n';
  }
  text += 'QUESTION: ' + body.question.trim();
  const parts = [{ type: 'input_text', text }];
  if (body.image) parts.push({ type: 'input_image', image_url: body.image });
  return [{ role: 'user', content: parts }];
}

function outputText(data) {
  if (typeof data.output_text === 'string') return data.output_text;
  const pieces = [];
  for (const item of data.output || []) {
    for (const part of item.content || []) {
      if (part.type === 'output_text' && typeof part.text === 'string') pieces.push(part.text);
    }
  }
  return pieces.join('');
}

export async function handle(request, env, fetcher = fetch) {
  const url = new URL(request.url);
  if (url.pathname === '/v1/health') return json({ ok: true });
  if (url.pathname !== '/v1/ask' || request.method !== 'POST') return json({ ok: false, error: 'not found' }, 404);
  const install = request.headers.get('X-BlindScan-Install') || '';
  if (!/^[0-9a-f]{32}$/.test(install)) return json({ ok: false, error: 'not blindscan' }, 403);
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: 'bad request' }, 400); }
  const why = problem(body);
  if (why) return json({ ok: false, error: why }, 400);

  const reply = await fetcher('https://api.openai.com/v1/responses', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + env.OPENAI_API_KEY },
    body: JSON.stringify({ model: env.MODEL, instructions: INSTRUCTIONS, input: buildInput(body), store: false }),
  });
  if (!reply.ok) {
    // Every failure names itself: pass on OpenAI's own error code and message (never the key).
    const err = await reply.json().catch(() => ({}));
    const detail = String((err.error && (err.error.code || err.error.type)) || '') + ': ' + String((err.error && err.error.message) || '').slice(0, 300);
    if (reply.status === 429) return json({ ok: false, error: 'unavailable', detail }, 503);
    return json({ ok: false, error: 'ai service ' + reply.status, detail }, 502);
  }
  const text = outputText(await reply.json()).trim();
  if (!text) return json({ ok: false, error: 'empty answer' }, 502);
  return json({ ok: true, text });
}

export default { fetch: (request, env) => handle(request, env) };
