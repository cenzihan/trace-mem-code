import json
from agent_memory.coding_raw_app import RawCodingTransport, RawTrajectoryCodingMemory
from agent_memory.coding_recovery import digest,row_digest
from agent_memory.provider_http import ProviderFailure
import test_service_transport as transport_tests


class CodingRecoveryTests(transport_tests.ServiceTransportTests):
    def make(self):
        return RawCodingTransport(self.ledger.path,self.authority,self.prices,self.p/'receipts',{},
            http=self.http,offline_test=True,call_limit=512)

    def freeze_unknown(self):
        self.http.failure=True
        with self.assertRaises(ProviderFailure):self.call()
        self.http.failure=False
        t=self.make()
        with t.journal.connect() as db:row=dict(db.execute('select * from operations').fetchone())
        with self.ledger.connect() as db:reserve=db.execute('select reserved from attempts').fetchone()[0]
        value={'schema':1,'authorization':'Independent unit-test operator decision','input_sha256':digest('frozen control'),
            'retired_users':[digest('retired-user')],'retired_texts':[digest(self.payload['input'][0])],
            'unknowns':[{'fingerprint':row['fingerprint'],'row_sha256':row_digest(row),
                'attempt_id':row['attempt_id'],'reserved_micro_cny':reserve}]}
        t.coding_recovery.path.write_text(json.dumps(value))
        return row,reserve

    def test_fresh_input_allowed_old_payload_and_user_blocked_across_restart(self):
        row,reserve=self.freeze_unknown()
        before=self.ledger.totals()['attempts']
        with self.assertRaises(ValueError):self.call()
        t=self.make()
        with self.assertRaises(ValueError):t.coding_recovery.assert_user('retired-user')
        store=RawTrajectoryCodingMemory(self.p/'memory.sqlite');store.source_guard=t.coding_recovery.assert_user
        with self.assertRaises(ValueError):store.add(dict(user_id='retired-user'))
        with self.assertRaises(ValueError):store.search(dict(user_id='retired-user',query='fresh',top_k=100))
        self.assertEqual(self.ledger.totals()['attempts'],before)
        self.payload['input']=['A different independent function: fresh_guard_check().']
        self.call()
        t=self.make();t.ready()
        self.assertEqual(dict(t.journal.row(row['fingerprint'])),row)
        with self.ledger.connect() as db:
            self.assertEqual(db.execute('select accounted,reserved,status from attempts where id=?',(row['attempt_id'],)).fetchone(),(reserve,reserve,'uncertain'))
        self.assertEqual(self.http.calls,2)
        self.assertEqual(t.call_limit,512)

    def test_rebatching_a_retired_span_is_blocked_before_journal_claim(self):
        self.freeze_unknown();self.payload['input']=['new context',*self.payload['input']]
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.http.calls,1)
        self.assertEqual(self.ledger.totals()['attempts'],1)

    def test_new_unknown_is_not_implicitly_accepted(self):
        self.freeze_unknown();self.payload['input']=['unrelated new source']
        self.http.failure=True
        with self.assertRaises(ProviderFailure):self.call()
        self.http.failure=False;self.payload['input']=['third new source']
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.http.calls,2)

    def test_modified_hold_or_receipt_invalidates_recovery(self):
        row,reserve=self.freeze_unknown();t=self.make();t.ready()
        with self.ledger.connect() as db:db.execute('update attempts set accounted=accounted-1 where id=?',(row['attempt_id'],))
        with self.assertRaises(ValueError):t.ready()
        with self.ledger.connect() as db:db.execute('update attempts set accounted=? where id=?',(reserve,row['attempt_id']))
        with t.journal.connect() as db:db.execute("update operations set state='complete' where fingerprint=?",(row['fingerprint'],))
        with self.assertRaises(ValueError):t.ready()
