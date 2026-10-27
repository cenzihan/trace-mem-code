"""Unreleased long-trajectory candidate; original Coding state and guards survive.

This expands transport admission, not provider context or authorization. Source
spans still use one GPT-4o-mini extraction and eight-item embedding batches.
"""
from .coding import CodingMemorySystem, segments
from .coding_official_app import create_app as create_official_app
from .protocol import ContractError

VERSION = 'tracemem-code-v0.2.3-rc1'


class TrajectoryCodingMemory(CodingMemorySystem):
    model_add_message_limit = 1024
    dense_add_message_limit = 1024
    message_source_bytes = 2 * 1024 * 1024
    add_source_bytes = 8 * 1024 * 1024
    add_segments = 2048
    admission_check = None

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
                    add_commit='atomic-after-all-source-indexing')


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
    return app
