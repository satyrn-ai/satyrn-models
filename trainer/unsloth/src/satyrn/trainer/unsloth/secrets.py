"""Loads required secrets from the environment (optionally via a .env file)."""

import os

from dotenv import load_dotenv


def load_secrets() -> None:
    load_dotenv()
    assert os.environ.get("HF_TOKEN"), "HF_TOKEN environment variable is not set"
    assert os.environ.get("HF_USERNAME"), "HF_USERNAME environment variable is not set"
    assert os.environ.get("MLFLOW_TRACKING_USERNAME"), "MLFLOW_TRACKING_USERNAME environment variable is not set"
    assert os.environ.get("MLFLOW_TRACKING_PASSWORD"), "MLFLOW_TRACKING_PASSWORD environment variable is not set"
