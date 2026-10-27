"""Pure source projections; no model calls, summaries, persistence or execution.

Inspired by DSH's distinction between original events and derived context with
explicit source references. This is an original source-window implementation,
not a port of DSH's agent loop, compaction algorithm or event format.
"""
from dataclasses import dataclass
import hashlib


@dataclass(frozen=True)
class SourceSpan:
    id: str
    parent_id: str
    user_id: str
    start: int
    end: int
    sha256: str


@dataclass(frozen=True)
class SourceWindow:
    id: str
    content: str
    source_ids: tuple
    matched_id: str
    sha256: str


def source_window(source, spans, matched_id, *, user_id, parent_id, max_bytes=12288):
    """Keep the match, then at most one contiguous neighbor on either side.

    Neighbors use source order, with the previous span considered first. Gaps
    (including unindexed whitespace) are never crossed. The entire admitted
    parent's span index is checked against the raw source before projection.
    A match too large for the remaining budget returns None, never a clipped match.
    """
    if not isinstance(source,str) or type(max_bytes) is not int or not 0 <= max_bytes <= 32768:
        raise ValueError('invalid source projection input or UTF-8 budget')
    if not spans or not user_id or not parent_id:
        raise ValueError('explicit source scope required')
    ordered=sorted(spans,key=lambda item:(item.start,item.end,item.id))
    seen=set();last_end=0;match_index=None
    for position,item in enumerate(ordered):
        if item.user_id != user_id or item.parent_id != parent_id:
            raise ValueError('source projection scope mismatch')
        if (type(item.start) is not int or type(item.end) is not int
                or not 0 <= item.start < item.end <= len(source) or item.start < last_end
                or item.id in seen or item.id != f'{parent_id}:{item.start}:{item.end}'):
            raise ValueError('invalid source span identity or range')
        if hashlib.sha256(source[item.start:item.end].encode()).hexdigest()!=item.sha256:
            raise ValueError('source projection digest mismatch')
        seen.add(item.id);last_end=item.end
        if item.id==matched_id:match_index=position
    if match_index is None:
        raise ValueError('matched source span is absent')
    match=ordered[match_index];start,end=match.start,match.end;selected=[match]
    if len(source[start:end].encode())>max_bytes:
        return None
    if match_index:
        previous=ordered[match_index-1]
        if previous.end==start and len(source[previous.start:end].encode())<=max_bytes:
            selected.insert(0,previous);start=previous.start
    if match_index+1<len(ordered):
        following=ordered[match_index+1]
        if following.start==end and len(source[start:following.end].encode())<=max_bytes:
            selected.append(following);end=following.end
    content=source[start:end]
    return SourceWindow(f'{parent_id}:{start}:{end}',content,
                        tuple(item.id for item in selected),matched_id,
                        hashlib.sha256(content.encode()).hexdigest())
