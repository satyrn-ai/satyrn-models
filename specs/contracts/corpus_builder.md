# Corpus-builder Contract

## Package and entry point

The `satyrn-corpus-builder` distribution provides the `satyrn-dataset` CLI.

Invoking `sft` or `rl` through the command group adds a Python logging handler
at `results/YYYYMMDD-HHMM-corpus-builder-{command}/run.log`. It does not capture
all terminal output.

## Source collection

### `download-inputs TARGET_VERSION`

- `TARGET_VERSION` is `3.14` or `3.15`.
- The command downloads its source-owned list of PEP and `whatsnew` files from
  GitHub `main` URLs.
- It writes fixed filenames below
  `datasets/python{version}/input/docs/`, overwriting matching files.
- Download failures propagate and can leave a partially refreshed directory.

### `collect-doc-changes TARGET_VERSION DOC_DIRECTORY`

- `DOC_DIRECTORY` must be an existing CPython `Doc/` tree containing
  `conf.py`.
- The command parses the Sphinx tree and selects sections tied to
  `TARGET_VERSION`.
- It reuses `${TMPDIR}/satyrn-cpython-sphinx-cache` and writes below
  `datasets/python{version}/input/docs/changes/`.
- Matching output files are overwritten; stale files that are no longer
  produced are not removed.
- Sphinx, parsing, and filesystem failures propagate. Partial output can
  remain.

## CPT generation

```sh
satyrn-dataset cpt --input-dir DIR --output FILE.jsonl
```

`DIR` must be a directory containing at least one recursively discovered
`.rst` file. The command renders the sorted source tree through Sphinx, using
the first source document as the root, and overwrites the output only after
rendering succeeds. The output path must end in `.jsonl`; missing parent
directories are created.

Rows are sorted by rendered path and have this shape:

```json
{"filename": "relative/source/path.rst", "text": "rendered Markdown"}
```

## SFT generation

```sh
satyrn-dataset sft --input PATH --output FILE.jsonl \
  --python-version VERSION [--preview] [--workers N]
```

- `PATH` must exist. A directory contributes recursively sorted `.rst` files;
  a single file is accepted regardless of suffix.
- `VERSION` is required but is not limited to the versions supported by
  `download-inputs`.
- `N` is an integer of at least 1 and defaults to 1.
- The provider and model are fixed in source. `DEEPSEEK_API_KEY` is read from
  the environment or `.env`.
- The output must end in `.jsonl`. If it exists, the command asks whether to
  clear it; declining appends to it.
- Accepted rows are appended immediately. An interrupted run preserves rows
  already written.
- `--preview` prints proposed ideas and each accepted row after persistence.

Each source document prompts the model for zero to fifty proposed ideas. The
response schema does not enforce that maximum, so a conforming response can
contain more. For each idea the pipeline generates code, a reasoning trace, and
predicted output; executes the code; judges mismatches; produces a conversation;
and judges that conversation. Accepted rows have this shape:

```json
{
  "prompt": [{"role": "user", "content": "..."}],
  "completion": [{"role": "assistant", "content": "..."}],
  "filename": "source-file.rst",
  "python_version": "3.15",
  "idea": "...",
  "code": "...",
  "trace": "...",
  "expected_output": "..."
}
```

### Concurrency and ordering

Workers are divided between document and idea pools. Both pools consume work
as it completes. A process-local lock prevents JSON lines from interleaving,
but row order is completion order and is nondeterministic across documents and
ideas.

### Generated-code execution

Docker must be installed and running. The command selects
`python:{VERSION}-slim`, then `python:{VERSION}-rc-slim`, from Docker Hub and
pulls the selected image when necessary.

When Docker reports the `runsc` runtime, the container uses gVisor. Otherwise
the command warns and continues with ordinary Docker. In both cases it disables
networking, limits memory/CPU/processes, drops capabilities, prevents privilege
gain, runs as user and group `65534`, mounts a read-only root filesystem, and
provides a `noexec,nosuid,nodev` temporary filesystem.

Execution is limited to 10 seconds. Standard output and error are combined and
truncated after 12,000 characters. Timeout is returned as output. Container
exit status is not checked; verification compares stripped combined output to
the stripped prediction. A judge may accept an incidental mismatch and replace
the prediction with actual output.

### Failure behavior

- Schema-invalid model output is attempted up to three times per model call.
- Code generation is attempted up to three times when verification fails.
- Code rejection, conversation rejection, and most exceptions within one idea
  are logged and skipped. The output contains no aggregate rejection report.
- Document-level idea generation and global input, Docker-availability,
  image-tag lookup, and output failures abort the command.
- Image-pull and container-run exit statuses are not checked. Their output can
  therefore enter code verification and be retried or skipped per idea instead
  of aborting globally.
- Rows written before an abort remain in the output.

## RL generation

```sh
satyrn-dataset rl --input PATH --output FILE.jsonl
```

The command validates the input and `.jsonl` suffix, prints the intended
paths, and then fails with `satyrn-dataset rl is not yet implemented`.

See [known limitations](../known_limitations.md) for current contract and
fail-fast exceptions.
