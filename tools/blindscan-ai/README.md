# BlindScan AI service

## What it is

- A Cloudflare Worker that answers "Ask a question" in BlindScan, Will's free Android scanner.
- Address: blindscan-ai.voicecompanionapp.com
- It uses Voice Companion's Cloudflare account and OpenAI key, so BlindScan users need no key.
- It only answers BlindScan's question task. Its instructions are kept here, so the key can't be used as a general chatbot.
- No per-user limits (Will, November 23, 2026). The OpenAI spending limit is the stop.
- Model: set by MODEL in wrangler.toml.

## How it is deployed

- `.github/workflows/blindscan-ai.yml` tests and deploys it on any push that changes `tools/blindscan-ai/`.
- It never touches Voice Companion or its AI service.
