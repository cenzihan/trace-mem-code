"""Opt-in Coding container; separate state with the same server-owned ledger."""
import os
import json
from pathlib import Path
import time

from .coding import CodingMemorySystem
from .coding_cards import CodingCards
from .container_app import read_service_token
from .embedding_cache import RUNTIME
from .embedding_smoke_app import read_embedding_token
from .provider_http import BAILIAN_BEIJING_ENDPOINT, SHARED_LEDGER
from .providers import TextEmbeddingV4
from .service_app import ServiceApplication
from .service_transport import ServiceTransport


class CodingServiceTransport(ServiceTransport):
    """Finite lifetime call counter over receipts, never another money ledger."""
    journal_scope = 'coding-development-v1'
    max_call_limit = 64

    def __init__(self,*args,call_limit,**kwargs):
        if type(call_limit) is not int or not 1 <= call_limit <= self.max_call_limit:
            raise ValueError(f'explicit1..{self.max_call_limit} provider-call cap required')
        self.call_limit = call_limit
        super().__init__(*args,**kwargs)
        self.limit_path = self.journal.root/'coding-call-limit.json'
        if self.limit_path.is_symlink():
            raise ValueError('coding call-cap symlink forbidden')
        if not self.limit_path.exists():
            with self.journal.connect() as db:
                if db.execute('SELECT count(*) FROM operations').fetchone()[0]:
                    raise ValueError('missing coding call cap after activity; never recreate it')
            try:
                with self.limit_path.open('x',encoding='utf-8') as handle:
                    handle.write(json.dumps({'schema':1,'max_calls':call_limit}))
                    handle.flush();os.fsync(handle.fileno())
            except FileExistsError:
                pass
        self.check_limit()

    def check_limit(self):
        if (self.limit_path.is_symlink() or not self.limit_path.is_file()
                or json.loads(self.limit_path.read_text()) != {'schema':1,'max_calls':self.call_limit}):
            raise ValueError('coding development cap is immutable; do not reset or increase it')

    def ready(self):
        self.check_limit()
        super().ready()
        with self.journal.connect() as db:
            count = db.execute('SELECT count(*) FROM operations').fetchone()[0]
        if count >= self.call_limit:
            raise ValueError('coding development call cap reached; no automatic reset')


def create_app(environ=None):
    env = os.environ if environ is None else environ
    if env.get('TRACEMEM_CODING_ENABLED') != 'isolated-original-ledger':
        raise ValueError('explicit isolated coding activation required')
    state = Path(env['TRACEMEM_CODING_STATE']).resolve()
    if not state.is_relative_to(RUNTIME.resolve()) or not state.name.startswith('coding-'):
        raise ValueError('separate coding runtime required')
    readers = {model:(lambda path=env[key]:read_embedding_token(path)) for model,key in
               [('gpt-4o-mini','TRACEMEM_OPENAI_TOKEN_FILE'),('text-embedding-v4','TRACEMEM_BAILIAN_TOKEN_FILE')]}
    transport = CodingServiceTransport(SHARED_LEDGER, env['TRACEMEM_LEDGER_AUTHORITY_FILE'],
        env['TRACEMEM_VERIFIED_PRICES_FILE'],state/'receipts',readers,
        call_limit=int(env['TRACEMEM_CODING_CALL_LIMIT']))
    expires = int(env['TRACEMEM_CODING_EXPIRES_AT'])
    if not time.time() < expires <= time.time()+7*86400:
        raise ValueError('explicit coding development lease within7days required')
    store = CodingMemorySystem(state/'memory.sqlite',card_adapter=CodingCards(transport),
                               embedding=TextEmbeddingV4(BAILIAN_BEIJING_ENDPOINT,transport,dimensions=256))
    # This candidate does not depend on or consume the frozen multimodal GPU scorer.
    return ServiceApplication(store,transport,read_service_token(env['TRACEMEM_AUTH_TOKEN_FILE']),
                              scorer_health=lambda:None,expires_at=expires)
