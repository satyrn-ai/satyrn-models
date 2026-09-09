"""How a code problem is framed for the model, shared by the eval scorer and RL."""

INSTRUCTION = """
Write the function described below. Your response should only contain the code
for this function and any imports it needs.\n
"""


def to_chat_prompt(row: dict) -> dict:
    """Replace a raw RL prompt string with a single-turn user message list."""
    return {"prompt": [{"role": "user", "content": INSTRUCTION + row["prompt"]}]}
