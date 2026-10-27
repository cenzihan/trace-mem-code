"""Synthetic large-Add regressions; no official inputs or model traffic."""
from pathlib import Path
from contextlib import contextmanager
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

from agent_memory.coding_trajectory_app import TrajectoryCodingMemory, admit_trajectory
from agent_memory.protocol import ContractError, canonical
from test_coding import Cards, Embedding


class TrajectoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'memory.sqlite'
        self.cards, self.embedding = Cards(), Embedding()
        self.store = self.open()

    def open(self):
        return TrajectoryCodingMemory(self.path, card_adapter=self.cards,
                                      embedding=self.embedding, context_policy='source-window')

    def payload(self, texts):
        return dict(user_id='owner', request_id='write', session_id='history',
                    messages=[dict(role='user' if i % 2 == 0 else 'assistant',
                                   timestamp=1700000000000+i, content=text)
                              for i, text in enumerate(texts)])

    def test_long_trajectory_atomic_roundtrip_restart_and_isolation(self):
        texts = [f'def HTTPAdapter_{i}():\n'+('    # independent source context\n'*60)
                 for i in range(129)]
        texts += [('HTTPAdapter() Unicode: 中🙂\n' * 12000)]
        payload = self.payload(texts)
        self.assertGreater(len(canonical(payload).encode()), 500000)
        self.assertTrue(self.store.add(payload)['success'])
        calls = (self.cards.calls, len(self.embedding.calls))
        self.assertGreater(self.cards.calls, 64)
        self.assertTrue(all(1 <= len(batch) <= 8 for batch in self.embedding.calls))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM memories').fetchone()[0], len(texts))
            self.assertEqual(db.execute('SELECT state FROM add_operations').fetchone()[0], 'complete')
        restarted = self.open()
        self.assertTrue(restarted.add(payload)['success'])
        self.assertEqual(calls, (self.cards.calls, len(self.embedding.calls)))
        query = dict(user_id='owner', query='HTTPAdapter_128', top_k=100)
        rows = restarted.search(query)['data']
        self.assertTrue(rows)
        self.assertTrue(all(any(row['content'] in text for text in texts) for row in rows))
        self.assertEqual(restarted.search(dict(query, user_id='outsider')), {'data': []})

    def test_whole_add_preflight_denial_does_not_claim_or_call(self):
        seen = []
        def deny(count):
            seen.append(count)
            raise ContractError('coding admission:remaining_provider_calls', 503)
        self.store.admission_check = deny
        with self.assertRaises(ContractError):
            self.store.add(self.payload(['HTTPAdapter()']*129))
        self.assertEqual(seen, [129])
        self.assertEqual((self.cards.calls, len(self.embedding.calls)), (0, 0))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM add_operations').fetchone()[0], 0)

    def test_later_embedding_batch_failure_is_atomic_and_never_replayed(self):
        original = self.embedding.embed
        def fail_second(texts):
            if len(self.embedding.calls) == 1:
                raise RuntimeError('simulated uncertain later batch')
            return original(texts)
        self.embedding.embed = fail_second
        payload = self.payload(['HTTPAdapter()']*21)
        with self.assertRaises(RuntimeError): self.store.add(payload)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM memories').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM code_segments').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT state FROM add_operations').fetchone()[0], 'uncertain')
        calls = self.cards.calls
        self.embedding.embed = original
        with self.assertRaises(ContractError): self.open().add(payload)
        self.assertEqual(self.cards.calls, calls)

    def test_each_capacity_guard_rejects_before_model_dispatch(self):
        cases = [(['x']*1025, 'messages'),
                 (['x'*(2*1024*1024+1)], 'message_source_bytes'),
                 (['x'*(2*1024*1024)]*5, 'add_source_bytes'),
                 (['x'*5000]*1023+['x'*9000], 'source_segments')]
        for texts, reason in cases:
            with self.assertRaises(ContractError) as caught: self.store.add(self.payload(texts))
            self.assertEqual(caught.exception.status, 413)
            self.assertIn(reason, str(caught.exception))
        self.assertEqual((self.cards.calls, len(self.embedding.calls)), (0, 0))

    def test_lifetime_and_original_money_are_checked_without_reset(self):
        path = Path(self.tmp.name)/'receipts.sqlite'
        @contextmanager
        def connect():
            db = sqlite3.connect(path)
            try:
                with db: yield db
            finally: db.close()
        with connect() as db:
            db.execute('CREATE TABLE operations(id INTEGER)')
            db.executemany('INSERT INTO operations VALUES(?)', [(i,) for i in range(11)])
        remaining = [200000000]
        transport = SimpleNamespace(ready=lambda: None, call_limit=512,
            journal=SimpleNamespace(connect=connect),
            ledger=SimpleNamespace(totals=lambda: {'remaining_micro_cny': remaining[0]}))
        admit_trajectory(transport, 445)
        with self.assertRaises(ContractError) as caught: admit_trajectory(transport, 446)
        self.assertIn('remaining_provider_calls', str(caught.exception))
        remaining[0] = 5000000
        with self.assertRaises(ContractError) as caught: admit_trajectory(transport, 1)
        self.assertIn('remaining_original_budget', str(caught.exception))
        with connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM operations').fetchone()[0], 11)


if __name__ == '__main__': unittest.main()
