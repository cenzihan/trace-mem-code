"""Freeze public Git-history engineering fixtures without reading target patches.

This is a transport/retrieval regression, not CAMBench, SWEContextBench or an
unseen benchmark. Queries use real later change subjects and changed-file names;
the temporal same-file association is a diagnostic proxy, not relevance gold.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from agent_memory.coding import segments

BASE = '18aff5a1da91a7ab8817e603c1e577824dd98cbf'


def freeze(repository, output):
    def git(*args):
        return subprocess.check_output(['git','-c','core.quotepath=false','--no-pager',*args],
                                       cwd=repository,encoding='utf-8')
    if output.exists():
        raise ValueError('freeze exists; never overwrite an executed input')
    git('cat-file','-e',BASE+'^{commit}')
    targets=git('log','--format=%H',BASE,'--','agent_memory').splitlines()
    selected=[]; used=set()
    for target in targets:
        paths=git('diff-tree','--no-commit-id','--name-only','-r',target,'--','agent_memory').splitlines()
        for path in sorted(p for p in paths if p.endswith('.py')):
            previous=git('log','-1','--format=%H',target+'^','--',path).strip()
            if not previous or (previous,path) in used:
                continue
            # Only the earlier source patch is read. No target patch or test outcome is opened.
            historical=git('show','--format=%s%n%b','--no-ext-diff','--no-renames','--unified=3',previous,'--',path)
            source=f'Repository: cenzihan/trace-mem-mm\nHistorical commit: {previous}\nFile: {path}\n'+historical
            if not 300 <= len(source.encode()) <= 7000:
                continue
            subject=git('show','-s','--format=%s',target).strip()
            query=f'Engineering change: {subject}\nTarget file: {path}\nWhich earlier engineering history is useful for this change?'
            selected.append({'id':f'case-{len(selected)+1}','source_commit':previous,
                             'target_commit':target,'file':path,'source':source,'query':query,
                             'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                             'query_sha256':hashlib.sha256(query.encode()).hexdigest()})
            used.add((previous,path)); break
        if len(selected)==4:
            break
    if len(selected)!=4:
        raise ValueError('four eligible temporal source/intent pairs required')
    output.mkdir(parents=True)
    payload={'schema':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
             'repository':'https://github.com/cenzihan/trace-mem-mm','fixed_public_commit':BASE,
             'selection':'newest four distinct change commits with an earlier same-file patch of300..7000UTF8 bytes; file names sorted; complete patches retained',
             'source_authorization':'existing user-owned audited public repository; retain its attribution and NOTICE',
             'target_patches_read':False,'official_dataset':False,'unseen_evidence':False,
             'query_kind':'real change subject plus file metadata; constructed retrieval request',
             'relevance_proxy':'earlier same-file change; not human-annotated relevance or task-solving score',
             'cases':selected}
    raw=(json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode()
    (output/'INPUT.json').write_bytes(raw)
    (output/'INPUT.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    gpt_calls=2*sum(sum(bool(part.strip()) for _,_,part in segments(c['source'])) for c in selected)
    if gpt_calls+17 > 32:
        raise ValueError('input exceeds the32-call preflight capacity; do not dispatch')
    plan={'input_sha256':hashlib.sha256(raw).hexdigest(),'cases':4,'conditions':['relevant-one-history','noisy-four-histories'],
          'add_requests':8,'search_requests':8,'restart_searches':1,
          'expected_provider_calls':{'gpt-4o-mini':gpt_calls,'text-embedding-v4':17},
          'qwen_calls':0,'provider_call_cap':32,'maximum_preflight_cny':'8',
          'money_ledger':'existing server /opt/tracemem-access-v1/runtime/development-budget.sqlite only',
          'no_replay_unknowns':True,'no_completed_grant_reuse':True,
          'official_smoke_calls':0,'official_full_authorized':False}
    (output/'PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
    return {'input_sha256':plan['input_sha256'],'cases':len(selected),
            'source_bytes':[len(c['source'].encode()) for c in selected],
            'provider_call_cap':32,'expected_provider_calls':gpt_calls+17,'official_score':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--repository',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    print(json.dumps(freeze(args.repository,args.output)))
