# Raw trajectory candidate v0.3.0-rc2

Status: independent offline candidate, not deployed or officially scored.
This is stacked on the long-trajectory capacity candidate, preserving its source
bounds, atomic writes, original state and provider history. It is an explicit
alternative to per-span source summarization, not a fallback after a failed call.

Every new Add preserves complete original messages and indexes raw4096-byte spans
with text-embedding-v4 at256 dimensions in batches of at most8. No source-summary
LLM is constructed, and its transport rejects GPT before any receipt preparation,
credential read or money reservation. Code BM25, exact path/symbol anchors, dense
rank fusion and original-source windows remain unchanged. Previously stored
summaries and their source indexes remain intact; this is not a database reset.

With2048 source spans, a write plans256 embedding calls instead of2048 GPT calls
plus256 embedding calls. With11 historic receipts, this fits the original512-call
ceiling and still leaves16 reserved Search calls. Whole-write cost admission uses
the existing conservative per-item allowance and5CNY readiness floor; every real
provider call must separately reserve money in the original shared ledger. No
allowance is increased. Partial or uncertain model work remains blocked, with no
automatic replay, hidden fallback, or partially acknowledged Add.

Entry point: `agent_memory.coding_raw_app:create_app()`, with explicit
`TRACEMEM_CODING_RAW_ENABLED=approved-raw-original-state` in addition to the
original official Coding activation. The published v0.2.2 default is unchanged.
This file is a candidate specification, not instructions to change a live route.

Independent synthetic regressions cover a1024-message/2048-span atomic write,
original-text integrity, replay after restart, user isolation, preserved lifetime
and money bounds, later-batch uncertainty, and GPT dispatch rejection. These are
engineering controls, not benchmark quality or real latency measurements. The
historical HTTP413 branch remains unknown. Real bounded validation and a separate
fixed-backend window are still required before deployment or official Smoke.

The rc2 preflight treats source text literally. A code fixture or log line matching
the inherited `FACT ... event=...` template, including an intentionally invalid
date, no longer causes a422 rejection of the entire Add. This was reproduced with
independent synthetic source text before the fix. Structured message timestamps,
capacity checks and whole-Add provider/money admission remain enforced before
claiming work. Regression controls check exact source retrieval, restart replay,
user isolation, invalid structured timestamps and denied-budget admission. This
is a separate observed defect; it does not diagnose the historical413 failure.
