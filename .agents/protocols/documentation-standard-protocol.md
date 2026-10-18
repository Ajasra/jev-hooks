# Documentation conventions

Scope: JEV documentation. Other repositories retain their own layout and conventions.

- Lead with the reader's task and concrete outcome. Put operational instructions
  before architecture details when the audience needs to use the software.
- Keep the root README a short entry point, aiming for 150 lines rather than a
  hard gate. Link deeper guides instead of repeating background everywhere.
- Use PHILOSOPHY for concepts, USER_GUIDE for operations, and ARCHITECTURE for
  contracts where those documents exist. Do not create this layout for every project
  or force every short document through three stages.
- Use relative links in checked-in Markdown. Write copyable commands for the
  actual shell/platform; `cmd /c` and `%CD%` are Windows cmd conventions, not universal
  portability syntax. Give separate variants only when needed.
- Preserve JEV's existing `RFC-XX_CATEGORY_slug.md` convention for new proposals.
  Reuse the catalog's categories and header shape instead of renaming old proposals.
- Verify changed commands and links when relevant. A docs edit does not require
  a runtime test suite, three screenshots, or a separate style scan.

Follow the optional [voice profile](style-protocol.md) and
[editing guidance](anti-slop-protocol.md) when applicable.
