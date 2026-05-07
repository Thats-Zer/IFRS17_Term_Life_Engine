import json

from anyio import Path 
from models.config_model import ConfigModel

def loadconfig(config_path: str = "config/config.json") -> ConfigModel:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found at {config_path}")
     with open(path, "r", encoding="utf-8") as file:
        raw_config = json.load(file)
    return ConfigModel(**raw_config)