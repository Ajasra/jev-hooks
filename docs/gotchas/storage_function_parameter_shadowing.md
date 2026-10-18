# Gotcha: Storage Function Parameter Shadowing
- **Tags**: [storage, python, scoping, hashing]
- **Trap**: Function parameter named operation_digest shadowed the module-level pure hashing function operation_digest, causing TypeError: NoneType object is not callable when None was passed.
- **Remediation**: Alias module-level pure helpers (e.g. jev_operation_digest = operation_digest) and keep parameter names distinct (e.g. op_digest).
