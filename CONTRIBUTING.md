# Contributing

Start with the [README](README.md) and [roadmap](ROADMAP.md). The scope is a local extraction CLI; external research and cloud inference are not enabled.

Use the [model-free CI environment](docs/CI.md) for unit tests. Use `install.cmd` for local extraction, and keep generated results under ignored `outputs/`.

Before proposing a change:

1. Run application and setup tests.
2. Run `python scripts/check_repository.py` for repository hygiene and documentation links.
3. Preserve one-JSON-object stdout for `extract`, separate diagnostics, and documented exit codes.
4. Provide evidence for extraction changes and label synthetic fixtures clearly.
5. Keep weights, caches, credentials, private paths, and downloaded media out of Git.

The project is MIT licensed. See [third-party notices](THIRD_PARTY_NOTICES.md) for dependencies, models, and publication content.
