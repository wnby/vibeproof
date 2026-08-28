# Day 10: Minimal model reliability layer

Day 10 uses the `gpt-5.6-terra` relay failure as a narrow design input instead of building a defensive framework.

## Delivered

- `TransientModelError` distinguishes temporary transport failures from permanent response and configuration errors.
- `RetryingModelClient` decorates any `ModelClient` and permits at most two total attempts.
- Agents, Tutor, Reviewer, and Coordinator remain unaware of retry behavior.
- OpenAI-compatible Agent requests ask for a standard JSON object response.
- HTTP 429, HTTP 5xx, timeouts, and connection failures are the only retryable paths.
- Invalid model output, authentication failures, configuration errors, and citation failures are not transport retries.
- Three focused tests cover transient recovery, permanent failure, and the two-attempt limit.

## Design boundary

The implementation deliberately adds no provider registry, retry framework, circuit breaker, fallback model, or relay-specific error table. The Agent remains the product; this layer only keeps one temporary network failure from immediately destroying an otherwise valid run.

## Real evaluation

The relay accepted the JSON-mode request, but the bounded real Eval ended after 127.1 seconds when the remote side closed the connection without a response. Scanning, indexing, and runtime pytest passed. No further retry was added because persistent upstream failure is outside this layer's responsibility.
