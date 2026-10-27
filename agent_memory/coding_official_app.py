"""Versioned Coding access profile; the original money ledger stays authoritative."""
import os
from pathlib import Path
import time

from .coding import CodingMemorySystem
from .coding_app import CodingServiceTransport
from .coding_cards import CodingCards
from .container_app import read_service_token
from .embedding_cache import RUNTIME
from .embedding_smoke_app import read_embedding_token
from .provider_http import BAILIAN_BEIJING_ENDPOINT, SHARED_LEDGER
from .providers import TextEmbeddingV4
from .service_app import ServiceApplication

VERSION = 'tracemem-code-v0.2.2'


class OfficialCodingTransport(CodingServiceTransport):
    journal_scope = 'coding-official-v0.2'
    max_call_limit = 512


class OfficialCodingMemory(CodingMemorySystem):
    model_add_message_limit = 20


def create_app(environ=None, *, memory_type=OfficialCodingMemory, version=VERSION,
               transport_type=OfficialCodingTransport, source_cards=True):
    if type(source_cards) is not bool:
        raise ValueError('explicit source indexing mode required')
    env = os.environ if environ is None else environ
    if env.get('TRACEMEM_CODING_ENABLED') != 'official-original-ledger-v0.2':
        raise ValueError('explicit versioned Coding activation required')
    state = Path(env['TRACEMEM_CODING_STATE']).resolve()
    if not state.is_relative_to(RUNTIME.resolve()) or state.name != 'coding-official-v0.2':
        raise ValueError('dedicated official state required; never reuse the development grant')
    expires = int(env['TRACEMEM_CODING_EXPIRES_AT'])
    if not time.time() < expires <= time.time()+28*86400:
        raise ValueError('explicit bounded official lease required')
    # This deployment fixes a new traffic guard, not another CNY budget.
    if env.get('TRACEMEM_CODING_CALL_LIMIT') != '512':
        raise ValueError('fixed512-call official lifetime ceiling required')
    readers = {model:(lambda path=env[key]:read_embedding_token(path)) for model,key in
               [('gpt-4o-mini','TRACEMEM_OPENAI_TOKEN_FILE'),('text-embedding-v4','TRACEMEM_BAILIAN_TOKEN_FILE')]}
    transport = transport_type(SHARED_LEDGER,env['TRACEMEM_LEDGER_AUTHORITY_FILE'],
        env['TRACEMEM_VERIFIED_PRICES_FILE'],state/'receipts',readers,call_limit=512)
    store = memory_type(state/'memory.sqlite',context_policy='source-window',
        card_adapter=CodingCards(transport,structured_output=True) if source_cards else None,
        embedding=TextEmbeddingV4(BAILIAN_BEIJING_ENDPOINT,transport,dimensions=256))
    capabilities = store.capabilities
    store.capabilities = lambda:dict(capabilities(),version=version,
        deployment_profile='coding-official-v0.2',release_stage='access-candidate',
        source_card_format='strict-json-schema' if source_cards else 'disabled-raw-source',max_add_messages=store.model_add_message_limit,
        concurrency=16,model_concurrency=1,receipt_content_logging=False)
    return ServiceApplication(store,transport,read_service_token(env['TRACEMEM_AUTH_TOKEN_FILE']),
        scorer_health=lambda:None,expires_at=expires,admission_capacity=16,queue_wait_seconds=30)
