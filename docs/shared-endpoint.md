# One AML key with separate Coding and Multimodal services

The existing Academic key exposes Textual, Coding and Multimodal evaluations.
A separate Git repository does not require another access key. The website
rejects a second request using the same approved email and reports
`endpoint is immutable for this leaderboard key` when a bound key attempts to
register a different URL after use. Repeating the application cannot solve that.

The [official API guide](https://agentmemoryleaderboard.ai/api-guide) specifies
string `messages[].content` and string `query` for Coding, and ordered
`ContentPart[]` for Multimodal. The stateless gateway selects a fixed loopback
backend using these documented JSON types. It does not examine source meaning,
user ID conventions, benchmark names, questions or answers.

| Operation format | Fixed component |
|---|---|
| Add with all string contents; Search with string query | TraceMem-Code v0.2.2, loopback8770 |
| Add containing an ordered content array; Search with array query | TraceMem-MM v2.0.4, loopback8769 |

Native multimodal histories with array user content and plain assistant replies
remain supported. Text-only Multimodal requests must retain array form, including
text-only questions. All-string requests are the Coding profile; the gateway
cannot infer a different intended track from an undocumented payload shape.
Textual evaluation is not claimed by this release.

The Coding backend changes only its release identifier from v0.2.1: its memory,
provider and receipt implementation is unchanged. The separate Multimodal source
is frozen at `cenzihan/trace-mem-mm` commit
`790e2d73816eefd5ab8b5f11b4ee7056781026bd`. This repository owns the gateway and
Coding component; the other repository owns the Multimodal component. Their
memory databases and call counters remain separate. Both use the existing sole
server-owned financial ledger and the already registered service authentication.

The gateway has no provider credentials or memory database. It forwards exact
body bytes and response order, preserves backend status and Retry-After, and
never retries a request. It rejects duplicate JSON keys, malformed types,
unauthorized requests and bodies over64MiB. There are32 admitted requests;
one body is decoded/sent at a time and responses are streamed in64KiB chunks.
Both original backends retain their own16-slot admission limits. Its health
response lists and checks both exact component versions. Lease expiry is the
same existing date, not a new extension. No request/response contents are logged.

Deploy `compose.gateway.yaml` only after the two fixed components are healthy.
The operator points the existing registered Add/Search path at loopback8771,
then binds the Coding version to those unchanged registered URLs and selects
Coding in the official evaluation page. Separate component URLs may remain for
maintenance. No existing official run may be active during route replacement;
preserve the prior Nginx configuration for rollback. Binding alone is not a
passed Smoke. Full is not authorized by this integration workflow.

Validation covers exact byte forwarding, native mixed content, text-only arrays,
authentication, malformed JSON, lifetime expiry, admission, disconnected clients,
upstream errors and zero automatic retries. Deployment acceptance uses existing
completed idempotence fixtures and empty isolated scopes without fresh provider
calls. The prior v0.2.1 preflight used5 actual GPT and6 embedding calls; this
transport addition is not another paid experiment or an official quality score.
