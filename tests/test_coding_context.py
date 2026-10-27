"""Synthetic source-integrity checks; no benchmark questions or live models."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from agent_memory.coding import CodingMemorySystem
from agent_memory.coding_context import SourceSpan,source_window
from agent_memory.protocol import ContractError


class ProjectionTests(unittest.TestCase):
    def fixture(self,parts=('cause\n','attempt\n','validation pending\n')):
        source=''.join(parts);spans=[];offset=0
        for part in parts:
            end=offset+len(part)
            spans.append(SourceSpan(f'p:{offset}:{end}','p','u',offset,end,hashlib.sha256(part.encode()).hexdigest()))
            offset=end
        return source,spans

    def project(self,source,spans,**kw):
        return source_window(source,spans,spans[1].id,user_id='u',parent_id='p',**kw)

    def test_original_order_and_source_references(self):
        source,spans=self.fixture();result=self.project(source,list(reversed(spans)))
        self.assertEqual(result.content,source)
        self.assertEqual(result.source_ids,tuple(s.id for s in spans))
        self.assertEqual(result.matched_id,spans[1].id)
        self.assertEqual(result.sha256,hashlib.sha256(source.encode()).hexdigest())

    def test_unicode_budget_preserves_whole_match(self):
        source,spans=self.fixture(('症状\n','尝试🙂\n','测试未完成\n'))
        match_bytes=len('尝试🙂\n'.encode())
        result=self.project(source,spans,max_bytes=match_bytes)
        self.assertEqual(result.content,'尝试🙂\n')
        self.assertIsNone(self.project(source,spans,max_bytes=match_bytes-1))

    def test_no_unindexed_gap_can_enter_projection(self):
        source,spans=self.fixture(('before\n',' \n','match\n'))
        result=source_window(source,[spans[0],spans[2]],spans[2].id,user_id='u',parent_id='p')
        self.assertEqual(result.content,'match\n')

    def test_scope_mismatch_rejected(self):
        source,spans=self.fixture()
        for change in [{'user_id':'other'},{'parent_id':'another'}]:
            bad=[replace(spans[0],**change),*spans[1:]]
            with self.assertRaisesRegex(ValueError,'scope mismatch'):self.project(source,bad)

    def test_unselected_source_corruption_rejected(self):
        source,spans=self.fixture()
        with self.assertRaisesRegex(ValueError,'digest mismatch'):
            self.project(source+'!',spans[:-1]+[replace(spans[-1],sha256='0'*64)],max_bytes=8)

    def test_missing_overlap_and_wrong_id_rejected(self):
        source,spans=self.fixture()
        for bad in [spans+[spans[0]],[replace(spans[0],start=-1),*spans[1:]],
                    [replace(spans[0],id='unrelated'),*spans[1:]]]:
            with self.assertRaises(ValueError):self.project(source,bad)
        with self.assertRaisesRegex(ValueError,'absent'):
            source_window(source,spans,'missing',user_id='u',parent_id='p')

    def test_only_immediate_neighbors_are_added(self):
        source,spans=self.fixture(('one\n','two\n','three\n','four\n','five\n'))
        result=source_window(source,spans,spans[2].id,user_id='u',parent_id='p')
        self.assertEqual(result.content,'two\nthree\nfour\n')


class ContextIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'code.sqlite'
        self.store=CodingMemorySystem(self.path,context_policy='source-window')
        self.source='prior context\n'*300+'TraceFn() unresolved\n'+'verification pending\n'*300
        self.payload={'request_id':'r','session_id':'s','user_id':'u','messages':[{'role':'user','content':self.source}]}
        self.store.add(self.payload)
        self.query={'query':'TraceFn()','user_id':'u','top_k':100}

    def test_window_contains_match_and_only_original_content(self):
        result,diagnostic=self.store.retrieve(self.query)
        self.assertEqual(len(result['data']),1)
        item=result['data'][0]
        self.assertIn('TraceFn()',item['content']);self.assertIn(item['content'],self.source)
        self.assertGreater(len(diagnostic['projections'][0]['source_ids']),1)
        self.assertEqual(diagnostic['projections'][0]['sha256'],hashlib.sha256(item['content'].encode()).hexdigest())

    def test_isolation_and_stable_restart(self):
        expected=self.store.search(self.query)
        reopened=CodingMemorySystem(self.path,context_policy='source-window')
        self.assertEqual(reopened.search(self.query),expected)
        self.assertEqual(reopened.search(dict(self.query,user_id='other')),{'data':[]})

    def test_default_remains_v01_without_context_fill(self):
        baseline=CodingMemorySystem(self.path)
        plain=baseline.search(self.query)['data'][0]['content']
        projected=self.store.search(self.query)['data'][0]['content']
        self.assertIn(plain,projected);self.assertGreater(len(projected),len(plain))
        self.assertEqual(baseline.capabilities()['version'],'tracemem-code-v0.1.0')
        self.assertEqual(self.store.capabilities()['version'],'tracemem-code-v0.2-context-dev')

    def test_whole_record_budget_and_top_k(self):
        second=dict(self.payload,request_id='r2',messages=[{'role':'user','content':'TraceFn() another history'}])
        self.store.add(second)
        result=self.store.search(dict(self.query,top_k=1))
        self.assertEqual(len(result['data']),1)
        limited=CodingMemorySystem(self.path,context_policy='source-window',return_bytes=4096)
        output=limited.search(self.query)
        self.assertLessEqual(sum(len(i['content'].encode()) for i in output['data']),4096)

    def test_source_tamper_is_detected(self):
        with self.store.connect() as db:
            db.execute('UPDATE memories SET content=?',(json.dumps([{'type':'text','text':'X'+self.source[1:]}]),))
        with self.assertRaisesRegex(ContractError,'digest mismatch'):self.store.search(self.query)

    def test_invalid_policy_is_rejected_before_state_creation(self):
        path=Path(self.tmp.name)/'new.sqlite'
        with self.assertRaises(ValueError):CodingMemorySystem(path,context_policy='guess')
        self.assertFalse(path.exists())

    def test_projection_needs_no_additional_provider_calls(self):
        from test_coding import Embedding,Cards
        embedding=Embedding();cards=Cards()
        store=CodingMemorySystem(Path(self.tmp.name)/'adapters.sqlite',embedding=embedding,
                                 card_adapter=cards,context_policy='source-window')
        store.add(self.payload)
        before=(len(embedding.calls),cards.calls)
        result=store.search(self.query)
        self.assertTrue(result['data'])
        self.assertEqual((len(embedding.calls),cards.calls),(before[0]+1,before[1]))
        self.assertTrue(all('DERIVED_INDEX_ONLY' not in i['content'] for i in result['data']))
