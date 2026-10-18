import json, os

def load(path=None):
    """Load config.json. Every tunable number lives there; nothing is hard-coded."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    with open(path) as f:
        return json.load(f)
