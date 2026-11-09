"""Cloudflare R2 storage for published updates (November 2026).

Installers, the update feed and the guides live in an R2 bucket. Installed copies read them
over HTTPS from the bucket's public address (update-settings.json). The GitHub build writes to
the bucket through R2's S3-compatible API with three repository secrets:

  R2_ACCOUNT_ID         Cloudflare account ID
  R2_ACCESS_KEY_ID      R2 API token access key ID (Object Read and Write)
  R2_SECRET_ACCESS_KEY  R2 API token secret access key

The bucket name comes from the R2_BUCKET repository variable, or DEFAULT_BUCKET.

boto3 is imported only when a real bucket is opened, so tests and --help need no extra packages.
"""
import hashlib
import os
import re
from pathlib import Path

DEFAULT_BUCKET = 'voice-companion-updates'
SECRETS = ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY')

# The feed changes with every release, so nothing may keep an old copy of it.
NO_CACHE = 'no-cache, max-age=0'
# Files in a release folder never change once published.
FOREVER = 'public, max-age=31536000, immutable'

CONTENT_TYPES = {
    '.exe': 'application/vnd.microsoft.portable-executable',
    '.json': 'application/json',
    '.txt': 'text/plain; charset=utf-8',
    '.html': 'text/html; charset=utf-8',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.epub': 'application/epub+zip',
    '.zip': 'application/zip',
    '.brf': 'text/plain; charset=us-ascii',
    '.gz': 'application/gzip',
}


class MissingSetup(RuntimeError):
    """The secrets needed to write to the bucket are not there."""


class BadSetup(ValueError):
    """A secret is there but cannot be right. The message says why, never the value."""


ACCOUNT_ID = re.compile(r'[0-9a-f]{32}')


def account_id(raw):
    """The Cloudflare account ID from R2_ACCOUNT_ID.

    Cloudflare shows the ID next to a full address (the S3 API address,
    https://<id>.r2.cloudflarestorage.com), and both are easy to copy. Accept the
    ID, that address, or a dashboard address with the ID in it. Anything else
    stops with a reason that names the secret and describes the problem without
    showing the value (November 9, 2026: a pasted address gave only "Invalid endpoint").
    """
    text = str(raw).strip().lower()
    if ACCOUNT_ID.fullmatch(text):
        return text
    if '://' in text or '/' in text or '.' in text:
        found = set(re.findall(r'(?<![0-9a-z])([0-9a-f]{32})(?![0-9a-z])', text))
        if len(found) == 1:
            return found.pop()
    problems = ['it is ' + str(len(text)) + ' characters long']
    if '://' in text:
        problems.append('it is a web address')
    if re.search(r'\s', text):
        problems.append('it has spaces or line breaks inside it')
    if re.search(r'[^0-9a-f]', text) and '://' not in text:
        problems.append('it has characters other than 0 to 9 and a to f')
    raise BadSetup('The R2_ACCOUNT_ID secret is not a Cloudflare account ID: ' + ', and '.join(problems)
                   + '. It must be the 32-character Account ID from the R2 overview page in Cloudflare.'
                   + ' Replace it in the repository settings, under Secrets and variables, Actions.')


def content_type(name):
    name = str(name)
    if name == 'COPYING':
        return CONTENT_TYPES['.txt']
    return CONTENT_TYPES.get(Path(name).suffix.lower(), 'application/octet-stream')


def missing_secrets(environ=os.environ):
    return [name for name in SECRETS if not str(environ.get(name, '')).strip()]


class R2Store:
    """One bucket. Every method names the object by its key (its path in the bucket)."""

    def __init__(self, client, bucket):
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_environment(cls, environ=os.environ):
        missing = missing_secrets(environ)
        if missing:
            raise MissingSetup('These repository secrets are missing: ' + ', '.join(missing) + '.')
        account = account_id(environ['R2_ACCOUNT_ID'])
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise MissingSetup('The boto3 package is not installed for publishing.') from exc
        client = boto3.client(
            's3',
            endpoint_url='https://' + account + '.r2.cloudflarestorage.com',
            aws_access_key_id=environ['R2_ACCESS_KEY_ID'].strip(),
            aws_secret_access_key=environ['R2_SECRET_ACCESS_KEY'].strip(),
            region_name='auto',
            # R2 does not accept every checksum header newer boto3 sends by default.
            config=Config(retries={'max_attempts': 6, 'mode': 'standard'},
                          request_checksum_calculation='when_required',
                          response_checksum_validation='when_required'))
        bucket = str(environ.get('R2_BUCKET') or '').strip() or DEFAULT_BUCKET
        return cls(client, bucket)

    @staticmethod
    def _missing(exc):
        # Only a missing object. A missing bucket (NoSuchBucket) is also HTTP 404, but it is a
        # setup mistake that must stop publishing, not "nothing published yet".
        error = (getattr(exc, 'response', None) or {}).get('Error') or {}
        return error.get('Code') in ('NoSuchKey', '404', 'NotFound')

    def read(self, key):
        """The object's bytes, or None when there is no such object."""
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if self._missing(exc):
                return None
            raise
        with response['Body'] as body:
            return body.read()

    def size(self, key):
        """The object's size in bytes, or None when there is no such object."""
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if self._missing(exc):
                return None
            raise
        return int(response['ContentLength'])

    def upload(self, path, key, cache_control=FOREVER):
        """Upload a file. Large files go up in parts; one failed part is retried."""
        self.client.upload_file(str(path), self.bucket, key, ExtraArgs={
            'ContentType': content_type(Path(path).name), 'CacheControl': cache_control})

    def put(self, data, key, cache_control=NO_CACHE):
        """Write a small object in one request. Readers see the old or the new one, never half."""
        self.client.put_object(Bucket=self.bucket, Key=key, Body=bytes(data),
                               ContentType=content_type(key), CacheControl=cache_control)

    def copy(self, source, key, cache_control=NO_CACHE):
        self.client.copy({'Bucket': self.bucket, 'Key': source}, self.bucket, key, ExtraArgs={
            'ContentType': content_type(key), 'CacheControl': cache_control, 'MetadataDirective': 'REPLACE'})

    def sha256(self, key):
        """Download the object and return its SHA-256, or None when there is no such object."""
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if self._missing(exc):
                return None
            raise
        digest = hashlib.sha256()
        with response['Body'] as body:
            for block in iter(lambda: body.read(1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest()


class MemoryStore:
    """A bucket kept in memory, for tests. Same methods as R2Store."""

    def __init__(self):
        self.objects = {}
        self.cache = {}
        self.log = []

    def read(self, key):
        self.log.append(('read', key))
        return self.objects.get(key)

    def size(self, key):
        self.log.append(('size', key))
        return len(self.objects[key]) if key in self.objects else None

    def upload(self, path, key, cache_control=FOREVER):
        self.log.append(('upload', key))
        self.objects[key] = Path(path).read_bytes()
        self.cache[key] = cache_control

    def put(self, data, key, cache_control=NO_CACHE):
        self.log.append(('put', key))
        self.objects[key] = bytes(data)
        self.cache[key] = cache_control

    def copy(self, source, key, cache_control=NO_CACHE):
        self.log.append(('copy', key))
        self.objects[key] = self.objects[source]
        self.cache[key] = cache_control

    def sha256(self, key):
        self.log.append(('sha256', key))
        return hashlib.sha256(self.objects[key]).hexdigest() if key in self.objects else None
