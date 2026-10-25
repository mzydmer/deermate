# Contributing to DeerMate

Thank you for helping build a private assistant that can delegate real work. The local Python worker and Codex adapter are now implemented. See [the setup guide](docs/local-worker.md) for installation and [the roadmap](docs/roadmap.md) for the remaining integrations.

## Useful first contributions

1. Review the worker lifecycle and restart/reconnect semantics.
2. Propose a narrow Codex app-server adapter proof.
3. Validate DeerFlow's background MCP task contract against a pinned version.
4. Review SSH enrollment, limited execution accounts, and revocation requirements.
5. Improve the documentation or Chinese translation.

Open a [design proposal](https://github.com/mzydmer/deermate/issues/new?template=design-proposal.yml) or [integration request](https://github.com/mzydmer/deermate/issues/new?template=integration-request.yml) before a broad change. Focus a pull request on one outcome; include upstream version references and evidence for any support claim.

## Project conventions

Install developer dependencies with `python -m pip install -e '.[dev]'`. Run `ruff check src tests scripts/live_smoke.py`, `python -m pytest -q`, and `python -m build --wheel`. Ordinary tests are offline and need no model credentials; `scripts/live_smoke.py --live` is explicitly opt-in and consumes Codex quota.

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
