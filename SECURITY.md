# Security policy

The UniFi Alerts integration runs inside Home Assistant on the local network. A
vulnerability in the integration could expose UniFi controller credentials,
allow webhook spoofing, or interfere with the HA installation. We take security
reports seriously and respond as quickly as a single-maintainer project can.

## Reporting a vulnerability

**Do not file public GitHub issues for security bugs.** Public issues alert
attackers before users have a chance to update.

Instead, open a [private vulnerability report on GitHub](https://github.com/PHeonix25/unifi_alerts/security/advisories/new).
This route gives the maintainer a private channel to triage, draft a fix, and
coordinate disclosure timing.

If you cannot use GitHub's private advisories - for example, you do not have a
GitHub account - open a regular GitHub issue titled `Security: please contact me
privately` containing **only** a way to reach you (e.g. an email handle), and
the maintainer will respond out-of-band. Do not include any technical details
about the vulnerability in the public issue.

## What to include

A useful report contains:

- The affected component (file path, function, or feature).
- The integration version (`manifest.json` `version` field) and Home Assistant
  version where you reproduced the issue.
- A minimal reproduction (config snippet, payload, or step list).
- The impact you believe the bug enables (credential disclosure, RCE, denial of
  service, webhook forgery, etc.).
- Any proof-of-concept code, if you have one. PoCs are appreciated but never
  required.

## What's in scope

Security-relevant components of this integration include:

- The webhook handler (`webhook_handler.py`): bearer-token validation,
  payload-size limits, decode handling.
- The UniFi controller client (`unifi_client.py`): auth flows, SSL handling,
  URL validation.
- The config and options flows (`config_flow.py`): SSRF, credential exposure
  through the UI / logs / diagnostics.
- The diagnostics platform (`diagnostics.py`): correctly redacting credentials
  before disclosure.
- CI / release workflows (`.github/workflows/`): supply-chain integrity (action
  pinning, release packaging).

See [docs/DATA_HANDLING.md](docs/DATA_HANDLING.md) for the full statement of
what this integration persists to disk, what stays memory-only, what appears
in diagnostics downloads (and what is redacted from them), and what is logged
at DEBUG.

## Webhook authentication: header vs legacy query parameter

Inbound webhook requests are authenticated with a per-entry bearer secret,
checked via `hmac.compare_digest` (timing-safe). Two forms are accepted:

- **`Authorization: Bearer <secret>` header (preferred, issue #176).** Headers
  are not captured by reverse-proxy or web-server access logs, browser
  history, or screenshots of the config flow the way a query string is, so
  this form has less exposure surface.
- **`?token=<secret>` query parameter (deprecated).** Kept for backwards
  compatibility during a migration window so existing UniFi Alarm Manager
  configurations are not broken by the header migration. Will be removed no
  earlier than v3.0.0. A webhook authenticated this way raises the
  `webhook_legacy_query_auth` repair issue prompting migration to the header
  form.

Both forms carry the same risk profile if the secret itself leaks (e.g.
pasted into a public log or issue): whoever holds it can POST to the webhook
endpoint until the secret is rotated. Config- and options-flow "Webhook URLs"
screens no longer embed the secret in the displayed URL; it is shown
separately for the user to set as a header value (or, for the legacy form,
to append manually).

## Webhook secret rotation

The options flow can regenerate the per-entry webhook bearer secret. Rotation
replaces the value validated against both the `Authorization` header and the
legacy `?token=<value>` query parameter; the webhook URL path (which embeds
an 8-character entry suffix) is **not** rotated. An attacker who captured the
old secret can still POST to the same endpoint, but the constant-time check
(`hmac.compare_digest`) rejects the request.

If true URL-path revocation is ever required (e.g. the suffix itself is
believed compromised), the only recovery is to delete and re-add the config
entry. Rotation alone is sufficient for the common "I think my secret leaked"
case; it is not sufficient for "the URL has been published publicly".

## Schema version 3 migration (v1.7)

v1.7 introduced a config entry schema version 3 migration that backfills
`webhook_secret` and `webhook_id_suffix` on any entry that lacks them. This
affects installations that were originally set up before v1.4.0 and have never
been reconfigured via the options flow.

The webhook handler now fails closed: if no secret is configured, incoming
requests are rejected with HTTP 500 instead of being accepted silently. This
removes the pre-v1.7 bypass where an empty `CONF_WEBHOOK_SECRET` caused the
token check to be skipped entirely.

Users who installed before v1.4.0 and have never reconfigured should
re-paste their webhook URLs into the UniFi Alarm Manager after upgrading.
New webhook URLs are available at Settings > Devices & Services >
UniFi Alerts > Configure.

## Accepted CodeQL false positives

- **`py/clear-text-logging-sensitive-data` at `unifi_client.py` (debug logs of alarm/probe URLs).** First identified on PR #259: `_LOGGER.debug("Fetching alarms from %s", url)` (and the equivalent v2 system-log probe/fetch debug logs) trace back through `self._base`/`controller_url` to the config dict (`UniFiClientConfig`, which also carries `api_key`) passed into `UniFiClient.__init__`. No secret ever reaches the log line - every hop only ever carries the controller hostname/URL and a fixed API path, never the API key itself. The alert fires because CodeQL's Python dataflow analysis is field-insensitive on dicts: reading *any* key out of a dict that *also* contains a sensitive key (`api_key`) gets tainted, regardless of which key is actually read.
  `UniFiClientConfig` was restructured as an explicit `TypedDict` (in PR #195) specifically to test whether giving CodeQL field-level type information would stop the over-tainting (tracked as issue #261). Re-running the CodeQL workflow with the TypedDict already in place, the alert still fires: `TypedDict` is a static-typing construct with no runtime distinction from a plain `dict`, so CodeQL's dataflow analysis - which operates on runtime dict-access patterns, not static annotations - cannot distinguish "read `controller_url`" from "read `api_key`" on the same dict object. No further code change is expected to resolve this; the alert is dismissed as an accepted false positive rather than fixed. Re-triaging this exact shape from scratch is unnecessary; link back to this note and issues #259/#261 instead.

## What's out of scope

- Vulnerabilities in upstream Home Assistant Core or in third-party HA
  integrations. Report those to their respective maintainers.
- Vulnerabilities that require local access to a Home Assistant administrator
  account that already has full system privileges. (HA admins are by design
  trusted.)
- Issues that depend on the UniFi controller itself being compromised; the
  integration trusts its configured controller. Report those to Ubiquiti.
- Denial-of-service via maliciously crafted *valid* alerts (UniFi can already
  fire these directly). The 5s `(category, alert_key)` debounce mitigates flood
  scenarios; severe abuse still merits a report.

## Disclosure

Once a fix is ready and released, the corresponding GitHub Security Advisory
will be made public alongside the release notes. Reporters are credited unless
they ask to remain anonymous.
