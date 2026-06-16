from datetime import datetime
from pathlib import Path

import pandas as pd

from storage import (
    SETTINGS_COLUMNS,
    StorageError,
    remote_user_settings,
    supabase_configured,
    upsert_remote_user_settings,
)


APP_DIR = Path(__file__).parent
SETTINGS_PATH = APP_DIR / "user_settings.csv"
DEFAULT_SETTINGS = {
    "level_preset": "600だけ",
    "manual_levels": "",
}


def load_local_settings() -> pd.DataFrame:
    if SETTINGS_PATH.exists():
        settings = pd.read_csv(SETTINGS_PATH)
        for col in SETTINGS_COLUMNS:
            if col not in settings.columns:
                settings[col] = ""
        return settings[SETTINGS_COLUMNS]
    return pd.DataFrame(columns=SETTINGS_COLUMNS)


def save_local_settings(settings: pd.DataFrame):
    tmp_path = SETTINGS_PATH.with_suffix(".tmp")
    settings[SETTINGS_COLUMNS].to_csv(tmp_path, index=False)
    tmp_path.replace(SETTINGS_PATH)


def load_user_settings(user_id: str) -> dict:
    row = None
    if supabase_configured():
        try:
            remote = remote_user_settings(user_id)
            if not remote.empty:
                row = remote.iloc[0].to_dict()
        except StorageError:
            row = None

    if row is None:
        local = load_local_settings()
        matched = local[local["user_id"].astype(str).eq(user_id)]
        if not matched.empty:
            row = matched.iloc[0].to_dict()

    settings = DEFAULT_SETTINGS.copy()
    if row:
        settings["level_preset"] = str(row.get("level_preset") or settings["level_preset"])
        settings["manual_levels"] = str(row.get("manual_levels") or "")
    return settings


def save_user_settings(user_id: str, level_preset: str, manual_levels: list[str]):
    row = {
        "user_id": user_id,
        "level_preset": level_preset,
        "manual_levels": ",".join(manual_levels),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    saved_remote = False
    if supabase_configured():
        try:
            upsert_remote_user_settings(row)
            saved_remote = True
        except StorageError:
            saved_remote = False

    if not saved_remote:
        settings = load_local_settings()
        settings = settings[~settings["user_id"].astype(str).eq(user_id)]
        save_local_settings(pd.concat([settings, pd.DataFrame([row])], ignore_index=True))
