# Releases-only repository

Installed copies of Voice Companion read updates from a public repository that holds only the
installers and the update file, and no source code. That lets the source repository become
private while updates keep reaching everyone.

## Where things are

- **Releases-only repository:** `willwalsh14-hub/voice-companion-releases`. It is public and holds no code.
- **Source repository:** `willwalsh14-hub/voice-companion-updates`. It can be made private once the releases repository works.
- **Update feed:** `voice_companion/update-settings.json`. `manifest_url` is the releases repository. `fallback_urls` is the source repository, used only while it is public.
- **Publishing:** `publish_release.py` publishes each release to every feed. The source repository uses the workflow's own token. The releases repository uses the `RELEASES_TOKEN` secret.

## One-time setup (Will)

1. Create the repository on GitHub. Choose **New repository**, name it `voice-companion-releases`, choose **Public**, and add a README so it is not empty. Do not add any code.
2. Create a token that can publish there. On GitHub, open **Settings**, **Developer settings**, **Personal access tokens**, **Fine-grained tokens**, then **Generate new token**.
   - Name: Voice Companion releases.
   - Expiration: the longest offered. Note the date: releases to this repository stop when it expires.
   - Repository access: **Only select repositories**, then `voice-companion-releases`.
   - Permissions: **Contents: Read and write**. Nothing else.
3. Copy the token. In the source repository, open **Settings**, **Secrets and variables**, **Actions**, then **New repository secret**. Name it `RELEASES_TOKEN`, and paste the token.
4. Tell Claude. The next release publishes to both repositories, and Claude checks the files arrived.

## Making the source repository private (Will)

Do this only after Claude confirms a release reached the releases repository, and after most copies have taken an update since then.

1. In the source repository, open **Settings**, then **General**.
2. At the bottom, under **Danger Zone**, choose **Change visibility**, then **Make private**.

Then:

- Build time on a private repository uses the free plan's included $12 a month. A self-hosted runner on a spare Windows PC is free.
- Testers can no longer see or file GitHub issues there. Bug reports need another way in, such as email.
- The privacy policy names the issues page as the contact. It needs another contact before the switch.
- Copies older than the release that moved the feed can no longer update, and need the installer once.
