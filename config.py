import json
import os

CONFIG_FILE = "config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError("Config file not found. Please create config.json")
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)
