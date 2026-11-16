// Voice Companion AI service (Cloudflare Worker).
//
// Holds the OpenAI key so Voice Companion users need no account of their own
// (Will, November 16, 2026). Only Companion's own tasks are offered, with
// prompts kept here, so the key cannot be used as a general chatbot. Each
// installed copy has a monthly limit, and the whole service a daily limit,
// so costs stay predictable.
//
// POST /v1/assist   {task, text?, tone?, image?, question?, guide?}
//   headers: X-Companion-Install (random id per installed copy), X-Companion-Version
// GET  /v1/health

const TASKS = {
  check_errors: {
    instructions:
      'You check writing for a blind or low-vision person who uses a screen reader. ' +
      'Find spelling, grammar, punctuation and typing mistakes in the text. ' +
      'Do not change the meaning, the tone, names, or anything that is not a mistake. ' +
      'Reply only with JSON: {"corrections":[{"original":"exact text as written","replacement":"corrected text","reason":"a few plain words"}]}. ' +
      'Each "original" must appear exactly in the text, and be as short as possible while still unique. ' +
      'If there are no mistakes, reply {"corrections":[]}.',
    json: true,
  },
  rewrite: {
    instructions:
      'You rewrite text for a blind or low-vision person. Keep every fact, name, date and number. ' +
      'Keep the same language and the same kind of writing (letter, email, note). ' +
      'Reply with the rewritten text only, with no title, no quotation marks and no comments.',
    tones: {
      friendlier: 'Make it warmer and friendlier.',
      professional: 'Make it more professional and polite, suitable for a bank, a council or an employer.',
      clearer: 'Make it clearer and easier to follow, in plain words.',
      shorter: 'Make it shorter and more to the point, keeping everything important.',
    },
  },
  summarise: {
    instructions:
      'Summarise the text for a blind or low-vision person who listens with a screen reader. ' +
      'Start with the main point in one sentence. Then give any dates, times, amounts, people, and anything the reader must do, ' +
      'each on its own short line starting with a dash. Use plain words. No headings, no tables, no bold or other formatting.',
  },
  simplify: {
    instructions:
      'Rewrite the text in simple, plain language at about an 8th-grade reading level, for a blind or low-vision person ' +
      'who listens with a screen reader. Keep every fact, date, amount and instruction. Use short sentences. ' +
      'Explain any hard words. No headings, no tables, no bold or other formatting.',
  },
  describe_image: {
    instructions:
      'Describe this image for a blind or low-vision person. Start with one sentence saying what it is. ' +
      'Then describe the important details: people, objects, setting, colours, and the mood. ' +
      'Read out any text in the image exactly, including handwriting, and say that it is handwritten. ' +
      'If the person asks a question about the image, answer that first. Use plain words, no formatting.',
    image: true,
  },
  help_question: {
    instructions:
      'You answer questions about Voice Companion, a Windows app for blind and low-vision people, using only the guide sections given. ' +
      'Give the keys and the voice commands for each step. Use numbered steps for instructions, otherwise short sentences. ' +
      'No tables, no headings, no bold. If the guide sections do not answer the question, say you could not find it in the guide ' +
      'and suggest pressing F1 twice to open the full help.',
  },
};

const LIMITS = { text: 60000, question: 2000, guide: 40000, image: 8 * 1024 * 1024 };

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

function month(now) { return now.toISOString().slice(0, 7); }
function day(now) { return now.toISOString().slice(0, 10); }

async function count(env, key, ttl) {
  const used = parseInt((await env.USAGE.get(key)) || '0', 10) || 0;
  return {
    used,
    add: async () => env.USAGE.put(key, String(used + 1), { expirationTtl: ttl }),
  };
}

function buildInput(task, spec, body) {
  const parts = [];
  if (task === 'rewrite') {
    parts.push({ type: 'input_text', text: (spec.tones[body.tone] || spec.tones.clearer) + '\n\nText:\n' + body.text });
  } else if (task === 'describe_image') {
    parts.push({ type: 'input_text', text: body.question ? 'Question: ' + body.question : 'Describe this image.' });
    parts.push({ type: 'input_image', image_url: body.image });
  } else if (task === 'help_question') {
    parts.push({ type: 'input_text', text: 'Guide sections:\n' + body.guide + '\n\nQuestion: ' + body.question });
  } else {
    parts.push({ type: 'input_text', text: 'Text:\n' + body.text });
  }
  return [{ role: 'user', content: parts }];
}

function problem(task, body) {
  if (!TASKS[task]) return 'unknown task';
  if (task === 'describe_image') {
    if (typeof body.image !== 'string' || !/^data:image\/(png|jpe?g|gif|webp);base64,/.test(body.image)) return 'no image';
    if (body.image.length > LIMITS.image) return 'image too large';
    if (body.question && String(body.question).length > LIMITS.question) return 'question too long';
    return null;
  }
  if (task === 'help_question') {
    if (!body.question || String(body.question).length > LIMITS.question) return 'no question';
    if (String(body.guide || '').length > LIMITS.guide) return 'guide too long';
    return null;
  }
  if (typeof body.text !== 'string' || !body.text.trim()) return 'no text';
  if (body.text.length > LIMITS.text) return 'text too long';
  if (task === 'rewrite' && body.tone && !TASKS.rewrite.tones[body.tone]) return 'unknown tone';
  return null;
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

export async function handle(request, env, now = new Date(), fetcher = fetch) {
  const url = new URL(request.url);
  if (url.pathname === '/v1/health') return json({ ok: true });
  if (url.pathname !== '/v1/assist' || request.method !== 'POST') return json({ ok: false, error: 'not found' }, 404);
  const install = request.headers.get('X-Companion-Install') || '';
  if (!/^[0-9a-f]{32}$/.test(install)) return json({ ok: false, error: 'not voice companion' }, 403);
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: 'bad request' }, 400); }
  const task = String(body.task || '');
  const why = problem(task, body);
  if (why) return json({ ok: false, error: why }, 400);

  const monthly = parseInt(env.MONTHLY_LIMIT || '200', 10);
  const daily = parseInt(env.DAILY_LIMIT || '3000', 10);
  const mine = await count(env, 'm:' + month(now) + ':' + install, 40 * 86400);
  const all = await count(env, 'd:' + day(now), 3 * 86400);
  if (mine.used >= monthly) return json({ ok: false, error: 'monthly limit', limit: monthly }, 429);
  if (all.used >= daily) return json({ ok: false, error: 'busy' }, 429);

  const spec = TASKS[task];
  const reply = await fetcher('https://api.openai.com/v1/responses', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + env.OPENAI_API_KEY },
    body: JSON.stringify({
      model: env.MODEL,
      instructions: spec.instructions,
      input: buildInput(task, spec, body),
      ...(spec.json ? { text: { format: { type: 'json_object' } } } : {}),
      store: false,
    }),
  });
  if (!reply.ok) return json({ ok: false, error: 'ai service ' + reply.status }, 502);
  const text = outputText(await reply.json()).trim();
  await mine.add();
  await all.add();
  const result = { ok: true, remaining: Math.max(0, monthly - mine.used - 1) };
  if (spec.json) {
    try {
      const parsed = JSON.parse(text);
      result.corrections = Array.isArray(parsed.corrections) ? parsed.corrections.filter(
        (c) => c && typeof c.original === 'string' && typeof c.replacement === 'string' && body.text.includes(c.original)) : [];
    } catch {
      return json({ ok: false, error: 'ai answer unreadable' }, 502);
    }
  } else {
    result.text = text;
  }
  return json(result);
}

export default { fetch: (request, env) => handle(request, env) };
