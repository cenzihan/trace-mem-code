"""Offline candidate: bounded raw trajectory indexing, no LLM dispatch.

Keep the original Coding state, provider journal, money ledger and call ceiling.
Previously stored source summaries remain intact; new writes index raw spans.
"""
import os
from pathlib import Path

from .coding_official_app import OfficialCodingTransport, create_app as create_official_app
from .coding_trajectory_app import (TrajectoryCodingMemory, BoundedAdmissionLog,
                                    SEARCH_CALL_RESERVE)
from .protocol import ContractError
from .provider_http import BAILIAN_BEIJING_ENDPOINT

VERSION = 'tracemem-code-raw-v0.3.0-rc1'


class RawCodingTransport(OfficialCodingTransport):
    def __call__(self, endpoint, payload):
        # Reject before journal preparation, money reservation or credential access.
        if payload.get('model') != 'text-embedding-v4' or endpoint != BAILIAN_BEIJING_ENDPOINT:
            raise ValueError('raw Coding permits only text-embedding-v4')
        return super().__call__(endpoint, payload)


class RawTrajectoryCodingMemory(TrajectoryCodingMemory):
    def __init__(self, *args, **kwargs):
        if kwargs.get('card_adapter') is not None:
            raise ValueError('raw Coding cannot construct an LLM source adapter')
        super().__init__(*args, **kwargs)

    def capabilities(self):
        return dict(super().capabilities(), version=VERSION,
                    source_indexing='raw-source-spans', new_source_llm_calls=0,
                    legacy_source_indexes_preserved=True,
                    model='text-embedding-v4', generated_answers=False)


def admit_raw_trajectory(transport, segments_count):
    if type(segments_count) is not int or not 0 <= segments_count <= 2048:
        raise ValueError('bounded source span count required')
    transport.ready()
    required_calls = (segments_count + 7) // 8
    with transport.journal.connect() as db:
        used = db.execute('SELECT count(*) FROM operations').fetchone()[0]
    if used + required_calls + SEARCH_CALL_RESERVE > transport.call_limit:
        raise ContractError('coding admission:remaining_provider_calls', 503)
    # Per-item full8192-token conservative allowance plus sixteen queries and
    # the unchanged5CNY readiness floor. Per-call reservation remains authoritative.
    required_money = (segments_count + SEARCH_CALL_RESERVE) * 4096 + 5000000
    if transport.ledger.totals()['remaining_micro_cny'] < required_money:
        raise ContractError('coding admission:remaining_original_budget', 503)


def create_app(environ=None):
    env = os.environ if environ is None else environ
    if env.get('TRACEMEM_CODING_RAW_ENABLED') != 'approved-raw-original-state':
        raise ValueError('explicit raw Coding activation required')
    app = create_official_app(env, memory_type=RawTrajectoryCodingMemory,
        version=VERSION, transport_type=RawCodingTransport, source_cards=False)
    app.store.admission_check = lambda count: admit_raw_trajectory(app.transport, count)
    app.store.admission_diagnostic = BoundedAdmissionLog(
        Path(env['TRACEMEM_CODING_STATE'])/'admission-metadata.jsonl')
    return app
