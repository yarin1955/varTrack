import json
import os
from pathlib import Path

def load_config()-> dict:
    path = Path("config.json")
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open() as f:
        cfg = json.load(f)

    return cfg