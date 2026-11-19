---
name: mlflow-web
description: Query the MLflow REST API read-only, download run artifacts such as train.log and evals.zip with curl, and build MLflow chart links.
---

# Satyrn MLflow runs, metrics, and artifacts (read-only REST API)

All queries use `https://mlflow.satyrn.ai` with `source .env` first (`MLFLOW_READONLY_USERNAME` / `MLFLOW_READONLY_PASSWORD`).

If a query fails authentication, check whether `MLFLOW_READONLY_PASSWORD` is empty. If it is, ask the user for the read-only `SatyrnAI` credentials (for example: "`MLFLOW_READONLY_PASSWORD` is not set in `.env`. Please provide the password for the read-only `SatyrnAI` MLflow account (you can request it on the [Satyrn Discord](https://discord.gg/WeBCemTj5)).").

## Example questions

All queries print JSON. A training job is a parent run; its stages (`cpt`, `sft`, `rl`) are child runs with the tag `mlflow.parentRunId`. Stage settings are params of the child run, not of the parent.

List experiments (`experiment_id` and `name`) or runs in an experiment:

```bash
source .env
curl -fsS -u "$MLFLOW_READONLY_USERNAME:$MLFLOW_READONLY_PASSWORD" -H 'Content-Type: application/json' -d '{"max_results": 50}' https://mlflow.satyrn.ai/api/2.0/mlflow/experiments/search
curl -fsS -u "$MLFLOW_READONLY_USERNAME:$MLFLOW_READONLY_PASSWORD" -H 'Content-Type: application/json' -d '{"experiment_ids": ["EXPERIMENT_ID"], "max_results": 20}' https://mlflow.satyrn.ai/api/2.0/mlflow/runs/search
```

### Did two runs use the same dataset files and number of rows?

List the stage runs of each parent, then read `data.params` of the stage you care about:

```bash
curl -fsS -u "$MLFLOW_READONLY_USERNAME:$MLFLOW_READONLY_PASSWORD" -H 'Content-Type: application/json' \
  -d '{"experiment_ids": ["EXPERIMENT_ID"], "filter": "tags.`mlflow.parentRunId` = '"'"'PARENT_RUN_ID'"'"'"}' \
  https://mlflow.satyrn.ai/api/2.0/mlflow/runs/search
```

Compare `dataset_path` and `dataset_train_rows`.

Runs without these params have the file names in `train.log` on the parent run. Search it for `datasets/.*\.jsonl`.

### What were the PythonEval and HumanEval scores of a run?

They are metric histories on the parent run, one point per eval:

```bash
curl -fsS -u "$MLFLOW_READONLY_USERNAME:$MLFLOW_READONLY_PASSWORD" \
  "https://mlflow.satyrn.ai/api/2.0/mlflow/metrics/get-history?run_id=PARENT_RUN_ID&metric_key=python_eval_verify_accuracy"
```

Use `humaneval_verify_accuracy` for HumanEval. Sort the points by `timestamp`. The first is before training, then one follows each stage that ran. Match them to stages by comparing with the stage runs' `end_time`.

### How do the curves of a metric compare between runs?

Give the user a link to a chart with the runs on it. Do not describe curves in words. Build the link for any metric of any runs you want to talk about:

```
https://mlflow.satyrn.ai/#/metric?runs=[%22RUN_ID_1%22,%22RUN_ID_2%22]&metric=%22METRIC%22&experiments=[%22EXPERIMENT_ID%22]&plot_metric_keys=%5B%22METRIC%22%5D&plot_layout={}&x_axis=step&y_axis_scale=linear&line_smoothness=1&show_point=false&deselected_curves=[]&last_linear_y_axis_range=[]
```

Training metrics (`reward`, `loss`, `eval_loss`, `completions/clipped_ratio`) are logged on the stage runs, not on the parent run. Use the full run IDs of the stage runs, found with the `runs/search` query above. `METRIC` appears twice, once in `metric` and once in `plot_metric_keys`.

After building the link, check that the latest values on the chart match the values you quote.

## Download a run artifact

`RUN_ID` is the full run UUID:

```bash
curl -fsS -u "$MLFLOW_READONLY_USERNAME:$MLFLOW_READONLY_PASSWORD" \
  -o train.log "https://mlflow.satyrn.ai/get-artifact?path=train.log&run_uuid=$RUN_ID"
```

### Inspecting `evals.zip`

`evals.zip` (on the parent run) contains one `.eval` archive per benchmark (`humaneval`, `python-eval`). Unzip it and load each `.eval` with `inspect_ai.log.read_eval_log(path)` (Python's `zipfile` fails on zstd compression). On each `sample` in `log.samples`:
- `sample.scores`: score (`value`), extracted code (`answer`), and failure output (`explanation`).
- `sample.output.choices[0].message.content`: `list` of `ContentReasoning`/`ContentText` or `str`; `sample.output.usage.output_tokens` has token counts.

## Reference docs

For endpoints, parameters, or `filter` syntax beyond the examples above, download the [MLflow REST API reference](https://mlflow.org/docs/latest/api_reference/rest-api.html) once to a temporary or scratch file and extract only the section you need (any equivalent approach works):

```bash
# List available endpoints
grep -o '2\.0/mlflow/[a-z0-9/_-]*' <file> | sort -u

# Extract one endpoint section (stops at the next endpoint's <h2>)
awk '/2\.0\/mlflow\/runs\/search/{found=1} found && /<h2>/{exit} found' <file> | sed 's/<[^>]*>//g' | grep -v '^[[:space:]]*$'
```
