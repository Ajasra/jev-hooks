# Gotcha: Adapter Monotonic Deadline Timeout Flakiness
- **Tags**: [adapters, deadline, timeout, pytest]
- **Trap**: Adapter._deadline defaulting to 2.0 seconds caused intermittent hook timeouts and extra timeout events in SQLite during high-concurrency pytest runs or GC pauses.
- **Remediation**: Set default deadline in Adapter._deadline to at least 30.0s so unit tests and hook dispatches do not falsely trip.
