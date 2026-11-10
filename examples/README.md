# Examples

Complete synthetic results illustrate the public contract:

- [Successful tool walkthrough](success.json): a tool and three steps extracted from author text.
- [Partial recommendation list](partial.json): useful items preserved with required gaps.
- [Access error](error.json): an unavailable publication without fabricated items.

The example publication URLs and authors are fictional. They demonstrate the schema, not a real Instagram request.

The [Node client](backend-client.mjs) invokes the CLI as a subprocess, sends one request JSON, and reads the result and diagnostics separately:

```text
node examples/backend-client.mjs CLI_EXE MODEL_DIR WORK_DIR URL OUTPUT_DIR
```

See the [CLI reference](../docs/CLI.md) for request fields and exit codes.
