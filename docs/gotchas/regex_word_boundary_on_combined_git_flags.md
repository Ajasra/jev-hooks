# Gotcha: Regex Word Boundary on Combined Git Flags
- **Tags**: [safety, regex, git, invariants]
- **Trap**: Using word boundary on force flag fails on compound arguments like git clean with force/directory flags because subsequent letters prevent word boundary match.
- **Remediation**: Use multi-letter regex patterns to correctly match flags regardless of position within compound argument lists.
