"""Coding-memory candidate: immutable source spans, code anchors and rank fusion.

No task solutions, commands or repository files are executed. Generated summaries
are index metadata; every returned character comes from an admitted source.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import re

from .protocol import ContractError, canonical, validate_add, validate_search
from .retrieval import cosine, ranked, rrf
from .system import AgentMemorySystem, RetrievalConfig
from .coding_context import SourceSpan, source_window


VERSION = 'tracemem-code-v0.1.0'
SEGMENT_BYTES = 4096
ADD_SEGMENTS = 64
RETURN_BYTES = 32768
TOKEN = re.compile(r'[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[\u3400-\u9fff]')
PATH = re.compile(r'(?<![\w])(?:[A-Za-z0-9_.@-]+/)+[A-Za-z0-9_.@-]+|\b[A-Za-z_][\w.-]*\.(?:py|js|ts|tsx|jsx|java|go|rs|c|h|cpp|hpp|rb|sql|toml|yaml|yml|json)\b')
SYMBOL = re.compile(r'\b(?:[A-Za-z_]\w*::)+[A-Za-z_]\w*\b|\b[A-Za-z_]\w*(?:Error|Exception)\b|\b(?:def|class|function|func|fn)\s+([A-Za-z_]\w*)|`([A-Za-z_][\w.:/-]*)`|\b([A-Za-z_]\w*)\s*\(')


def code_tokens(text):
    result = []
    for match in TOKEN.finditer(text):
        word = match.group()
        result.append(word.casefold())
        pieces = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', word)
        pieces = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', pieces).replace('_', ' ').split()
        if len(pieces) > 1:
            result.extend(part.casefold() for part in pieces if part)
    return result


def anchors(text):
    values = [m.group() for m in PATH.finditer(text)]
    for m in SYMBOL.finditer(text):
        values.append(next((g for g in m.groups() if g), m.group()))
    return sorted(set(value.casefold() for value in values))


def segments(text, limit=SEGMENT_BYTES):
    """Non-overlapping Unicode offsets; prefer complete lines, never drop bytes."""
    if type(limit) is not int or limit < 4:
        raise ValueError('segment byte limit must be at least4')
    start = 0
    while start < len(text):
        end, used, newline = start, 0, None
        while end < len(text) and used + len(text[end].encode('utf-8')) <= limit:
            used += len(text[end].encode('utf-8'))
            end += 1
            if text[end-1] == '\n':
                newline = end
        if end < len(text) and newline is not None and newline > start:
            end = newline
        yield start, end, text[start:end]
        start = end


def sparse_scores(query_tokens, documents):
    """BM25 with code-aware tokenization; zero-overlap rows never enter fusion."""
    if not documents or not query_tokens:
        return {}
    counts = {key: Counter(value) for key, value in documents.items()}
    lengths = {key: sum(value.values()) for key, value in counts.items()}
    average = sum(lengths.values()) / len(counts) or 1
    df = Counter(term for value in counts.values() for term in value)
    scores = {}
    for key, value in counts.items():
        score = 0.0
        for term in set(query_tokens):
            frequency = value.get(term, 0)
            if frequency:
                idf = math.log(1 + (len(counts)-df[term]+.5)/(df[term]+.5))
                score += idf * frequency * 2.2 / (frequency + 1.2*(.25+.75*lengths[key]/average))
        if score > 0:
            scores[key] = score
    return scores


class CodingMemorySystem(AgentMemorySystem):
    message_source_bytes = 128 * 1024
    add_source_bytes = 8 * 1024 * 1024
    add_segments = ADD_SEGMENTS
    def __init__(self, path, *, embedding=None, card_adapter=None, scoring_adapter=None,
                 return_bytes=RETURN_BYTES, anchor_channel=True,
                 context_policy='matched-spans', context_window_bytes=12288):
        if context_policy not in ('matched-spans','source-window'):
            raise ValueError('unknown coding context policy')
        if type(context_window_bytes) is not int or not SEGMENT_BYTES <= context_window_bytes <= RETURN_BYTES:
            raise ValueError('coding context window must be4096..32768 UTF-8 bytes')
        if embedding is not None and (getattr(embedding, 'model', None) != 'text-embedding-v4'
                                      or getattr(embedding, 'dimensions', None) != 256):
            raise ValueError('fixed text-embedding-v4 256-dimensional adapter required')
        if scoring_adapter is not None and any(getattr(scoring_adapter, key, None) != value for key, value in {
                'model': 'Qwen/Qwen3-VL-Reranker-2B',
                'revision': '4bd860ac4f15ad1897a214615cccc700f8f71818',
                'weights_sha256': '466ec01961061e9d7f804b4fb1625fb6f406106cd1567e026096d4736fa9d5b9'}.items()):
            raise ValueError('optional reranker must have the original exact identity')
        if type(return_bytes) is not int or not SEGMENT_BYTES <= return_bytes <= 1024*1024:
            raise ValueError('response budget must be4096..1048576 UTF-8 bytes')
        super().__init__(path, RetrievalConfig(cards=True, temporal=False, links=False,
                         image_identity=False, dense=embedding is not None),
                         embedding=embedding, card_adapter=card_adapter)
        self.scoring_adapter = scoring_adapter
        self.context_policy,self.context_window_bytes=context_policy,context_window_bytes
        self.return_bytes, self.anchor_channel = return_bytes, anchor_channel
        with self.connect() as db:
            if db.execute('SELECT count(*) FROM memories').fetchone()[0] and not db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='code_segments'").fetchone():
                raise ValueError('coding needs its own empty database; no multimodal migration')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS code_segments (
                    id TEXT PRIMARY KEY, memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL, start_offset INTEGER NOT NULL, end_offset INTEGER NOT NULL,
                    source_sha256 TEXT NOT NULL, indexed_text TEXT NOT NULL, anchors TEXT NOT NULL,
                    vector TEXT, vector_model TEXT);
                CREATE INDEX IF NOT EXISTS code_segments_scope ON code_segments(user_id,memory_id);
            ''')

    def capabilities(self):
        return dict(super().capabilities(), version=VERSION if self.context_policy=='matched-spans' else 'tracemem-code-v0.2-context-dev', track='coding',
                    deployment_profile='coding_candidate', release_stage='development_candidate',
                    retrieval='code-BM25+exact-anchors'+('+dense-RRF' if self.embedding else ''),
                    reranker='original-pinned-Qwen' if self.scoring_adapter else 'disabled',
                    response_content='exact-source-text-spans', segment_bytes=SEGMENT_BYTES,
                    return_text_bytes=self.return_bytes, candidate_limit=100,
                    context_policy=self.context_policy,
                    platform_answer_generated=False, official_score=False)

    def _source_windows(self, order, scores, rows, payload):
        """Project independently ranked hits without changing the candidate scores."""
        uid=payload['user_id'];groups={};rowmap={row[0]:row for row in rows}
        for row in rows:
            groups.setdefault(row[1],[]).append(SourceSpan(row[0],row[1],uid,row[2],row[3],row[4]))
        result=[];selected=set();seen_hashes=set();used=0;projections=[]
        for sid in order:
            if len(result)>=payload['top_k']:break
            row=rowmap[sid];mid=row[1]
            if mid in selected:continue
            with self.connect() as db:
                stored=db.execute('SELECT content FROM memories WHERE user_id=? AND id=?',(uid,mid)).fetchone()
            if stored is None:raise ContractError('source removed during projection',503)
            parts=json.loads(stored[0])
            if len(parts)!=1 or parts[0].get('type')!='text':
                raise ContractError('coding source format mismatch',503)
            try:
                window=source_window(parts[0]['text'],groups[mid],sid,user_id=uid,parent_id=mid,
                                     max_bytes=min(self.context_window_bytes,self.return_bytes-used))
            except ValueError as exc:
                raise ContractError(str(exc),503) from exc
            if window is None or not window.content.strip():continue
            if window.sha256 in seen_hashes:continue
            result.append(dict(id=window.id,content=window.content,score=scores[sid],created_at=row[9]))
            selected.add(mid);seen_hashes.add(window.sha256);used+=len(window.content.encode())
            projections.append(dict(id=window.id,matched_id=window.matched_id,
                                    source_ids=list(window.source_ids),sha256=window.sha256))
        return {'data':result},{'source_segments':len(rows),'candidate_count':len(order),
            'returned_utf8_bytes':used,'exact_source_spans':True,'dense_enabled':self.embedding is not None,
            'context_policy':'source-window','projections':projections,'official_score':False}

    def add(self, payload):
        validate_add(payload)
        if any(not isinstance(message['content'], str) for message in payload['messages']):
            raise ContractError('Coding messages[].content must be a string')
        if len(payload['messages']) > self.model_add_message_limit:
            raise ContractError(f'coding capacity:{self.model_add_message_limit} messages per Add', 413)
        count = total = 0
        for message in payload['messages']:
            size = len(message['content'].encode('utf-8'))
            if size > self.message_source_bytes:
                raise ContractError(f'coding capacity:message_source_bytes limit={self.message_source_bytes}', 413)
            total += size
            if total > self.add_source_bytes:
                raise ContractError(f'coding capacity:add_source_bytes limit={self.add_source_bytes}', 413)
            count += sum(1 for _ in segments(message['content']))
            if count > self.add_segments:
                raise ContractError(f'coding capacity:source_segments limit={self.add_segments}', 413)
        return super().add(payload)

    def _check_dense_scope(self, db, payload):
        super()._check_dense_scope(db, payload)
        if db.execute('''SELECT 1 FROM memories m WHERE m.user_id=? AND NOT EXISTS
            (SELECT 1 FROM code_segments s WHERE s.memory_id=m.id) LIMIT 1''',
                      (payload['user_id'],)).fetchone():
            raise ContractError('coding index incomplete; explicit recovery required', 503)
        for metadata, count in db.execute('''SELECT c.content,count(s.id) FROM cards c
            LEFT JOIN code_segments s ON s.memory_id=c.memory_id WHERE c.user_id=? GROUP BY c.id''',
                                          (payload['user_id'],)):
            if json.loads(metadata).get('segments') != count:
                raise ContractError('coding span index incomplete; explicit recovery required',503)

    def _request_ready(self, db, payload, digest):
        ready = super()._request_ready(db, payload, digest)
        if ready:
            self._check_dense_scope(db, payload)
        return ready

    def _execute_add(self, payload, operation_token=None):
        plans, parents = [], []
        for ordinal, message in enumerate(payload['messages']):
            mid = 'mem_' + hashlib.sha256(canonical([payload['user_id'], payload['session_id'],
                                                    payload['request_id'], ordinal]).encode()).hexdigest()
            parent_plans = []
            for start, end, source in segments(message['content']):
                # Whitespace-only fragments remain in the raw source; they are not retrieval units.
                if not source.strip():
                    continue
                generated = self.card_adapter.extract([{'type':'text','text':source}]) if self.card_adapter else None
                summary = ''
                if generated is not None:
                    if (not isinstance(generated, dict) or not isinstance(generated.get('summary'), str)
                            or not isinstance(generated.get('evidence_quotes'), list)
                            or any(not isinstance(q,str) or q not in source for q in generated['evidence_quotes'])):
                        raise ValueError('invalid source-grounded coding summary')
                    summary = generated['summary']
                    if len(summary.encode('utf-8')) > 2048:
                        raise ValueError('coding summary exceeds2048 UTF-8 bytes')
                indexed = source + ('\n' + summary if summary else '')
                sid = mid + ':' + str(start) + ':' + str(end)
                plan = dict(id=sid, mid=mid, start=start, end=end, indexed=indexed,
                            sha=hashlib.sha256(source.encode()).hexdigest(), anchors=anchors(source),
                            generated=generated, vector=None)
                plans.append(plan); parent_plans.append(plan)
            parents.append((mid, parent_plans))
        if self.embedding:
            for offset in range(0, len(plans), 8):
                batch = plans[offset:offset+8]
                values = self.embedding.embed([p['indexed'] for p in batch])
                if len(values) != len(batch):
                    raise ValueError('coding embedding batch mismatch')
                for plan, vector in zip(batch, values):
                    if len(vector) != 256 or any(type(v) not in (int,float) for v in vector):
                        raise ValueError('invalid coding vector')
                    cosine(vector, vector)
                    plan['vector'] = vector
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            digest = hashlib.sha256(canonical(payload).encode()).hexdigest()
            if operation_token is None and self._request_ready(db,payload,digest):
                return self._echo(payload)
            self._check_dense_scope(db, payload)
            response = self._persist_add(db, payload, operation_token=operation_token)
            for mid, items in parents:
                # Parent vector is an integrity marker for the existing Add journal; Search uses segments.
                vector = items[0]['vector']
                metadata = {'kind':'coding-source-spans', 'segments':len(items),
                            'summaries':[p['generated'] for p in items if p['generated'] is not None]}
                db.execute('INSERT INTO cards VALUES(?,?,?,?,?,?,?,?)',
                           ('card_'+mid[4:],mid,payload['user_id'],payload['session_id'],canonical(metadata),
                            '',canonical(vector) if vector is not None else None,
                            'text-embedding-v4' if vector is not None else None))
            for p in plans:
                db.execute('INSERT INTO code_segments VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (p['id'],p['mid'],payload['user_id'],p['start'],p['end'],p['sha'],
                            p['indexed'],canonical(p['anchors']),canonical(p['vector']) if p['vector'] is not None else None,
                            'text-embedding-v4' if p['vector'] is not None else None))
            if operation_token is not None:
                changed = db.execute("UPDATE add_operations SET state='complete',updated_at=? WHERE user_id=? AND request_id=? AND owner_token=? AND state='preparing'",
                                     (datetime.now(timezone.utc).isoformat(),payload['user_id'],payload['request_id'],operation_token)).rowcount
                if changed != 1:
                    raise ContractError('coding Add ownership changed',503)
        return response

    def retrieve(self, payload):
        validate_search(payload)
        if not isinstance(payload['query'], str):
            raise ContractError('Coding query must be a string')
        query = payload['query']
        if len(query.encode('utf-8')) > 8192:
            raise ContractError('coding query capacity:8192 UTF-8 bytes',413)
        uid = payload['user_id']
        with self.connect() as db:
            db.execute('BEGIN')
            self._check_dense_scope(db, {'user_id':uid,'request_id':''})
            rows = db.execute('''SELECT s.id,s.memory_id,s.start_offset,s.end_offset,s.source_sha256,
                s.indexed_text,s.anchors,s.vector,s.vector_model,m.created_at
                FROM code_segments s JOIN memories m ON s.memory_id=m.id
                WHERE s.user_id=? AND m.user_id=? ORDER BY s.id''',(uid,uid)).fetchall()
        if not rows:
            return {'data':[]}, {'candidate_count':0,'model_calls_required':False}
        rowmap = {row[0]:row for row in rows}
        sparse = sparse_scores(code_tokens(query), {row[0]:code_tokens(row[5]) for row in rows})
        lists = [ranked(sparse)]
        if self.anchor_channel:
            anchor_scores = sparse_scores(anchors(query), {row[0]:json.loads(row[6]) for row in rows})
            lists.append(ranked(anchor_scores))
        if self.embedding:
            vectors = {}
            for row in rows:
                value = json.loads(row[7]) if row[7] is not None else None
                if row[8] != 'text-embedding-v4' or not isinstance(value,list) or len(value)!=256:
                    raise ContractError('coding dense index incomplete',503)
                cosine(value,value); vectors[row[0]] = value
            query_vector = self.embedding.embed([query])[0]
            lists.append(ranked({key:cosine(query_vector,vector) for key,vector in vectors.items()}))
        scores = rrf([items for items in lists if items])
        order = ranked(scores)[:100]
        if self.scoring_adapter and order:
            candidates = [dict(id=sid,retrieval_text=rowmap[sid][5]) for sid in order]
            values = self.scoring_adapter.score([{'type':'text','text':query}],candidates,[scores[sid] for sid in order])
            if len(values)!=len(order) or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
                raise ValueError('invalid coding candidate scores')
            scores = dict(zip(order,values)); order = ranked(scores)
        if self.context_policy=='source-window':
            return self._source_windows(order,scores,rows,payload)
        result, used, counts, seen, parents = [], 0, Counter(), set(), {}
        for sid in order:
            row = rowmap[sid]; mid=row[1]
            if len(result)>=payload['top_k']:
                break
            if counts[mid]>=3 or row[4] in seen:
                continue
            if mid not in parents:
                with self.connect() as db:
                    stored=db.execute('SELECT content FROM memories WHERE user_id=? AND id=?',(uid,mid)).fetchone()
                if stored is None:
                    raise ContractError('source removed during search',503)
                parts=json.loads(stored[0])
                if len(parts)!=1 or parts[0].get('type')!='text':
                    raise ContractError('coding source format mismatch',503)
                parents[mid]=parts[0]['text']
            content=parents[mid][row[2]:row[3]]
            if hashlib.sha256(content.encode()).hexdigest()!=row[4]:
                raise ContractError('coding source digest mismatch',503)
            size=len(content.encode())
            if not content.strip() or used+size>self.return_bytes:
                continue
            result.append(dict(id=sid,content=content,score=scores[sid],created_at=row[9]))
            used+=size; counts[mid]+=1; seen.add(row[4])
        return {'data':result}, {'source_segments':len(rows),'candidate_count':len(order),
                                'returned_utf8_bytes':used,'exact_source_spans':True,
                                'dense_enabled':self.embedding is not None,'official_score':False}
