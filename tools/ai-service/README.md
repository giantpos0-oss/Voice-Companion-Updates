# Voice Companion AI service

## What it is

- A small Cloudflare service at ai.voicecompanionapp.com.
- It answers the Reading Assistant, Writing Assistant, Describe Image and Ask a Question.
- It holds the OpenAI key, so users need no account of their own.
- It only does Companion's own tasks. It cannot be used as a general chatbot.

## Limits

- Reading and writing help has no monthly limit (`MONTHLY_LIMIT` is 0 in `wrangler.toml`). Set a number there to bring one back.
- Pictures (Describe the image and Ask about the image) are limited to 200 a month for each copy (`IMAGE_MONTHLY_LIMIT`), as in GuideConnect.
- The real stop is the monthly spending limit in the OpenAI account.
- The whole service also stops at 20,000 requests a day (`DAILY_LIMIT`), so a runaway mistake or misuse cannot use the whole budget in one day.
- A request that fails is not counted.
- The model is set by `MODEL` in `wrangler.toml`. Change it there to switch models without a Companion update.

## Setting it up (once)

1. In your OpenAI account, create an API key and add a payment method. Set a monthly spending limit there too.
2. In Cloudflare, create an API token with these permissions: "Workers Scripts: Edit", "Workers KV Storage: Edit", and "Workers Routes: Edit" plus "DNS: Edit" for voicecompanionapp.com.
3. In the GitHub repository, add two secrets: `OPENAI_API_KEY` and `CLOUDFLARE_API_TOKEN`.
4. Run the "Deploy AI service" workflow. Its last step checks that the service answers.

## Updating it

- A merge to `main` that changes `tools/ai-service/` deploys it again by itself.
- Run the tests with `node tools/ai-service/test-worker.mjs`.
