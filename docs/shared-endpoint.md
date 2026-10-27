# Existing key, separate track implementations

The existing Academic key exposes Textual, Coding and Multimodal evaluations.
A separate Git repository does not require another access key. The website
rejects a second request using the same approved email and reports
`endpoint is immutable for this leaderboard key` when a bound key attempts to
register a different URL after use. Repeating the application cannot solve that.

These endpoint constraints do not mean Coding permission is missing. Coding
v0.2.2 was successfully bound and submitted with the existing key and URLs.

## Withdrawn automatic routing

Do not deploy `compose.gateway.yaml` or activate the v1.0.0 format classifier
for official evaluations. It is retained as a historical implementation.
It routes strings to Coding and content arrays to Multimodal, but the
[official Add/Search integration contract](https://agentmemoryleaderboard.ai/api-guide)
also permits Multimodal strings. The newer guide section's array examples do
not establish that every Multimodal request uses arrays. An all-string history
or query is therefore ambiguous. The earlier requirement that text-only
Multimodal must use arrays was incorrect.

The gateway passed100 repository checks, including byte forwarding, mixed
content and authentication. Those tests assumed disjoint request types and
did not prove full track compatibility. Deployment checks with previously
completed fixtures also cannot resolve the ambiguity. No model or dataset
content should be inspected to guess the intended track.

## Explicit profile selection

The registered route currently serves the fixed Multimodal v2.0.4 backend.
The separate Coding v0.2.2 component and its maintenance URL remain healthy,
but its official registered route is inactive while the Coding failure is
being diagnosed. The repositories, data stores, models, immutable releases
and counters remain independent.

An operator may select one fixed backend for a sequential evaluation only
after confirming no official job is active. Record the target track, exact
release, image and previous route; validate Nginx before reloading, verify
the public health version, then select that same bound version and track on
the official evaluation page. Keep the route fixed for the entire job.
Do not start concurrent jobs for different profiles or resume an older job
against a different backend. Do not infer tracks from benchmark names, IDs,
source meaning, questions or answers. Simultaneous routing requires a
documented platform signal or separately supported endpoints.

The Coding backend changes only its release identifier from v0.2.1: its memory,
provider and receipt implementation is unchanged. The separate Multimodal source
is frozen at `cenzihan/trace-mem-mm` commit
`790e2d73816eefd5ab8b5f11b4ee7056781026bd`. This repository owns the gateway and
Coding component; the other repository owns the Multimodal component. Their
memory databases and call counters remain separate. Both use the existing sole
server-owned financial ledger and the already registered service authentication.

Neither this correction nor a route switch resets a budget or authorizes
new model calls. The original deployment lease and deletion deadline remain.

## Current validation boundary

The Coding official Smoke failed in Add before any new provider calls were
recorded. The platform exposes `ADD_RUNTIME_ERROR` without an HTTP status or
underlying exception; available local records do not establish its cause.
The routing ambiguity is a separate confirmed defect, not a proven explanation
for that Coding failure. Do not claim that HEAD probes or local capacity
limits caused it without request-level evidence.

The prior v0.2.1 engineering preflight completed5 actual GPT and6 embedding
calls on public Git history. This remains a preflight result, not an official
Coding score. Hold further official attempts until the failure is diagnosed;
preserve failed jobs and lifetime counters. Full remains outside the current
authorization.
