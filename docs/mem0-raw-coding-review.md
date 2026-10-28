# Mem0 and DeepSeek Harness applicability review

Reviewed 2026-10-28. The candidate is `coding_raw_app`, source revision
`75e5f4169966b6e10f1302aeb568f2fee530edd4`. It has not yet established an
official Coding score.

## References and scope

[Mem0's actual implementation](https://github.com/mem0ai/mem0/blob/main/mem0/memory/main.py)
has an `infer=False` branch that embeds raw messages, preserves message-role
metadata, and scopes operations by identifiers. Its
[Add documentation](https://github.com/mem0ai/mem0/blob/main/docs/core-concepts/memory-operations/add.mdx)
distinguishes raw storage from inferred memories and warns about duplicate raw
inserts. This is an appropriate reference for retaining code, logs and exact
identifiers without paying for or relying on fact extraction for every span.
TraceMem's candidate is an independent implementation, not the Mem0 SDK or a
Mem0 performance reproduction.

[DeepSeek Harness sessions](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/docs/subsystems/session.md)
use an append-only event log as the source for derived model messages. The
relevant transfer is keeping original evidence separate from a bounded context
view. Our source-window implementation verifies offsets and hashes and returns
contiguous original text. It does not recreate DSH tool events or compaction.

## Candidate assessment

The raw candidate preserves source order, request-level idempotence, isolated
users, atomic publication after all embedding batches, and uncertain-operation
blocking. New spans use eight-item batches of `text-embedding-v4`; old source
indexes remain intact. Retrieval combines code-aware BM25, path/symbol anchors
and dense rank fusion, then returns bounded source windows. No generated answer,
DeepSeek model, tool execution or reranker is added.

Capacity admission allows up to 1,024 messages, 2 MiB per message, 8 MiB per Add
and 2,048 spans. These are explicit local bounds, not inferred official workload
sizes. The original 512-call lifetime guard retains at least 16 query calls.
An independent synthetic test fixed FACT-like code literals being misinterpreted
as structured event dates. That 422 repair does not establish the cause of the
earlier official 413 failures.

[AML's current guide](https://agentmemoryleaderboard.ai/api-guide) requires
`text-embedding-v4` for Academic embeddings and `gpt-4o-mini` for LLM components.
This candidate has no LLM component on new writes or Search. The platform owns
answering and grading; its executor model is separate from our memory service.
Official material is evaluation-only and is excluded from this review and
independent controls.

## Remaining validation

The existing 120 offline checks and successful Docker CI are engineering evidence.
A separately frozen, user-owned public-source control must establish actual
embedding transport, source integrity and restart/idempotence behavior before
deployment. One independently recorded official Smoke then tests compatibility;
neither proxy retrieval ranks nor offline tests substitute for that result.
Raw indexing can lose semantic abstraction, and source windows can reduce
evidence diversity. Neither reference establishes a quality improvement here.

## Network failure handling in rc3

The independent rc2 control stopped after two successful embedding batches and
one unknown network outcome. No quality result or official compatibility result
was obtained. The unknown receipt and its entire conservative money hold remain.

Rc3 adds an operator-installed proof for a frozen failed execution. It validates
the unchanged unknown receipt and accounting, blocks its user and all frozen
source-span hashes, and permits unrelated new inputs. Request handling cannot
create this proof. Any subsequent unknown still blocks dispatch. Legacy receipts
do not identify their payload, so this conservatively retires the entire frozen
control rather than claiming an exact unknown-batch attribution. The lifetime
512-call guard and original money ledger remain unchanged. All 134 offline checks
passed, including replay prevention and invalidated-proof controls.
