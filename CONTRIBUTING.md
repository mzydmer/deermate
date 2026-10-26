# Contributing to DeerMate

Thank you for helping build a private assistant that can delegate real work. The local Python worker and Codex adapter are now implemented. See [the setup guide](docs/local-worker.md) for installation and [the roadmap](docs/roadmap.md) for the remaining integrations.

## Agent handoff and specifications

Start with [AGENTS.md](AGENTS.md) and [current status](docs/STATUS.md). [SPEC.md](docs/SPEC.md) defines stable requirements and acceptance criteria; [EVOLUTION.md](docs/EVOLUTION.md) records meaningful changes; [ADRs](docs/decisions/README.md) explain architectural decisions. Use the [feature spec template](docs/specs/TEMPLATE.md) for substantial new contracts. Keep these records aligned with actual implementation and evidence; routine prose fixes do not require a new spec or history entry.

## Useful first contributions

1. Review the worker lifecycle and restart/reconnect semantics.
2. Improve the Codex adapter's lifecycle evidence and bounded recovery.
3. Extend the actual Gateway/SQL verifier to configured-model notifications or upgrade scenarios; local restart and outage checks already have retained receipts.
4. Validate the implemented SSH transport on real restricted accounts. The combined [Gateway/SSH demo](docs/demo.md) already covers protocol enrollment, outage/reconnect and revocation with generated credentials.
5. Improve the documentation or Chinese translation.

Open a [design proposal](https://github.com/mzydmer/deermate/issues/new?template=design-proposal.yml) or [integration request](https://github.com/mzydmer/deermate/issues/new?template=integration-request.yml) before a broad change. Focus a pull request on one outcome; include upstream version references and evidence for any support claim.

## Project conventions

Install developer dependencies with `python -m pip install -e '.[dev]'`. Run the checks in [AGENTS.md](AGENTS.md). Ordinary tests are offline and need no model credentials; `scripts/live_smoke.py --live` is explicitly opt-in and consumes Codex quota. The separate [Gateway verifier](docs/demo.md) requires a pinned upstream checkout and frozen backend environment but makes no model calls.

- Maintain DeerMate-owned backend services in Python. Hermesh is optional external interoperability, not a required Go service.
- Reuse upstream capabilities where practical and keep interfaces narrow.
- Clearly label planned, mocked, and implemented behavior.
- Use supported authentication flows. Never commit credentials, private messages, production traces, or local machine identities.
- Keep English and Chinese README claims aligned.
- Avoid fake installation commands, unsupported performance claims, and unverified security guarantees.
- Include relevant validation when changing lifecycle, policy, or remote-execution code.

## Documentation and media

Check relative links and Mermaid syntax. The README concept assets are original, generated material. Regenerate them with the instructions in [docs/media.md](docs/media.md). Never present the concept dashboard as a screenshot of a shipped application.

## License

Contributions are provided under this repository's MIT license. Include attribution and comply with upstream licenses for any third-party material you introduce.
