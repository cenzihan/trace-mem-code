"""Synthetic contract regressions, not benchmark scores or provider inference."""
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from agent_memory.app import Application
from agent_memory.coding import CodingMemorySystem, anchors, code_tokens, segments
from agent_memory.coding_app import CodingServiceTransport, create_app
from agent_memory.coding_cards import CodingCards
from agent_memory.protocol import ContractError, canonical
from agent_memory.provider_http import BAILIAN_BEIJING_ENDPOINT


class Embedding:
    model = 'text-embedding-v4'
    dimensions = 256
    transport = SimpleNamespace(mode='offline_fake')

    def __init__(self): self.calls=[]

    def embed(self,texts):
        self.calls.append(list(texts))
        return [[1.,0.]+[0.]*254 if 'HTTPAdapter' in text else [0.,1.]+[0.]*254 for text in texts]


class Cards:
    model = 'gpt-4o-mini'
    transport = SimpleNamespace(mode='offline_fake')

    def __init__(self): self.calls=0; self.fail=False

    def extract(self,parts):
        self.calls+=1
        if self.fail: raise RuntimeError('simulated uncertain outcome')
        return {'summary':'DERIVED_INDEX_ONLY', 'evidence_quotes':[parts[0]['text']]}


class CodingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'code.sqlite'
        self.embedding=Embedding(); self.cards=Cards()
        self.store=self.open()

    def open(self):
        return CodingMemorySystem(self.path,embedding=self.embedding,card_adapter=self.cards)

    def payload(self,texts,uid='owner',rid='request'):
        return dict(user_id=uid,session_id='history',request_id=rid,
                    messages=[dict(role='user',content=text) for text in texts])

    def query(self,query='HTTPAdapter',uid='owner',top_k=100):
        return dict(query=query,user_id=uid,top_k=top_k)

    def test_unicode_segmentation_is_lossless_and_byte_bounded(self):
        source=('def HTTPAdapter():\n    return "你好🙂"\n'+'x'*111)*4
        chunks=list(segments(source,37))
        self.assertEqual(''.join(text for _,_,text in chunks),source)
        self.assertTrue(all(len(text.encode())<=37 for _,_,text in chunks))
        self.assertTrue(all(source[start:end]==text for start,end,text in chunks))
        self.assertEqual(chunks[0][0],0); self.assertEqual(chunks[-1][1],len(source))

    def test_code_identifiers_and_exact_path_anchors(self):
        self.assertTrue({'httprequesthandler','http','request','handler'}<=set(code_tokens('HTTPRequestHandler')))
        self.assertIn('cache',code_tokens('cache_entry'))
        self.assertIn('src/net/client.py',anchors('Failure in src/net/client.py: HTTPAdapter()'))
        self.assertIn('httpadapter',anchors('HTTPAdapter()'))
        self.assertIn('timeouterror',anchors('raise TimeoutError'))

    def test_strings_exact_spans_and_metadata_not_returned(self):
        text='src/net/client.py\ndef HTTPAdapter():\n    return 17\nValidation: test_retries passed.\n'
        self.store.add(self.payload([text]))
        result=self.store.search(self.query())
        self.assertEqual(result['data'][0]['content'],text)
        self.assertNotIn('DERIVED_INDEX_ONLY',canonical(result))
        self.assertTrue(all(isinstance(row['content'],str) for row in result['data']))
        self.assertIn('offline_fake',self.store.capabilities()['mode'])

    def test_noisy_lexical_sources_do_not_displace_exact_identifier(self):
        local=CodingMemorySystem(Path(self.tmp.name)/'local.sqlite')
        relevant='src/net/client.py\ndef HTTPAdapter():\n    return retry_pool\n'
        noise='generic network error error network request docs '+('retry discussion '*80)
        local.add(self.payload([noise,relevant]))
        self.assertEqual(local.search(self.query('HTTPAdapter() in src/net/client.py'))['data'][0]['content'],relevant)
        self.assertEqual(local.search(self.query('unrelateduniquequux'))['data'],[])

    def test_add_idempotence_conflict_and_restart(self):
        p=self.payload(['HTTPAdapter() retry_pool validation'])
        self.store.add(p); counts=(self.cards.calls,len(self.embedding.calls))
        first=self.store.search(self.query()); after=(self.cards.calls,len(self.embedding.calls))
        self.store=self.open(); self.store.add(p)
        self.assertEqual((self.cards.calls,len(self.embedding.calls)),after)
        self.assertEqual(self.store.search(self.query()),first)
        with self.assertRaises(ContractError) as caught:self.store.add(self.payload(['different']))
        self.assertEqual(caught.exception.status,409); self.assertEqual(self.cards.calls,counts[0])

    def test_cross_user_and_empty_scope_have_no_model_calls(self):
        self.store.add(self.payload(['HTTPAdapter()']))
        before=(self.cards.calls,len(self.embedding.calls))
        self.assertEqual(self.store.search(self.query(uid='other')),{'data':[]})
        self.assertEqual(before,(self.cards.calls,len(self.embedding.calls)))

    def test_capacity_and_images_reject_before_paid_work(self):
        for texts in [['x'*140000],['x'*17000]*16]:
            with self.assertRaises(ContractError):self.store.add(self.payload(texts))
        p=self.payload(['text']); p['messages'][0]['content']=[{'type':'text','text':'text'}]
        with self.assertRaises(ContractError):self.store.add(p)
        with self.assertRaises(ContractError):self.store.search(dict(user_id='owner',query=[{'type':'text','text':'text'}],top_k=1))
        self.assertEqual((self.cards.calls,len(self.embedding.calls)),(0,0))

    def test_whitespace_fragments_do_not_reach_embedding(self):
        self.store.add(self.payload(['\n'*5000+'HTTPAdapter()']))
        self.assertTrue(all(text.strip() for batch in self.embedding.calls for text in batch))
        self.assertTrue(self.store.search(self.query())['data'])

    def test_failed_add_is_not_acknowledged_or_replayed(self):
        self.cards.fail=True
        with self.assertRaises(RuntimeError):self.store.add(self.payload(['HTTPAdapter()']))
        self.cards.fail=False; self.store=self.open()
        with self.assertRaises(ContractError):self.store.add(self.payload(['HTTPAdapter()']))
        self.assertEqual(self.cards.calls,1)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM memories').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT state FROM add_operations').fetchone()[0],'uncertain')

    def test_missing_partial_index_fails_before_query_embedding(self):
        self.store.add(self.payload(['HTTPAdapter()\n'*600]))
        with self.store.connect() as db:
            sid=db.execute('SELECT id FROM code_segments LIMIT 1').fetchone()[0]
            db.execute('DELETE FROM code_segments WHERE id=?',(sid,))
        before=len(self.embedding.calls)
        with self.assertRaises(ContractError):self.store.search(self.query())
        self.assertEqual(len(self.embedding.calls),before)

    def test_corrupt_vector_fails_before_query_embedding(self):
        self.store.add(self.payload(['HTTPAdapter()']))
        with self.store.connect() as db:db.execute("UPDATE code_segments SET vector='[1,2]'")
        before=len(self.embedding.calls)
        with self.assertRaises(ContractError):self.store.search(self.query())
        self.assertEqual(len(self.embedding.calls),before)

    def test_source_digest_is_checked(self):
        self.store.add(self.payload(['HTTPAdapter()']))
        with self.store.connect() as db:
            db.execute('UPDATE memories SET content=?',(canonical([{'type':'text','text':'modified'}]),))
        with self.assertRaises(ContractError):self.store.search(self.query())

    def test_return_budget_and_per_episode_cap(self):
        text=('HTTPAdapter() historical retry validation\n'*800)
        self.store.add(self.payload([text]))
        result=self.store.search(self.query())
        self.assertLessEqual(len(result['data']),3)
        self.assertLessEqual(sum(len(x['content'].encode()) for x in result['data']),32768)
        self.assertTrue(all(x['content'] in text for x in result['data']))
        self.assertTrue(all(len(batch)<=8 for batch in self.embedding.calls[:-1]))

    def test_options_not_persisted_or_used_for_ranking(self):
        self.store.add(self.payload(['HTTPAdapter()']))
        first=self.store.search(self.query())
        p=self.query(); p['options']=['PRIVATE_QUERY_OPTION']
        self.assertEqual(self.store.search(p),first)
        with self.store.connect() as db:
            self.assertNotIn('PRIVATE_QUERY_OPTION','\n'.join(db.iterdump()))

    def test_optional_reranker_identity_is_enforced(self):
        with self.assertRaises(ValueError):
            CodingMemorySystem(Path(self.tmp.name)/'wrong.sqlite',scoring_adapter=SimpleNamespace(model='qwen3-vl-rerank'))

    def test_http_auth_and_coding_response_contract(self):
        app=Application(self.store,auth_mode='Bearer',key='test-only-service-secret')
        def call(path,payload,auth='Bearer test-only-service-secret'):
            raw=canonical(payload).encode(); result=[]
            env={'PATH_INFO':path,'REQUEST_METHOD':'POST','CONTENT_TYPE':'application/json',
                 'CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),'HTTP_AUTHORIZATION':auth}
            body=b''.join(app(env,lambda status,headers:result.append(status)))
            return int(result[0].split()[0]),json.loads(body)
        p=self.payload(['HTTPAdapter()'])
        self.assertEqual(call('/add',p,auth='wrong')[0],401)
        self.assertEqual(self.cards.calls,0)
        self.assertTrue(call('/add',p)[1]['success'])
        code,body=call('/search',self.query()); self.assertEqual(code,200)
        self.assertIsInstance(body['data'][0]['content'],str)

    def test_live_factory_is_closed_by_default(self):
        with self.assertRaises(ValueError):create_app({})

    def test_concurrent_deterministic_add_is_idempotent(self):
        from concurrent.futures import ThreadPoolExecutor
        a=CodingMemorySystem(Path(self.tmp.name)/'concurrent.sqlite')
        b=CodingMemorySystem(a.path)
        p=self.payload(['HTTPAdapter()'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda store:store.add(p),[a,b]))
        self.assertEqual(results[0],results[1])
        with a.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM code_segments').fetchone()[0],1)


class CodingCardTests(unittest.TestCase):
    def test_source_only_prompt_and_verifiable_quotes(self):
        sent=[]
        def transport(endpoint,payload):
            sent.append(payload)
            return {'model':'gpt-4o-mini-2024-07-18','choices':[{'message':{'content':json.dumps({
                'summary':'Old failure in RetryPool','evidence_quotes':['RetryPool','invented quote']})}}]}
        result=CodingCards(transport).extract([{'type':'text','text':'RetryPool failed validation.'}])
        self.assertEqual(result['evidence_quotes'],['RetryPool'])
        self.assertEqual(result['omitted_unverified_quote_count'],1)
        self.assertFalse(sent[0]['store']); self.assertEqual(sent[0]['model'],'gpt-4o-mini')


class CodingCallLimitTests(unittest.TestCase):
    def setUp(self):
        # Reuse only the synthetic temporary-ledger setup, never the live ledger.
        from test_service_transport import ServiceTransportTests
        ServiceTransportTests.setUp(self)

    def make(self):
        return CodingServiceTransport(self.ledger.path,self.authority,self.prices,self.p/'receipts',{},
                                      http=self.http,offline_test=True,call_limit=2)

    def test_lifetime_cap_survives_recreation(self):
        transport=self.make()
        transport(BAILIAN_BEIJING_ENDPOINT,self.payload)
        recreated=self.make()
        recreated.ready()
        recreated(BAILIAN_BEIJING_ENDPOINT,self.payload)
        recreated=self.make()
        with self.assertRaisesRegex(ValueError,'call cap reached'):
            recreated(BAILIAN_BEIJING_ENDPOINT,self.payload)
        self.assertEqual(self.http.calls,2)
        self.assertEqual(self.ledger.totals()['attempts'],2)

    def test_existing_call_cap_cannot_be_increased(self):
        self.make()
        with self.assertRaisesRegex(ValueError,'cap is immutable'):
            CodingServiceTransport(self.ledger.path,self.authority,self.prices,self.p/'receipts',{},
                                   http=self.http,offline_test=True,call_limit=3)

    def test_missing_cap_cannot_recreate_after_activity(self):
        transport=self.make();transport(BAILIAN_BEIJING_ENDPOINT,self.payload)
        transport.limit_path.unlink()
        with self.assertRaisesRegex(ValueError,'never recreate'):
            self.make()
        self.assertEqual(self.http.calls,1)

    def test_changed_cap_blocks_existing_process(self):
        transport=self.make()
        transport.limit_path.write_text(json.dumps({'schema':1,'max_calls':3}))
        with self.assertRaisesRegex(ValueError,'cap is immutable'):
            transport(BAILIAN_BEIJING_ENDPOINT,self.payload)
        self.assertEqual(self.http.calls,0)


if __name__=='__main__': unittest.main()
