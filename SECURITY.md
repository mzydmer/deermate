# Security policy

DeerMate is a local worker alpha with no production release or independent audit. Run only on loopback with trusted repositories. Remote SSH, multi-user isolation, and the full assistant platform are not implemented. Use a dedicated account or VM before granting access to sensitive hosts or data.

The proposed threat model and trust boundaries are documented in [docs/security.md](docs/security.md).

## Reporting

For design concerns without sensitive details, open a design issue. For a vulnerability, use GitHub's **Report a vulnerability** / private security reporting option if the repository provides it. This option depends on the repository's enabled settings and is not claimed to be configured here.

If a private channel is unavailable, open a minimal issue requesting a private contact without exploit details, secrets, private data, or host identifiers. Wait for the maintainer to establish a private channel before sending sensitive evidence.

No response SLA or security audit is currently offered. Vulnerabilities in an upstream project should be reported through that project's own security process.
