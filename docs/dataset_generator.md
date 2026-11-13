# Dataset generation

Use the `corpus_builder` package to generate fine-tuning datasets.

## Install

Install the `satyrn-dataset` command into your environment from the `corpus_builder` package.

Activate a Python virtual environment and install the package. Use an editable install (`-e`) 
if you plan to change the `corpus_builder` code, so edits take effect without reinstalling:

```sh
$ source /path/to/venv/bin/activate
(venv) $ pip install -e ./corpus_builder
```

## Collecting input material

Before generating a dataset, gather the source documents it draws from.

### Gather Python Enhancement Proposals (PEPs)

Download the PEPs for a Python version into `datasets/python3.15/input/docs/`

```sh
satyrn-dataset download-inputs 3.15
```

### Gather recent changes in CPython Docs

To collect and download the documentation changes for CPython, perform the following steps.

Clone CPython into any path on your system:

```sh
git clone --depth 1 https://github.com/python/cpython.git /path/to/cpython
```

Collect the documentation sections tied to changes in a Python version. Make sure that you use `Doc` 
directory of the CPython repo as the input:

```sh
satyrn-dataset collect-doc-changes 3.15 /path/to/cpython/Doc
```

Writes to `datasets/python3.15/input/docs/changes/`.

## Generating datasets

Each subcommand writes JSONL to the `--output` file.
`cpt` reads source material from `--input-dir`, the directory that
[Collecting input material](#collecting-input-material) writes to.

`sft`, `rl` and `agentic-sft` datasets are generated in two stages. `ideas` reads source material from
`--input` (a directory or a single doc file) and writes a JSONL file of ideas. The dataset generating
command then reads those ideas from `--ideas-path`. An ideas file can be reused for several runs of
its command, but ideas of a specific `kind` are best suited for a particular generator command.

```sh
satyrn-dataset cpt   --input-dir DIR --output FILE.jsonl                    # Continued Pretraining (CPT)

satyrn-dataset ideas --kind sft --input PATH --output SFT-IDEAS.jsonl       # Ideas for SFT
satyrn-dataset sft   --ideas-path SFT-IDEAS.jsonl --output FILE.jsonl       # Supervised Fine-Tuning (SFT)

satyrn-dataset ideas --kind rl --input PATH --output RL-IDEAS.jsonl         # Ideas for RL
satyrn-dataset rl    --ideas-path RL-IDEAS.jsonl --output FILE.jsonl        # Evaluation / Reinforcement Learning (RL)

satyrn-dataset ideas --kind agentic-sft --input PATH --output AGENTIC-IDEAS.jsonl   # Ideas for agentic SFT
satyrn-dataset agentic-sft --ideas-path AGENTIC-IDEAS.jsonl --output FILE.jsonl     # Agentic multi-turn SFT
```

> [!NOTE]
> All generators currently use an LLM via the DeepSeek API. A `DEEPSEEK_API_KEY` is required in your environment (or a `.env` file - see `.env.example`).
>
> Optionally set `LLM_MODEL_NAME` to choose the model (default `deepseek-v4-flash`) and `DEEPSEEK_BASE_URL` to use a different DeepSeek-compatible endpoint (default `https://api.deepseek.com`).

### Generate Continued Pretraining (CPT) datasets

`cpt` converts every `.rst` file under `input-dir` to Markdown and writes one row per file to
`--output`.

Usage example:

```sh
satyrn-dataset cpt --input-dir datasets/python3.14/input/docs --output datasets/python3.14/cpt.jsonl
satyrn-dataset cpt --input-dir datasets/python3.15/input/docs --output datasets/python3.15/cpt.jsonl
```

### Generate ideas

`ideas` asks an LLM to propose up to 50 distinct ideas for each source document, shaped by `--kind`.
Each row of `--output` holds one idea:

- `description`: what the example or task should demonstrate;
- `python_version`: the target Python version;
- `kind`: `sft`, `rl` or `agentic-sft`
- `doc_path`: the absolute path of the source document the idea came from.

> [!IMPORTANT]
> Because `doc_path` is absolute and the dataset generating command re-reads the source document,
> keep the source documents in place, and generate ideas on the same machine (or with the same
> paths) that will run it.

Pass `--preview` to print each document's ideas as they are saved, and `--workers` to process
several source documents in parallel (defaults to 1).

Generate ideas for a single PEP with preview:

```sh
satyrn-dataset ideas -i datasets/python3.14/input/docs/PEP750.rst -o datasets/python3.14/ideas-sft.jsonl --python-version 3.14 --kind sft --preview
```

Generate ideas across all downloaded documents, 8 documents at a time:

```sh
satyrn-dataset ideas -i datasets/python3.15/input/docs -o datasets/python3.15/ideas-sft.jsonl --python-version 3.15 --kind sft --workers 8
satyrn-dataset ideas -i datasets/python3.15/input/docs -o datasets/python3.15/ideas-rl.jsonl --python-version 3.15 --kind rl --workers 8
```

### Generate Supervised Fine-Tuning (SFT) datasets

`sft` uses an LLM to turn each idea from an [ideas file](#generate-ideas) into a prompt-response
pair demonstrating a new Python feature, using the idea's source document as context.

Each idea is verified by running in sandboxed Docker containers for the target Python version and
its immediate predecessor. Examples are rejected if both versions produce equivalent output.

Docker is _required_, gVisor (`runsc` runtime) is _recommended_ for sandbox safety. You can verify if both are set 
up in your environment:

```sh
docker run --rm hello-world
docker run --rm --runtime=runsc hello-world
```

Output is written one row per conversation to `--output`, appending as it goes so partial progress
survives an interruption.

#### Usage

Pass `--preview` to print each generated conversation to the terminal as it's saved, useful for
sanity-checking output quality while a run is in progress.

Generating examples from an ideas file with preview:

```sh
satyrn-dataset sft -i datasets/python3.14/ideas-sft.jsonl -o datasets/python3.14/sft.jsonl --python-version 3.14 --preview
```

Pass `--workers` to generate several conversations (one per idea) in parallel. Defaults to 1.

Generating examples 24 at a time:

```sh
satyrn-dataset sft -i datasets/python3.15/ideas-sft.jsonl -o datasets/python3.15/sft.jsonl --python-version 3.15 --workers 24
```

### Generate Agentic SFT datasets

`agentic-sft` records a coding agent working on a task over several tool-calling turns. For each
idea, an LLM writes a task: an initial code file, a user prompt, an expected solution and tests.

An agent then runs inside Pi in a Docker container, completing the task.
The generated solution is verified using the task's tests.

This agentic session, with all issued tool calls, is recorded as a single dataset entry.

Choose the Pi model with `--agent-model`: `deepseek/deepseek-flash` (default) or
`deepseek/deepseek-v4-pro`.

```sh
satyrn-dataset agentic-sft -i datasets/python3.14/ideas-agentic-sft.jsonl -o datasets/python3.14/agentic-sft.jsonl --python-version 3.14 --preview
```

### Generate evaluation and Reinforcement Learning datasets

`rl` turns each idea from an [ideas file](#generate-ideas) into a small callable programming task,
using the idea's source document as context. Each JSONL row contains:

- `prompt`: a self-contained problem and callable signature;
- `test_cases`: 5-12 independent checks, each with a documented input, expected output, and executable assertion;
- `solution`: a reference implementation used to verify the tests; and
- `metadata`: the source document, normalized PEP identifier when applicable, Python version,
  originating idea, entry point, and test count.

The reference solution must pass every test under the target Python version. The same solution and
suite are then run under the immediately preceding version, and the row is rejected if all tests
still pass there. A candidate model response can be scored by running every test independently and
using `passed_tests / total_tests`, producing a score between 0 and 1.

Docker has the same requirements as for `sft`. Generate from an ideas file with preview:

```sh
satyrn-dataset rl -i datasets/python3.15/ideas-rl.jsonl -o datasets/python3.15/rl.jsonl --python-version 3.15 --preview
```

Generate with parallel workers (one task per idea at a time):

```sh
satyrn-dataset rl -i datasets/python3.15/ideas-rl.jsonl -o datasets/python3.15/rl.jsonl --python-version 3.15 --workers 24
```

## Viewing datasets

`viewer` lets you read a dataset in the browser as chat sessions between a user and an LLM agent,
including tool calls. Use it to review the datasets you generate.

### Build the frontend

The viewer UI is a TypeScript app in `corpus_builder/frontend`. Its built bundle is not checked in,
so build it once (and again after pulling frontend changes). Node.js and npm are required:

```sh
cd corpus_builder/frontend
npm install
npm run build
```

This writes the bundle to `corpus_builder/src/satyrn/dataset/viewer/static/`, where the
`satyrn-dataset` package serves it from. If you skip this step, the viewer responds with a
"Frontend not built" page.

### Run the viewer

```sh
satyrn-dataset viewer datasets/python3.15/rl.jsonl
```

Then open <http://127.0.0.1:5000/>. Options:

- `--port PORT`: port to listen on (default `5000`);
- `--host HOST`: interface to bind to (default `127.0.0.1`; use `0.0.0.0` to reach it from another machine);
- `--debug`: enable the Flask debug reloader.

The dataset is read once at startup, so restart the viewer to see rows added after it started.

For frontend development with hot reloading, see `corpus_builder/frontend/README.md`.
