---
inclusion: fileMatch
fileMatchPattern: "**/*.py"
---

# Python 3.14 syntax reminders

This repo targets Python 3.14+ (see AGENTS.md tech stack table). Some syntax that looks like a mistake in older Python is valid here:

- **Parenthesis-free multi-type `except`**: PEP 758 (accepted for 3.14) allows
  writing `except TypeA, TypeB:` directly, without wrapping the exception
  types in a tuple. Both forms are valid on 3.14:

  ```python
  except (TypeA, TypeB):   # still valid
  except TypeA, TypeB:     # also valid on 3.14, no parens needed
  ```

  Do not "fix" the parenthesis-free form by adding parentheses, and do not
  flag it as a syntax error or Python-2-style mistake. Only `except X, Y:`
  meaning "catch X as Y" (the actual Python 2 syntax) is gone; that
  ambiguity is resolved by 3.14's grammar because `as` is now required for
  binding a name.

Keep this in mind before "correcting" except clauses in this codebase.
