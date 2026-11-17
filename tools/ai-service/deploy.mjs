// Finds or creates the usage counter (a Workers KV namespace) and writes its id into
// wrangler.toml before deploying. Run by .github/workflows/ai-service.yml.
// Every failure names itself, so one failed run is enough to find the cause.
import { readFileSync, writeFileSync } from 'node:fs';

const TITLE = 'voice-companion-ai-usage';
const token = process.env.CLOUDFLARE_API_TOKEN || '';
let account = (process.env.CLOUDFLARE_ACCOUNT_ID || '').trim();
const fromUrl = account.match(/https?:\/\/([0-9a-f]{32})\./);   // the R2 secret may hold the S3 address
if (fromUrl) account = fromUrl[1];
if (!token) { console.log('::error::The CLOUDFLARE_API_TOKEN secret is missing. See tools/ai-service/README.md.'); process.exit(1); }
if (!/^[0-9a-f]{32}$/.test(account)) { console.log('::error::The Cloudflare account id is missing or not valid (R2_ACCOUNT_ID).'); process.exit(1); }
const api = 'https://api.cloudflare.com/client/v4/accounts/' + account + '/storage/kv/namespaces';
const headers = { authorization: 'Bearer ' + token, 'content-type': 'application/json' };

async function call(url, init) {
  const reply = await fetch(url, { headers, ...init });
  const body = await reply.json().catch(() => ({}));
  if (!reply.ok || !body.success) {
    const why = (body.errors || []).map((e) => e.message).join('; ') || ('status ' + reply.status);
    console.log('::error::Cloudflare refused: ' + why + '. The API token needs "Workers KV Storage: Edit" and "Workers Scripts: Edit".');
    process.exit(1);
  }
  return body.result;
}

const list = await call(api + '?per_page=100');
let space = list.find((n) => n.title === TITLE);
if (!space) {
  space = await call(api, { method: 'POST', body: JSON.stringify({ title: TITLE }) });
  console.log('Created the usage counter ' + TITLE + '.');
}
const toml = readFileSync(new URL('./wrangler.toml', import.meta.url), 'utf8').replace('FILLED_IN_AT_DEPLOY', space.id);
writeFileSync(new URL('./wrangler.toml', import.meta.url), toml);
writeFileSync(process.env.GITHUB_ENV || '/dev/null', 'CLOUDFLARE_ACCOUNT_ID=' + account + '\n', { flag: 'a' });
console.log('Usage counter ready.');
