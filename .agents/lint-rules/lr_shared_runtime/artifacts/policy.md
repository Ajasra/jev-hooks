# Shared runtime implementation boundary

Runtime behavior belongs under `src/jev/`. Harness adapters translate native protocols, hook files bootstrap the installed package, and compatibility entry points delegate without owning feature logic.

This rule begins in `observe` mode. Promote it through a committed metadata change only after reviewed database feedback demonstrates acceptable accuracy.
