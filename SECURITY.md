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

If you cannot use GitHub's private advisories — for example, you do not have a
GitHub account — open a regular GitHub issue titled `Security: please contact me
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
