# CI and model-free verification

The workflow in `.github/workflows/ci.yml` is prepared for pushes to `main`, pull requests, and manual dispatch. It targets Windows 2022 runners with Python 3.11 and 3.12. It has read-only repository permissions and does not publish artifacts or packages.

The test environment installs only `jsonschema`, `psutil`, and their dependencies, then installs this package with `--no-deps`. Speech, text, OCR inference packages, model weights, Ollama, and Instagram access are not needed. The workflow asserts that inference packages were not installed and sets Hugging Face offline mode for tests.

The suite exercises contracts, grounding rules, parser fixtures, JSON/summary interfaces, deadlines, child-process cleanup, and mocked provisioning. It does not prove model accuracy, end-to-end media extraction, or clean-machine prerequisite installation.

Run the same commands locally in a disposable environment:

```powershell
python -m venv work/ci-venv
& .\work\ci-venv\Scripts\python.exe -m pip install -r requirements-ci.txt
& .\work\ci-venv\Scripts\python.exe -m pip install --no-deps .
& .\work\ci-venv\Scripts\python.exe scripts/check_repository.py
& .\work\ci-venv\Scripts\python.exe -m unittest discover -s tests -v
& .\work\ci-venv\Scripts\python.exe -m unittest discover -s scripts -p "test_*.py" -v
```

Package/build dependency installation requires network access unless an appropriate package cache is available. Test execution itself makes no platform/model download requests. A model-free test environment intentionally does not satisfy all runtime dependencies; use `install.cmd` for real extraction.

Current hosted results are available on [GitHub Actions](https://github.com/enros7500/savedex-extractor/actions/workflows/ci.yml). Report local checks separately from hosted CI results; a green unit-test run does not imply real model-quality or clean-machine installation validation.
