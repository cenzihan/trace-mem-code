"""Unreleased long-trajectory candidate; original Coding state and guards survive.

This expands transport admission, not provider context or authorization. Source
spans still use one GPT-4o-mini extraction and eight-item embedding batches.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading

from .coding import CodingMemorySystem, segments
from .coding_official_app import create_app as create_official_app
from .protocol import ContractError

VERSION = 'tracemem-code-v0.2.3-rc2'


def admission_reason(error):
    """Return fixed categories only, never an exception string or source value."""
    text = str(error)
    if error.status == 413:
        if text.startswith('coding capacity:') and text.endswith(' messages per Add'):
            return 'messages'
        for reason in ('message_source_bytes', 'add_source_bytes', 'source_segments'):
            if text.startswith('coding capacity:'+reason+' limit='):
                return reason
    if error.status == 503:
        for reason in ('remaining_provider_calls', 'remaining_original_budget'):
            if text == 'coding admission:'+reason:
                return reason
    return None


class BoundedAdmissionLog:
    """Private, capped operational metadata, under the existing state retention."""
    limit = 65536

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def __call__(self, error):
        reason = admission_reason(error)
        if reason is None:
            return
        raw = (json.dumps({'at': datetime.now(timezone.utc).isoformat(),
                           'status': error.status, 'reason': reason})+'\n').encode()
        with self.lock:
            try:
                if self.path.is_symlink():return
                if self.path.exists() and self.path.stat().st_size+len(raw)>self.limit:return
                fd = os.open(self.path, os.O_WRONLY|os.O_CREAT|os.O_APPEND, 0o600)
                with os.fdopen(fd, 'ab') as stream:stream.write(raw)
            except OSError:
                # A logging failure never changes an admission decision or
                # enables a provider call. No exception details are logged.
                return


class TrajectoryCodingMemory(CodingMemorySystem):
    model_add_message_limit = 1024
    dense_add_message_limit = 1024
    message_source_bytes = 2 * 1024 * 1024
    add_source_bytes = 8 * 1024 * 1024
    add_segments = 2048
    admission_check = None
    admission_diagnostic = None

    def add(self, payload):
        try:
            return super().add(payload)
        except ContractError as error:
            if self.admission_diagnostic is not None:
                self.admission_diagnostic(error)
            raise

    def _preflight_add(self, payload):
        super()._preflight_add(payload)
        count = sum(1 for m in payload['messages']
                    for _, _, source in segments(m['content']) if source.strip())
        if self.admission_check is not None:
            self.admission_check(count)

    def capabilities(self):
        return dict(super().capabilities(), version=VERSION,
                    max_add_messages=self.model_add_message_limit,
                    max_message_source_bytes=self.message_source_bytes,
                    max_add_source_bytes=self.add_source_bytes,
                    max_add_source_segments=self.add_segments,
                    embedding_batch_items=8,
                    add_commit='atomic-after-all-source-indexing',
                    admission_diagnostics='bounded-whitelist-no-content')


def admit_trajectory(transport, segments_count):
    """Read-only preflight; each call still reserves on the original ledger.

    The single admitted request lane prevents two local Add plans consuming the
    same remaining lifetime slots. Other services can consume shared funds, so
    this check supplements, never replaces, per-call money reservation.
    """
    transport.ready()
    required_calls = segments_count + (segments_count + 7) // 8
    with transport.journal.connect() as db:
        used = db.execute('SELECT count(*) FROM operations').fetchone()[0]
    if used + required_calls > transport.call_limit:
        raise ContractError('coding admission:remaining_provider_calls', 503)
    # Exact existing conservative GPT hold + full8192-token embedding admission,
    # at the fixed verified0.5CNY/million input rate. Keep the5CNY readiness floor.
    required_money = segments_count * (250000 + 4096) + 5000000
    if transport.ledger.totals()['remaining_micro_cny'] < required_money:
        raise ContractError('coding admission:remaining_original_budget', 503)


def create_app(environ=None):
    app = create_official_app(environ, memory_type=TrajectoryCodingMemory, version=VERSION)
    app.store.admission_check = lambda count: admit_trajectory(app.transport, count)
    env = os.environ if environ is None else environ
    app.store.admission_diagnostic = BoundedAdmissionLog(
        Path(env['TRACEMEM_CODING_STATE'])/'admission-metadata.jsonl')
    return app
