# No token streaming; the output guard sees the full answer first

Answers are returned only after deterministic output checks and the grounding judge pass, so tokens are not streamed to the user. Streaming would show text that might later fail the guard (leaked PII, invalid citations, exfiltration URLs), and retracting text the user already saw is not a real control. The cost is latency: the target is p95 ≤ 8 s instead of a sub-2 s first token; the UI shows progress states instead.

## Considered Options

- **Stream, then retract on failure**: better perceived latency; rejected because the leak has already happened.
- **Stream only after a cheap pre-check**: still streams unverified grounding; may be revisited for low-risk tenants.
