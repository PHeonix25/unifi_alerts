## Summary

<!-- What does this PR do? One or two sentences. -->

## Changes

<!-- List the key files/areas changed and why. -->

- 

## How to test

<!-- Steps a reviewer can follow to verify the change works. Include relevant `make` commands. -->

```bash
make check   # lint + typecheck + validate + all tests
```

## Checklist

- [ ] `make check` passes locally
- [ ] `CHANGELOG.md` `[Unreleased]` updated (user-visible changes only; skip for internal/ci/docs)
- [ ] PR title starts with a Conventional Commit prefix (`feat:`, `fix:`, `docs:`, `ci:`, `tests:`, `security:`, `chore:`, `refactor:`)
- [ ] PR has a label recognised by `.github/release.yml` (applied automatically for CC-prefixed titles via pr-labeler)
- [ ] `strings.json` and `translations/en.json` are still identical (if either was touched)
- [ ] New category fully registered: `const.py`, `strings.json`, `translations/en.json` (if adding a category)
- [ ] No blocking I/O introduced (all network/disk calls are `async`)
