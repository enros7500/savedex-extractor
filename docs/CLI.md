# Content Extractor CLI · 1.0.0

A local tool that any backend can invoke as a subprocess. Content contract **3.0.0**, CLI interface **1.1.0**. Tested on Windows with medium on CPU. No external AI, web research, geocoding, or Maps lookup.

For one-command Windows installation, run `./install.cmd` at the repository root. See the [setup guide and output examples](../README.md#installation).

## Quick start

Open PowerShell in the project folder and run with a real publication URL (the example URL below is a placeholder):

```powershell
.\reel "https://www.instagram.com/p/EXAMPLE1234/"
```

The default prints a single JSON object. For a readable conclusion instead:

```powershell
.\reel summary "https://www.instagram.com/p/EXAMPLE1234/"
```

To save JSON, then read it without processing the reel again:

```powershell
.\reel "https://www.instagram.com/p/EXAMPLE1234/" | Out-File outputs/my-result.json -Encoding utf8
.\reel summary --result outputs/my-result.json
```

The short launcher resolves the installed environment and model under `work/` relative to the repository root. The project-root `reel.cmd` calls `scripts/reel_launcher.py`. `reel --help` and `reel summary --help` show available options.

The summary reports extracted items, announced counts, sources actually reviewed, unreviewed media, unresolved gaps, and elapsed processing time when recorded. It formats existing data without another AI call or research. A `success` status means the extractor considered the reviewed sources sufficient; it does not establish full video coverage. Saved results retain their original text and language; the summary does not translate or repair earlier extractions.

## Direct executable

The installed CLI is available at:

```powershell
$base = (Get-Location).Path
$cli = "$base\work\asr-venv\Scripts\content-extractor.exe"
$model = "$base\work\models\faster-whisper-medium"
& $cli doctor --json --model-dir $model
& $cli extract --url 'https://www.instagram.com/p/EXAMPLE1234/' --model-dir $model
& $cli summary --url 'https://www.instagram.com/p/EXAMPLE1234/' --model-dir $model
& $cli summary --result "$base\outputs\my-result.json"
```

`summary --result` requires neither models nor network access. Its exit code is 0 for saved success, 2 for partial, 65 for a saved error, 64 for an invalid result, or 69 for an unreadable file. It reports the content status; the original process exit code is not part of the saved content contract.

English is the default for generated extraction text, logs, diagnostics, errors, help, and documentation. Names and evidence quotations preserve their original language. Explicit `--output-language` or request `output_language` remains supported for extraction text; the CLI interface stays English. Local models can make language or interpretation mistakes.

## Backend protocol

Use `extract` for machine integration. Send one UTF-8 request JSON through stdin and close stdin:

```json
{
  "schema_version": "3.0.0",
  "request_id": "my_request_001",
  "url": "https://www.instagram.com/p/EXAMPLE1234/"
}
```

Invoke `content-extractor extract --request - --model-dir MODEL_DIR --log-format jsonl`. Alternatively use `--request FILE` or `--url URL`. Do not mix input modes. Requests without `output_language` default to `en`; callers requiring another language should set it explicitly.

- stdout: exactly one JSON object for `extract`, readable text for `summary`.
- stderr: operational logs, separate from the result.
- Exit codes: 0 success; 2 partial; 64 invalid input; 65 inaccessible/unprocessable content; 69 missing local capability; 70 internal/validation error; 75 timeout/resources/busy; 130 interruption.
- Research opportunities are informational. Required extraction gaps cause partial/error status.
- A forced process kill or native crash may prevent JSON delivery. The caller must detect missing or truncated output.

`examples/backend-client.mjs` implements a generic Node client using subprocess stdin/stdout/stderr with no shell or extraction logic. Its interface remains unchanged:

```text
node examples/backend-client.mjs CLI_EXE MODEL_DIR WORK_DIR URL OUTPUT_DIR
```

Python, .NET, or Java backends can use the same protocol. No HTTP backend, queue, database, or permanent application service is included. The consuming backend owns storage, concurrency, and subsequent research.

## Local processing

1. Retrieve an individual Instagram post or YouTube video anonymously. No personal cookies, login, downloader plugins, or browser session.
2. Inspect the author description first. If insufficient, transcribe audio using **faster-whisper medium CPU INT8/FP32**, six threads.
3. Apply generic evidence-backed patterns for explicit company application lists and author-presented tools/procedures. No hardcoded reel IDs or company answers.
4. Other formats/instructions can use preinstalled **Qwen2.5:3b locally**. A private temporary Ollama child runs on loopback, with cloud disabled and CPU configured; it stops on completion. No automatic model download. Validate quotations, names, URLs, and counts; abstain or retain a partial result when unsupported.
5. Optional local OCR reads images/on-screen labels. **No non-textual visual model is configured**; photos that require visual interpretation can return partial/error.
6. Return evidence, attribution, uncertainty, coverage, collections, and issues. No web research, identity verification, geocoding, or Maps generation. Only explicit location/link mentions may be preserved.

`follow_up.extraction_gaps` and `follow_up.research_opportunities` are separate. The consuming application decides whether to investigate anything later.

## Installation elsewhere

Requires Python 3.11+ and a virtual environment. From the repository root:

```text
python -m venv .venv
.venv/Scripts/python -m pip install ".[ocr]"
```

Provision separately before extracting:

- CTranslate2 model `Systran/faster-whisper-medium` with model.bin, config.json, tokenizer.json and vocabulary.txt. Tested revision: `08e178d48790749d25932bbc082711ddcfdfbc4f`. Set `--model-dir` or `CONTENT_EXTRACTOR_MODEL_DIR`.
- Ollama and `qwen2.5:3b` already installed locally. The CLI starts its private temporary runtime only when needed; no permanent Ollama server is required.
- Writable work directory via `--work-dir` or `CONTENT_EXTRACTOR_WORK_DIR`; otherwise an application-owned system temporary directory is used.

The medium directory must allow a sidecar `.content-extractor.lock`; weights are not changed. Invocations using the same model directory share a lock even if work directories differ. The caller manages its own queue. The package does not include model weights, the Python environment, or Ollama. Linux uses `.venv/bin/`; this release was verified on Windows, not certified on Linux.

## Limits and verification

Default deadline: 600 seconds. Input request limit: 64 KiB; saved summary input limit: 16 MiB. Media limits: five minutes, 250 MiB, twenty assets. OCR samples up to twenty-four video frames. Local text extraction has a context budget and rejects oversized text instead of silently truncating it.

The parent validates worker output, contains descendants in a Windows Job Object, cleans application-owned temporary jobs, and preserves validated partial checkpoints on later failures. Models and dependencies remain installed. Forced termination does not guarantee output delivery or forensic deletion.

Run application tests with `python -m unittest discover -s tests -v` and setup tests with `python -m unittest discover -s scripts -p "test_*.py" -v`. See [CI instructions](CI.md) for model-free checks. The readable summary formats the extraction result without a separate inference pass.
