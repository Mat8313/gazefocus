"""Réglages utilisateur, sauvegardés dans %APPDATA%\\gazefocus\\config.json."""
import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .decision import Settings

DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "gazefocus"
CONFIG_PATH = DATA_DIR / "config.json"
# Sur un même écran, les fenêtres sont proches : on exige un regard plus posé.
WINDOW_MIN_DWELL = 0.6


@dataclass
class Config:
    camera: int = 0
    dwell: float = 0.3
    mouse_cooldown: float = 1.5
    typing_cooldown: float = 3.0
    learn_from_clicks: bool = True
    move_cursor: bool = False
    use_eyes: bool = False
    same_screen: bool = False

    def switching(self, min_dwell: float = 0.0) -> Settings:
        return Settings(max(self.dwell, min_dwell), self.mouse_cooldown, self.typing_cooldown)


def load() -> Config:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config()
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})


def save(config: Config):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
