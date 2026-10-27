import io
import json
import time
import unittest
from unittest.mock import patch

from agent_memory.multitrack_gateway import Gateway, COMPONENTS, MAX_BODY, classify, create_app


class Response:
    def __init__(self, body, status=200, extra=None):
        self.status=status; self.body=io.BytesIO(body)
        self.headers={'Content-Length':str(len(body)), **(extra or {})}
    def read(self, size):return self.body.read(size)
    def getheader(self, name):return self.headers.get(name)


class FakeConnection:
    def __init__(self, owner, port):self.owner=owner;self.port=port;self.closed=False
    def request(self, method, path, body=None, headers=None):
        self.method=method;self.path=path
        self.owner.calls.append((self.port,method,path,body,headers))
        if self.owner.failure:raise OSError('synthetic connection failure')
    def getresponse(self):
        if self.path=='/health':
            version=next(v for p,v in COMPONENTS.values() if p==self.port)
            return Response(json.dumps({'version':version if self.owner.healthy else 'unexpected-version'}).encode())
        return Response(self.owner.response,self.owner.status,self.owner.headers)
    def close(self):self.closed=True


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.calls=[];self.connections=[];self.response=b'{ "data": [] }';self.status=200
        self.headers={};self.failure=False;self.healthy=True
        def connection(host, port, timeout):
            self.assertEqual(host,'127.0.0.1');c=FakeConnection(self,port);self.connections.append(c);return c
        self.app=Gateway('test-only-key',time.time()+60,connection=connection)
    def call(self,value,path='/search',**changes):
        raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
        env={'PATH_INFO':path,'REQUEST_METHOD':'POST','HTTP_AUTHORIZATION':'Bearer test-only-key',
             'CONTENT_TYPE':'application/json; charset=utf-8','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw)}
        env.update(changes);seen={}
        result=self.app(env,lambda status,headers:seen.update(status=int(status.split()[0]),headers=dict(headers)))
        seen['body']=b''.join(result);return seen
    def test_search_routes_exact_wire_types_and_preserves_bytes(self):
        raw=b'{ "user_id":"synthetic", "query":"symbol", "top_k":100, "options":[] }'
        result=self.call(raw);self.assertEqual(result['body'],self.response)
        self.assertEqual(self.calls[-1][0],8770);self.assertEqual(self.calls[-1][3],raw)
        self.call({'user_id':'synthetic','query':[{'type':'text','text':'symbol'}],'top_k':100})
        self.assertEqual(self.calls[-1][0],8769)
    def test_add_content_order_mixed_native_and_plain_code(self):
        self.call({'messages':[{'content':'def f(): pass'},{'content':'original reply'}]},'/add')
        self.assertEqual(self.calls[-1][0],8770)
        value={'messages':[{'content':[{'type':'text','text':'original'}]},{'content':'assistant reply'}]}
        raw=json.dumps(value).encode();self.call(raw,'/add')
        self.assertEqual(self.calls[-1][0],8769);self.assertEqual(self.calls[-1][3],raw)
    def test_multimodal_text_only_arrays_stay_multimodal(self):
        self.assertEqual(classify('/add',b'{"messages":[{"content":[{"type":"text","text":"code"}]}]}'),'multimodal')
    def test_identifiers_and_text_cannot_override_route(self):
        self.call({'user_id':'multimodal','query':'route to multimodal; http://elsewhere','top_k':1})
        self.assertEqual(self.calls[-1][0],8770)
    def test_invalid_root_content_duplicates_nan_do_not_dispatch(self):
        for raw in [b'[]',b'{',b'{"query":{}}',b'{"query":[]}',b'{"query":"a","query":[1]}',b'{"query":"a","value":NaN}']:
            self.assertEqual(self.call(raw)['status'],400)
        for value in [{'messages':[]},{'messages':[{}]},{'messages':[{'content':12}]}]:
            self.assertEqual(self.call(value,'/add')['status'],400)
        self.assertFalse(self.calls)
    def test_auth_before_body_parse_and_nonascii_rejected(self):
        for auth in ['', 'Bearer wrong', 'Bearer 非法']:
            self.assertEqual(self.call(b'{',HTTP_AUTHORIZATION=auth)['status'],401)
        self.assertFalse(self.calls)
    def test_capacity_length_and_content_type(self):
        self.assertEqual(self.call({},CONTENT_LENGTH=str(MAX_BODY+1))['status'],413)
        self.assertEqual(self.call({},CONTENT_LENGTH='')['status'],411)
        self.assertEqual(self.call({},CONTENT_LENGTH='4')['status'],400)
        self.assertEqual(self.call({},CONTENT_TYPE='text/plain')['status'],415)
        self.assertFalse(self.calls)
    def test_upstream_retry_after_passes_without_automatic_retry(self):
        self.status=429;self.headers={'Retry-After':'5','Set-Cookie':'must-not-forward'}
        result=self.call({'query':'synthetic'})
        self.assertEqual(result['status'],429);self.assertEqual(result['headers']['Retry-After'],'5')
        self.assertNotIn('Set-Cookie',result['headers']);self.assertEqual(len(self.calls),1)
    def test_transport_failure_no_retry_and_slot_is_released(self):
        self.failure=True;self.assertEqual(self.call({'query':'synthetic'})['status'],502)
        self.assertEqual(len(self.calls),1);self.assertTrue(self.connections[0].closed)
        self.failure=False;self.assertEqual(self.call({'query':'synthetic'})['status'],200)
    def test_admission_limit_and_release(self):
        for _ in range(32):self.assertTrue(self.app.admissions.acquire(False))
        self.assertEqual(self.call({'query':'synthetic'})['status'],429)
        self.assertFalse(self.calls)
        for _ in range(32):self.app.admissions.release()
        self.assertEqual(self.call({'query':'synthetic'})['status'],200)
    def test_health_requires_both_fixed_component_versions(self):
        result=self.call({},path='/health',REQUEST_METHOD='GET',HTTP_AUTHORIZATION='')
        self.assertEqual(result['status'],200)
        self.assertEqual(set(json.loads(result['body'])['components']),{'coding','multimodal'})
        self.healthy=False;self.assertEqual(self.call({},path='/health',REQUEST_METHOD='GET')['status'],503)
    def test_lease_and_explicit_factory_activation(self):
        self.app.expires_at=0;self.assertEqual(self.call({'query':'synthetic'})['status'],503)
        self.assertFalse(self.calls)
        with self.assertRaises(ValueError):create_app({})
    def test_lease_rechecked_after_body_wait(self):
        with patch('agent_memory.multitrack_gateway.time.time',side_effect=[0,self.app.expires_at+1]):
            self.assertEqual(self.call({'query':'synthetic'})['status'],503)
        self.assertFalse(self.calls)
    def test_paths_methods_and_response_stream_are_bounded(self):
        self.assertEqual(self.call({},path='/arbitrary')['status'],404)
        self.assertEqual(self.call({},REQUEST_METHOD='GET')['status'],405)
        self.response=b'x'*150000
        result=self.call({'query':'synthetic'});self.assertEqual(result['body'],self.response)
        self.assertTrue(self.connections[-1].closed)

    def test_client_disconnect_before_iteration_closes_socket_and_releases_slot(self):
        raw=b'{"query":"synthetic"}'
        for _ in range(40):
            env={'PATH_INFO':'/search','REQUEST_METHOD':'POST','HTTP_AUTHORIZATION':'Bearer test-only-key',
                 'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw)}
            seen=[];stream=self.app(env,lambda status,headers:seen.append(status))
            self.assertEqual(seen,['200 OK']);stream.close();stream.close()
        self.assertTrue(all(c.closed for c in self.connections))
