# Model training on Molab notebooks

This tutorial explains how to run the training experiments on the Molab notebooks.

## Pre-requisites

- Create an account on https://molab.marimo.io/
- Generate the Github API token
- Generate the Hugging Face token
- (Optional) Request on discord the mlflow account

## Notebook preparation

First things first, open a new notebook in Molab.

Then, copy all your keys to the `.env.example` and upload that as `.env` to Molab notebook filesystem.

## Training launch

In a "Configure Resources" dropdown in the top panel, choose the GPU accelerator. At the moment (in the free trier) only the 'RTX Pro 6000' is available.

In a new cell put the following imports and a function:

```py
import marimo as mo
import os
from dotenv import load_dotenv

load_dotenv(".env") 

import subprocess

def run(cmd, **kwargs):
    print(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True, env=os.environ, **kwargs)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {cmd}")
    return result
```

Then, call the following set of commands:

```py
run("apt update && apt install -y git-lfs")
run("git lfs install")
run("rm -rf satyrn-models")
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
run(f"git clone https://${GITHUB_TOKEN}@github.com/satyrn-ai/satyrn-models.git")
run(f"cd satyrn-models && uv pip install --prerelease=allow --config-file uv.toml \
      --extra-index-url https://download.pytorch.org/whl/cu130 \
      --index-strategy unsafe-best-match \
      -e trainer/unsloth/")
run("uv python install 3.13 3.14 3.15")
run("hf download unsloth/Qwen3.8-27B")
```

This should prepare everything you need for the training run. You can launch the
training from the preconfigured settings.

```py
run("""
cd satyrn-models && uv run satyrn-unsloth --config-name experiment/py3.15-qwen3.8-27b datasets.cpt=null max_steps=20 sft.batch_size=48
""")
```

## Extras

Note that Molab files manipulation UI is quite tricky. You may then want to clone your own fork instead:

```py
run(f"git clone https://${GITHUB_TOKEN}@github.com/<your-gh-login>/satyrn-models.git")
```

and work of the branch with a new config. Alternatively, you can also edit the files via the Molab terminal,
which you can open by toggling the developer panel at the very left bottom.
