"""Withdrawn wire-format routing experiment; do not serve official evaluations.

The AML contract permits string Multimodal requests, so the types overlap.
Use an explicitly selected fixed backend; see docs/shared-endpoint.md.
No model, dataset inspection, persistence, request logging or automatic retries.
The original request and response bytes pass through unchanged.
"""
import hmac
import http.client
import json
import os
import threading
import time

from .container_app import read_service_token

VERSION = 'tracemem-multitrack-gateway-v1.0.0'
COMPONENTS = {'coding': (8770, 'tracemem-code-v0.2.2'),
              'multimodal': (8769, 'tracemem-mm-bailian-v2.0.4')}
MAX_BODY = 64 * 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('nonfinite JSON constant')


def classify(path, raw):
    """Use only the documented JSON types, never identifiers or text meaning."""
    value = json.loads(raw, object_pairs_hook=unique_object,
                       parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError('JSON object required')
    if path == '/search':
        content = value.get('query')
        if isinstance(content, str) and content.strip():
            return 'coding'
        if isinstance(content, list) and content:
            return 'multimodal'
        raise ValueError('query format required')
    messages = value.get('messages')
    if not isinstance(messages, list) or not messages:
        raise ValueError('messages required')
    if any(not isinstance(m, dict) or not isinstance(m.get('content'), (str, list))
           for m in messages):
        raise ValueError('content format required')
    # Native MM histories may include plain assistant replies after image parts.
    # Text-only MM must still use ContentPart[] as required by the AML guide.
    return 'multimodal' if any(isinstance(m['content'], list) for m in messages) else 'coding'


class ResponseStream:
    """Explicit close also releases resources before the first iteration."""
    def __init__(self, response, connection, admission):
        self.response=response; self.connection=connection; self.admission=admission
        self.total=0; self.closed=False

    def __iter__(self):return self

    def __next__(self):
        if self.closed:raise StopIteration
        try:
            block=self.response.read(65536)
            if not block:
                self.close();raise StopIteration
            self.total+=len(block)
            if self.total>MAX_BODY:raise OSError('upstream response capacity exceeded')
            return block
        except BaseException:
            self.close();raise

    def close(self):
        if not self.closed:
            self.closed=True
            try:self.connection.close()
            finally:self.admission.release()


class Gateway:
    def __init__(self, key, expires_at, *, connection=http.client.HTTPConnection):
        self.key = key
        self.expires_at = expires_at
        self.connection = connection
        self.admissions = threading.BoundedSemaphore(32)
        # Only one body is decoded/sent at once. Release it before waiting for
        # model processing; stream responses rather than collecting image arrays.
        self.body_slot = threading.Lock()

    @staticmethod
    def reply(start, code, value, headers=()):
        raw = json.dumps(value, separators=(',', ':')).encode()
        start(f'{code} {http.client.responses[code]}', [
            ('Content-Type', 'application/json'), ('Content-Length', str(len(raw))),
            ('Cache-Control', 'no-store'), *headers])
        return [raw]

    def health(self, start):
        components = {}
        for name, (port, expected) in COMPONENTS.items():
            conn = self.connection('127.0.0.1', port, timeout=5)
            try:
                conn.request('GET', '/health')
                response = conn.getresponse()
                value = json.loads(response.read(65537))
                components[name] = {'version': value.get('version'),
                    'ready': response.status == 200 and value.get('version') == expected}
            except Exception:
                components[name] = {'version': None, 'ready': False}
            finally:
                conn.close()
        ready = all(c['ready'] for c in components.values())
        return self.reply(start, 200 if ready else 503,
            {'status': 'ok' if ready else 'not_ready', 'version': VERSION,
             'components': components, 'routing': 'documented-content-type',
             'request_logging': False, 'provider_retries': 0})

    def __call__(self, env, start):
        if time.time() >= self.expires_at:
            return self.reply(start, 503, {'error': 'deployment lease expired'})
        path = env.get('PATH_INFO')
        method = env.get('REQUEST_METHOD')
        if path == '/health' and method == 'GET':
            return self.health(start)
        if path not in ('/add', '/search'):
            return self.reply(start, 404, {'error': 'unknown endpoint'})
        if method != 'POST':
            return self.reply(start, 405, {'error': 'POST required'})
        auth = str(env.get('HTTP_AUTHORIZATION', '')).encode('utf-8')
        if not hmac.compare_digest(auth, ('Bearer '+self.key).encode('utf-8')):
            return self.reply(start, 401, {'error': 'unauthorized'})
        if env.get('CONTENT_TYPE', '').split(';', 1)[0].strip().lower() != 'application/json':
            return self.reply(start, 415, {'error': 'application/json required'})
        try:
            length = int(env.get('CONTENT_LENGTH', ''))
        except (ValueError, TypeError):
            return self.reply(start, 411, {'error': 'Content-Length required'})
        if not 0 < length <= MAX_BODY:
            return self.reply(start, 413, {'error': 'body capacity exceeded'})
        if not self.admissions.acquire(blocking=False):
            return self.reply(start, 429, {'error': 'admission capacity reached'}, [('Retry-After', '5')])
        conn = None
        try:
            with self.body_slot:
                raw = env['wsgi.input'].read(length)
                if len(raw) != length:
                    raise ValueError('incomplete body')
                target = classify(path, raw)
                if time.time() >= self.expires_at:
                    self.admissions.release()
                    return self.reply(start, 503, {'error': 'deployment lease expired'})
                conn = self.connection('127.0.0.1', COMPONENTS[target][0], timeout=1890)
                conn.request('POST', path, body=raw, headers={
                    'Content-Type': env['CONTENT_TYPE'], 'Authorization': 'Bearer '+self.key})
                del raw
            response = conn.getresponse()
            content_length = response.getheader('Content-Length')
            if content_length is not None and not 0 <= int(content_length) <= MAX_BODY:
                raise OSError('upstream response exceeds capacity')
            headers = [('Content-Type', 'application/json'), ('Cache-Control', 'no-store'),
                       ('X-TraceMem-Component', target)]
            if content_length is not None:
                headers.append(('Content-Length', content_length))
            retry_after = response.getheader('Retry-After')
            if retry_after and retry_after.isdecimal():
                headers.append(('Retry-After', retry_after))
            start(f'{response.status} {http.client.responses.get(response.status, "Upstream response")}', headers)
        except (ValueError, UnicodeError):
            if conn: conn.close()
            self.admissions.release()
            return self.reply(start, 400, {'error': 'invalid request or response format'})
        except Exception:
            if conn: conn.close()
            self.admissions.release()
            return self.reply(start, 502, {'error': 'upstream unavailable; request was not retried'})

        return ResponseStream(response, conn, self.admissions)


def create_app(environ=None):
    env = os.environ if environ is None else environ
    if env.get('TRACEMEM_GATEWAY_ENABLED') != 'documented-multitrack-v1':
        raise ValueError('explicit gateway activation required')
    expires = int(env['TRACEMEM_GATEWAY_EXPIRES_AT'])
    if not time.time() < expires <= time.time()+28*86400:
        raise ValueError('bounded existing lease required')
    return Gateway(read_service_token(env['TRACEMEM_AUTH_TOKEN_FILE']), expires)
