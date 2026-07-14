# Localisation

This document defines what "localisation maturity" means for this integration and records the audit that closed out the v2.0 gate item (GitHub issue #275).

## Decision: v2.0 ships English-only

v2.0 ships with `translations/en.json` complete and audited. No other language files are included in the initial catalogue submission.

Machine-generated seed translations for other languages were considered and declined. Shipping unreviewed translation quality under the project's name, even as a "starting point for contributors," risks putting incorrect or misleading strings in front of users who select a locale expecting a human-reviewed translation. This can be revisited post-v2.0 if there is contributor demand for a specific language, at which point a human fluent in that language should review the translation before it merges (see "Contributing a new language" below).

## Maturity bar

For this integration, "localisation maturity" means:

1. Every user-facing string an entity, config flow, options flow, repair issue, or service exposes to Home Assistant's frontend is expressed as a translation key, not a literal embedded in Python or YAML.
2. `strings.json` is the single source of truth for those keys and their English text.
3. `translations/en.json` is byte-identical to `strings.json` (enforced by `scripts/check_translations.py`, run in CI and via `make doc-check`). This identity requirement exists because `strings.json` and `translations/en.json` represent the *same* language (English) for two different Home Assistant subsystems: `strings.json` is what the integration ships as its default/reference text, and `translations/en.json` is the actual English locale file HA loads at runtime. They must never drift.
4. Every translation key referenced from code (`translation_key` attributes, `errors["base"]` / `errors[<field>]` dict values, `async_show_form` step ids, `async_abort` reasons, `ir.async_create_issue` translation keys) has a matching entry in `strings.json`.
5. `services.yaml` service and field names/descriptions are mirrored in `strings.json`'s `services` section, so the frontend can override the YAML defaults with localised text.

## Audit performed (2026-07-05)

The following checks were run against the `custom_components/unifi_alerts` tree as part of closing issue #275.

| Area checked | Method | Result |
|---|---|---|
| Hardcoded entity names | `grep` for `_attr_name` across all platform files | Pass. No matches. Every entity uses `_attr_has_entity_name = True` with `_attr_translation_key`. |
| Config flow string literals | Read every `async_show_form`, `async_create_entry`, `async_abort`, and `errors[...]` assignment in `config_flow.py` | Gap found and fixed. |
| Config flow error keys vs `strings.json` | Cross-checked every `errors["base"]` / `errors[<field>]` value against `config.error` and `options.error` in `strings.json` | Gap found and fixed. |
| Config flow abort reasons vs `strings.json` | Cross-checked every `async_abort(reason=...)` value against `config.abort` | Gap found and fixed. |
| Entity `translation_key` values vs `strings.json` `entity` section | Grepped every `translation_key` / `_attr_translation_key` assignment in `binary_sensor.py`, `sensor.py`, `event.py`, `button.py` and matched against the category constants in `const.py` | Pass. All keys present under `entity.binary_sensor`, `entity.sensor`, `entity.event`, `entity.button`. |
| Repair issues vs `strings.json` `issues` section | Grepped every `ir.async_create_issue(...)` call site in `config_flow.py`, `coordinator.py`, `__init__.py` and matched `translation_key` against `strings.json`'s `issues` keys | Pass. All four issue ids (`auth_failed`, `watermark_persist_failed`, `webhook_secret_rotated`, `webhook_urls_changed`) match, including `translation_placeholders` usage (`{name}`) lining up with placeholders in the corresponding `strings.json` text. |
| `services.yaml` vs `strings.json` `services` section | Read both files side by side | Pass. Both services (`clear_category`, `clear_all`) and every field (`category`, `entry_id`) are mirrored. |
| `strings.json` / `translations/en.json` byte identity | `scripts/check_translations.py` | Pass. |

Two gaps were found and fixed (missing options-flow error keys, missing SSDP abort reason); see the PR history for issue #275 for the specific details. `strings.json` and `translations/en.json` remain byte-identical, verified with `diff`.

## Contributing a new language

Adding a new language is a documented, welcome contribution path for after v2.0:

1. Copy `custom_components/unifi_alerts/translations/en.json` to `custom_components/unifi_alerts/translations/<lang>.json`, where `<lang>` is the two-letter (or `xx-YY`) locale code Home Assistant expects (e.g. `es.json`, `de.json`, `pt-BR.json`).
2. Translate every string *value*. Do not add, remove, rename, or reorder any *keys* - the key structure must stay identical to `en.json`, only the text changes.
3. Keep placeholders (`{name}`, `{current_url}`, `{docs_url}`) intact and in a position that reads naturally in the target language - do not translate the placeholder names themselves.
4. Do not touch `strings.json` or `translations/en.json`. The byte-identity requirement enforced by `scripts/check_translations.py` is specific to those two files (`strings.json` <-> `translations/en.json`), because they represent the same language for two different HA subsystems. A new language file is a translation of `en.json`'s *content* into another language; it is never compared against `strings.json` by tooling and does not need to match it structurally beyond having the same keys.
5. Open a PR with just the new `translations/<lang>.json` file. Since this only affects a new file with no change to existing behaviour, it does not require a `CHANGELOG.md` entry unless the maintainer requests one; apply the `documentation` label if no other CI-recognised label fits.
6. A maintainer (or a reviewer fluent in the target language) reviews the translation for accuracy before merging. Machine-translated submissions without human review of the target language will not be accepted, for the same reason none were seeded for v2.0.
