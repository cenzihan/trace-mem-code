"""Offline acceptance of the new public profile, never a scored Coding run."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from agent_memory.coding_app import CodingServiceTransport
from agent_memory.coding_cards import CodingCards
from agent_memory.coding_official_app import OfficialCodingMemory, OfficialCodingTransport, create_app
from agent_memory.protocol import ContractError
from agent_memory.service_transport import ServiceBudgetedTransport
from test_coding import Cards, Embedding
import test_service_transport as transport_tests


class OfficialCodingTests(unittest.TestCase):
    def test_twenty_message_add_replay_restart_and_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'memory.sqlite';cards=Cards();embedding=Embedding()
            store=OfficialCodingMemory(path,card_adapter=cards,embedding=embedding,context_policy='source-window')
            payload=dict(request_id='r',user_id='u',session_id='s',messages=[
                dict(role='user',content=f'def HTTPAdapter_{i}():\n    return {i}\n') for i in range(20)])
            result=store.add(payload);self.assertEqual(result['request_id'],'r');self.assertTrue(result['success'])
            calls=cards.calls;store.add(payload);self.assertEqual(cards.calls,calls)
            query=dict(query='HTTPAdapter_19',user_id='u',top_k=100,options=[])
            before=store.search(query)
            restarted=OfficialCodingMemory(path,card_adapter=cards,embedding=embedding,context_policy='source-window')
            self.assertEqual(restarted.search(query),before)
            self.assertTrue(before['data']);self.assertLessEqual(len(before['data']),20)
            self.assertTrue(all(row['content'] in [m['content'] for m in payload['messages']] for row in before['data']))
            self.assertEqual(restarted.search(dict(query,user_id='outsider'))['data'],[])
            too_many=copy.deepcopy(payload);too_many['request_id']='r2';too_many['messages'].append(payload['messages'][0])
            with self.assertRaises(ContractError):store.add(too_many)
            self.assertEqual(cards.calls,calls)

    def test_strict_request_preserves_source_and_quotes(self):
        seen=[]
        def transport(endpoint,payload):
            seen.append(payload)
            validator=object.__new__(ServiceBudgetedTransport);validator.model='gpt-4o-mini';validator.output_token_cap=512
            validator._bounds(payload)
            return dict(model='gpt-4o-mini',choices=[dict(message=dict(content=json.dumps(
                dict(summary='Original source index',evidence_quotes=['return 19','invented']))))])
        source='def HTTPAdapter():\n    return 19\n'
        result=CodingCards(transport,structured_output=True).extract(source)
        self.assertEqual(result['evidence_quotes'],['return 19'])
        self.assertEqual(seen[0]['response_format']['type'],'json_schema')
        self.assertEqual(seen[0]['messages'][1]['content'][0]['text'],source)

    def test_development_state_cannot_be_reopened_as_official(self):
        with self.assertRaises(ValueError):create_app({'TRACEMEM_CODING_ENABLED':'isolated-original-ledger'})
        with self.assertRaises(ValueError):create_app({'TRACEMEM_CODING_ENABLED':'official-original-ledger-v0.2',
            'TRACEMEM_CODING_STATE':'/app/runtime/coding-v1'})


class OfficialGuardTests(transport_tests.ServiceTransportTests):
    def make(self):
        return OfficialCodingTransport(self.ledger.path,self.authority,self.prices,self.p/'receipts',{},
            http=self.http,offline_test=True,call_limit=2)

    def test_limit_survives_restart_and_does_not_reset(self):
        self.call();self.call()
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.http.calls,2)
        with self.assertRaises(ValueError):OfficialCodingTransport(self.ledger.path,self.authority,self.prices,
            self.p/'receipts',{},http=self.http,offline_test=True,call_limit=3)
        with self.make().journal.connect() as db:
            self.assertEqual(db.execute('SELECT DISTINCT scope FROM operations').fetchall()[0][0],'coding-official-v0.2')
        with self.assertRaises(ValueError):CodingServiceTransport(self.ledger.path,self.authority,self.prices,
            self.p/'development',{},http=self.http,offline_test=True,call_limit=512)

