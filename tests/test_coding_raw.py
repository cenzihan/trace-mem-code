"""Independent synthetic trajectory controls; no external model calls."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

from agent_memory.coding_raw_app import (RawCodingTransport, RawTrajectoryCodingMemory,
    admit_raw_trajectory, create_app)
from agent_memory.protocol import ContractError
from agent_memory.provider_http import OPENAI_ENDPOINT
from test_coding import Cards, Embedding


class RawTrajectoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'memory.sqlite'
        self.embedding = Embedding()
        self.store = self.open()

    def open(self):
        return RawTrajectoryCodingMemory(self.path, embedding=self.embedding,
                                         context_policy='source-window')

    def payload(self, texts, request='raw'):
        return dict(user_id='owner', request_id=request, session_id='independent',
                    messages=[dict(role='user', content=t) for t in texts])

    def transport(self, used=11, remaining=100000000):
        path = Path(self.tmp.name)/('receipts-'+str(used)+'.sqlite')
        @contextmanager
        def connect():
            db = sqlite3.connect(path)
            try:
                with db: yield db
            finally: db.close()
        with connect() as db:
            db.execute('CREATE TABLE operations(id INTEGER)')
            db.executemany('INSERT INTO operations VALUES(?)', [(i,) for i in range(used)])
        return SimpleNamespace(ready=lambda:None, call_limit=512,
            journal=SimpleNamespace(connect=connect),
            ledger=SimpleNamespace(totals=lambda:{'remaining_micro_cny':remaining}))

    def test_full_admitted_trajectory_atomic_replay_and_source_integrity(self):
        texts = ['HTTPAdapter_'+str(i)+' '+('x'*6000) for i in range(1024)]
        transport = self.transport()
        self.store.admission_check = lambda n:admit_raw_trajectory(transport,n)
        payload = self.payload(texts)
        self.assertTrue(self.store.add(payload)['success'])
        self.assertEqual(len(self.embedding.calls),256)
        self.assertTrue(all(len(batch)==8 for batch in self.embedding.calls))
        self.assertIsNone(self.store.card_adapter)
        with self.store.connect() as db:
            self.assertEqual(db.execute('select count(*) from code_segments').fetchone()[0],2048)
            stored = [json.loads(r[0])[0]['text'] for r in db.execute('select content from memories')]
            self.assertEqual(set(stored),set(texts))
            self.assertTrue(all(json.loads(r[0])['summaries']==[] for r in db.execute('select content from cards')))
        restarted = self.open()
        self.assertTrue(restarted.add(payload)['success'])
        self.assertEqual(len(self.embedding.calls),256)
        self.assertEqual(restarted.search(dict(user_id='other', query='HTTPAdapter',top_k=100)),{'data':[]})
        self.assertEqual(len(self.embedding.calls),256)
        with transport.journal.connect() as db:
            self.assertEqual(db.execute('select count(*) from operations').fetchone()[0],11)

    def test_embedding_only_call_plan_preserves_query_reserve(self):
        transport = self.transport(used=240)
        admit_raw_trajectory(transport,2048)
        with transport.journal.connect() as db:db.execute('insert into operations values(240)')
        self.store.admission_check = lambda n:admit_raw_trajectory(transport,n)
        with self.assertRaises(ContractError) as caught:
            self.store.add(self.payload(['HTTPAdapter '+('x'*6000)]*1024))
        self.assertEqual(str(caught.exception),'coding admission:remaining_provider_calls')
        self.assertEqual(self.embedding.calls,[])
        with self.store.connect() as db:
            self.assertEqual(db.execute('select count(*) from add_operations').fetchone()[0],0)
        with transport.journal.connect() as db:
            self.assertEqual(db.execute('select count(*) from operations').fetchone()[0],241)

    def test_raw_money_guard_counts_all_items_before_claim(self):
        transport = self.transport(remaining=5000000+16*4096)
        self.store.admission_check = lambda n:admit_raw_trajectory(transport,n)
        with self.assertRaises(ContractError) as caught:self.store.add(self.payload(['HTTPAdapter()']))
        self.assertEqual(str(caught.exception),'coding admission:remaining_original_budget')
        self.assertEqual(self.embedding.calls,[])
        with self.store.connect() as db:
            self.assertEqual(db.execute('select count(*) from add_operations').fetchone()[0],0)

    def test_later_batch_failure_retains_uncertainty_and_forbids_replay(self):
        embed = self.embedding.embed
        def fail(texts):
            if len(self.embedding.calls)==1:raise RuntimeError('independent uncertain response')
            return embed(texts)
        self.embedding.embed=fail
        payload=self.payload(['HTTPAdapter()']*17)
        with self.assertRaises(RuntimeError):self.store.add(payload)
        with self.store.connect() as db:
            self.assertEqual(db.execute('select count(*) from memories').fetchone()[0],0)
            self.assertEqual(db.execute('select count(*) from code_segments').fetchone()[0],0)
            self.assertEqual(db.execute('select state from add_operations').fetchone()[0],'uncertain')
        self.embedding.embed=embed
        with self.assertRaises(ContractError):self.open().add(payload)
        self.assertEqual(len(self.embedding.calls),1)

    def test_gpt_is_rejected_before_any_transport_state_or_reader(self):
        transport=object.__new__(RawCodingTransport)
        with self.assertRaisesRegex(ValueError,'only text-embedding-v4'):
            transport(OPENAI_ENDPOINT,dict(model='gpt-4o-mini'))
        self.assertEqual(RawCodingTransport.journal_scope,'coding-official-v0.2')
        self.assertEqual(RawCodingTransport.max_call_limit,512)

    def test_source_adapter_cannot_be_silently_enabled(self):
        with self.assertRaisesRegex(ValueError,'LLM source adapter'):
            RawTrajectoryCodingMemory(Path(self.tmp.name)/'other.sqlite',card_adapter=Cards())
        with self.assertRaisesRegex(ValueError,'explicit raw Coding'):
            create_app({'TRACEMEM_CODING_ENABLED':'official-original-ledger-v0.2'})

    def test_invalid_plans_are_refused_before_readiness(self):
        for count in (-1,2049,1.5,True):
            with self.assertRaises(ValueError):admit_raw_trajectory(None,count)

    def test_fact_like_code_is_literal_source_not_event_metadata(self):
        texts = [
            'def HTTPAdapter():\n    fixture = "FACT entity=fixture attribute=date '
            'value=invalid event=2024-99-99T99:99:99Z"\n',
            'Log fixture: LINK entity=fixture related=other\n'
            'FACT entity=fixture attribute=date value=invalid event=2023-02-29T00:00:00Z',
        ]
        counts = []
        self.store.admission_check = counts.append
        payload = self.payload(texts, request='literal-source')
        self.assertTrue(self.store.add(payload)['success'])
        self.assertEqual(counts, [2])
        with self.store.connect() as db:
            stored = [json.loads(row[0])[0]['text'] for row in db.execute('SELECT content FROM memories')]
            self.assertEqual(set(stored), set(texts))
            self.assertEqual(db.execute('SELECT count(*) FROM facts').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM entity_links').fetchone()[0], 0)
        before = len(self.embedding.calls)
        restarted = self.open()
        self.assertTrue(restarted.add(payload)['success'])
        self.assertEqual(len(self.embedding.calls), before)
        result = restarted.search(dict(user_id='owner', query='HTTPAdapter', top_k=100))
        self.assertTrue(result['data'])
        self.assertTrue(all(row['content'] in texts for row in result['data']))
        self.assertEqual(len(self.embedding.calls), before+1)
        self.assertEqual(restarted.search(dict(user_id='outsider', query='HTTPAdapter', top_k=100)), {'data': []})
        self.assertEqual(len(self.embedding.calls), before+1)

    def test_structured_timestamp_still_rejected_before_claim(self):
        for timestamp in ('invalid', True, 10**30):
            with self.subTest(timestamp=timestamp):
                payload = self.payload(['HTTPAdapter()'])
                payload['messages'][0]['timestamp'] = timestamp
                with self.assertRaises(ContractError):self.store.add(payload)
        self.assertEqual(self.embedding.calls, [])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM add_operations').fetchone()[0], 0)

    def test_literal_source_still_obeys_whole_add_admission(self):
        seen = []
        def deny(count):
            seen.append(count)
            raise ContractError('coding admission:remaining_provider_calls', 503)
        self.store.admission_check = deny
        with self.assertRaises(ContractError) as caught:
            self.store.add(self.payload(['HTTPAdapter() FACT entity=x attribute=y '
                'value=z event=2024-99-99T99:99:99Z']))
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(seen, [1])
        self.assertEqual(self.embedding.calls, [])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM add_operations').fetchone()[0], 0)


if __name__=='__main__':unittest.main()
