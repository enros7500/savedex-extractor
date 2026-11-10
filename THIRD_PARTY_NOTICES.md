# Third-party components and content

The root MIT license covers the project's original code and original documentation. It does not relicense third-party software, model weights, publication text, or other material quoted as extraction evidence.

## Software dependencies

Python dependencies retain their own licenses. The package metadata declares runtime dependencies; `requirements-ci.txt` declares the smaller unit-test environment. No third-party source tree is vendored into this repository.

## Models

Model weights are downloaded separately and excluded from Git. Review their upstream terms for your intended use:

- [Whisper medium conversion](https://huggingface.co/Systran/faster-whisper-medium) and [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
- [Qwen2.5 3B on Ollama](https://ollama.com/library/qwen2.5:3b). The 3B model has upstream Qwen-specific licensing; this repository's MIT license does not apply to it.
- [RapidOCR](https://github.com/RapidAI/RapidOCR) and the ONNX OCR models supplied with its dependency.

Installing or downloading a model does not make its license the same as the CLI's license.

## Examples and publication content

Illustrative JSON examples use fictional content. Test fixtures may include attributed excerpts to verify output formatting. Quoted publication content remains attributable to its original author; the project's MIT license does not relicense it.
