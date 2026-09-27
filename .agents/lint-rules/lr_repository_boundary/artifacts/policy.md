# Repository boundary

Persistence access must remain encapsulated within `src/jev/services/storage.py` (or designated persistence modules). Business logic, adapters, and tools must not execute raw SQL or bypass storage abstractions.

This rule begins in `observe` mode. Promote it through a committed metadata change only after reviewed database feedback demonstrates acceptable accuracy.
