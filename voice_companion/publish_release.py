"""Publish only a checked Windows build using the trainer's GitHub CLI session."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from app_updates import MAX_INSTALLER, https_url, version_key
from guide_files import GUIDE_NAMES, guide_sources, published_name
from release_documents import load_notes, validate, STEM

ROOT = Path(__file__).parent


def release_manifest(setup, version, installer_url):
    version_key(version); https_url(installer_url)
    setup = Path(setup)
    if not setup.is_file() or setup.suffix.lower() != '.exe': raise ValueError('Choose the finished Setup EXE, not a source ZIP.')
    if not 1 <= setup.stat().st_size <= MAX_INSTALLER: raise ValueError('The installer must be smaller than 2 GiB for GitHub Releases.')
    with setup.open('rb') as source:
        if source.read(2) != b'MZ': raise ValueError('Choose a Windows Setup EXE.')
        source.seek(0); digest = hashlib.file_digest(source,'sha256').hexdigest()
    return {'schema':1,'version':version,'installer_url':installer_url,'sha256':digest,'size':setup.stat().st_size}


LOG_PATH = None
PROGRESS_INTERVAL = 20


def progress(message):
    print(message, flush=True)
    if LOG_PATH is not None:
        with Path(LOG_PATH).open('a', encoding='utf-8') as log:
            log.write(time.strftime('%H:%M:%S') + ' ' + message + '\n')


def operation_label(args):
    if args[0] == 'api': return 'Checking GitHub repository or release status'
    action = args[1]
    if action == 'upload': return 'Uploading ' + Path(args[3]).name
    if action == 'download': return 'Downloading for verification: ' + args[args.index('--pattern')+1]
    return {'create':'Creating the draft release', 'edit':'Publishing the verified release as latest'}.get(action, 'Contacting GitHub')


# The token for the releases-only repository (a repository secret named RELEASES_TOKEN).
# The workflow's own token can publish only to the repository it runs in.
GH_ENV = None


def gh_call(gh, *args, missing_ok=False):
    label = operation_label(args)
    progress(label + '.')
    started = time.monotonic()
    with subprocess.Popen([str(gh), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding='utf-8', errors='replace', env=GH_ENV) as process:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=PROGRESS_INTERVAL)
                break
            except subprocess.TimeoutExpired:
                elapsed = int(time.monotonic() - started)
                progress(f'Still waiting: {label}. {elapsed} seconds elapsed. Keep this window open.')
        if process.returncode:
            if missing_ok and 'HTTP 404' in stderr: return None
            raise RuntimeError(label + ' failed. Check sign-in, repository permissions, internet access, and retry publishing.')
    progress(label + ' completed.')
    return stdout


FEED = r'https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/releases/latest/download/voice-companion-update\.json'


def feed_repos(root=ROOT):
    """The repositories whose release feeds installed copies read: the main feed first, then
    the fallbacks (update-settings.json). Each release is published to every one of them."""
    settings = json.loads((Path(root)/'update-settings.json').read_text())
    repos = []
    for feed in [settings['manifest_url'], *(settings.get('fallback_urls') or [])]:
        match = re.fullmatch(FEED, feed)
        if not match:
            raise ValueError('Automatic publishing requires a configured GitHub release feed.')
        if match[1] not in repos:
            repos.append(match[1])
    return repos


def publish(setup, gh='gh', root=ROOT, repo=None):
    root = Path(root)
    version = re.search(r"APP_VERSION = '([^']+)'", (root/'companion.py').read_text())[1]
    repo = repo or feed_repos(root)[0]
    tag = 'v' + version
    url = f'https://github.com/{repo}/releases/download/{tag}/VoiceCompanion-Setup.exe'
    progress('Preparing release '+version+'. Checking the local installer and successful-build record.')
    manifest = release_manifest(setup, version, url)
    receipt = json.loads((root/'VoiceCompanion-Build-Passed.json').read_text(encoding='utf-8-sig'))
    if receipt != {'version':version, 'sha256':manifest['sha256'], 'size':manifest['size']}:
        raise ValueError('This installer does not match the successful Windows build checks. Rebuild it before publishing.')
    load_notes(root)
    validate(root)
    guide_sources([root], expected_version=version)
    documentation = [root/name for name in GUIDE_NAMES]
    if not all(path.is_file() for path in documentation):
        raise ValueError('All manual and release-note formats are required before publishing.')
    metadata = json.loads(gh_call(gh, 'api', f'repos/{repo}'))
    # Workflow installation tokens may omit the permissions object. GitHub
    # still enforces write authorization when creating or uploading the draft.
    permissions = metadata.get('permissions')
    workflow_token = os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REPOSITORY') == repo
    if metadata.get('private') is not False:
        raise ValueError('Publishing requires a public repository.')
    if not workflow_token and permissions is not None and not permissions.get('push'):
        raise ValueError('Publishing requires repository write permission.')
    if workflow_token:
        progress('Using the repository workflow token. GitHub will enforce release write permission on the draft upload.')
    latest = gh_call(gh, 'api', f'repos/{repo}/releases/latest', missing_ok=True)
    if latest:
        latest_tag = json.loads(latest)['tag_name']
        if version_key(latest_tag.removeprefix('v')) > version_key(version):
            raise ValueError('A newer release is already published. Increase the version before building.')
    existing = gh_call(gh, 'api', f'repos/{repo}/releases/tags/{tag}', missing_ok=True)
    if existing and not json.loads(existing)['draft']:
        raise ValueError('This version is already published. Published installers are never overwritten; increase the version and rebuild.')
    output = root/'release-upload'; output.mkdir(exist_ok=True)
    installer = output/'VoiceCompanion-Setup.exe'; shutil.copy2(setup, installer)
    manifest_path = output/'voice-companion-update.json'
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    source = root/'espeak'/'espeak-ng-1.52.0-source.tar.gz'
    license_path = root/'espeak'/'COPYING'
    if not source.is_file() or not license_path.is_file():
        raise ValueError('The bundled eSpeak source and license are required for distribution.')
    notes = output/'release-notes.txt'
    notes.write_text((root/(STEM+'.txt')).read_text(encoding='utf-8'), encoding='utf-8')
    if not existing:
        gh_call(gh, 'release', 'create', tag, '--repo', repo, '--draft', '--title', 'Voice Companion '+version, '--notes-file', str(notes))
    else:
        gh_call(gh, 'release', 'edit', tag, '--repo', repo, '--notes-file', str(notes))
    assets = [installer, manifest_path, source, license_path]
    for document in documentation:
        safe_name = re.sub('-+', '-', re.sub(r'[^A-Za-z0-9._-]+', '-', published_name(document.name,version)))
        copy = output/safe_name
        shutil.copy2(document, copy)
        assets.append(copy)
    for asset in assets:
        progress(f'Upload file: {asset.name}. Size: {asset.stat().st_size / (1024*1024):.1f} MB.')
        gh_call(gh, 'release', 'upload', tag, str(asset), '--repo', repo, '--clobber')
    # Verify every uploaded byte while still a draft. Incomplete releases stay invisible to clients.
    with tempfile.TemporaryDirectory() as folder:
        for asset in assets:
            gh_call(gh, 'release', 'download', tag, '--repo', repo, '--pattern', asset.name, '--dir', folder)
            downloaded = Path(folder)/asset.name
            progress('Checking downloaded checksum: '+asset.name+'.')
            with asset.open('rb') as local, downloaded.open('rb') as remote:
                if hashlib.file_digest(local, 'sha256').digest() != hashlib.file_digest(remote, 'sha256').digest():
                    raise ValueError('Uploaded files did not pass verification. The release remains a draft; retry publishing.')
    gh_call(gh, 'release', 'edit', tag, '--repo', repo, '--draft=false', '--prerelease=false', '--latest')
    visible = json.loads(gh_call(gh, 'api', f'repos/{repo}/releases/latest'))
    if visible['tag_name'] != tag or visible['draft'] or visible['prerelease']:
        raise RuntimeError('Could not verify this release as latest. Check GitHub before retrying.')
    confirmation = {'version':version, 'sha256':manifest['sha256'], 'url':visible['html_url']}
    temporary = root/'VoiceCompanion-Published.tmp'
    temporary.write_text(json.dumps(confirmation), encoding='utf-8')
    temporary.replace(root/'VoiceCompanion-Published.json')
    return visible['html_url']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--setup', required=True);parser.add_argument('--gh', default='gh')
    args=parser.parse_args()
    global LOG_PATH
    LOG_PATH = ROOT/'VoiceCompanion-Publish-Log.txt'
    LOG_PATH.write_text('Voice Companion publishing progress\n', encoding='utf-8')
    return publish_everywhere(args.setup, args.gh)


def token_for(repo, environ=os.environ):
    """The environment for gh to publish to repo: the workflow's own token for its own repository,
    RELEASES_TOKEN for the releases-only repository. None when there is no token for it."""
    if environ.get('GITHUB_ACTIONS') != 'true' or environ.get('GITHUB_REPOSITORY') == repo:
        return dict(environ)
    token = environ.get('RELEASES_TOKEN', '')
    if not token:
        return None
    env = dict(environ); env['GH_TOKEN'] = token
    return env


def annotate(environ, level, title, message):
    """On GitHub, show the result for each repository in the run's annotations, which can be
    read without the full log (CLAUDE.md: every failure must name itself)."""
    if environ.get('GITHUB_ACTIONS') == 'true':
        clean = str(message).replace('%', '%25').replace('\r', '').replace('\n', '%0A')
        print('::' + level + ' title=' + title + '::' + clean, flush=True)


def publish_everywhere(setup, gh='gh', root=ROOT, environ=os.environ):
    """Publish to every feed's repository. Succeeds when at least one has the verified release;
    each repository that could not be published to says why."""
    global GH_ENV
    published = []
    try:
        repos = feed_repos(root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        progress('BUILD PASSED, PUBLISHING FAILED: '+str(exc)); return 1
    for repo in repos:
        env = token_for(repo, environ)
        if env is None:
            reason = 'the RELEASES_TOKEN secret is missing. Installed copies use the other feed.'
            progress('NOT PUBLISHED TO '+repo+': '+reason)
            annotate(environ, 'warning', 'Not published to '+repo, reason)
            continue
        GH_ENV = env
        try:
            url = publish(setup, gh, root, repo=repo)
            progress('PUBLISHED AND VERIFIED: '+url)
            annotate(environ, 'notice', 'Published to '+repo, url)
            published.append(repo)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            progress('NOT PUBLISHED TO '+repo+': '+str(exc))
            annotate(environ, 'warning', 'Not published to '+repo, str(exc))
        finally:
            GH_ENV = None
    if published:
        return 0
    progress('BUILD PASSED, PUBLISHING FAILED: no feed could be published.')
    progress('Nothing was shared. Run the GitHub build again to retry.')
    return 1

if __name__ == '__main__': raise SystemExit(main())

