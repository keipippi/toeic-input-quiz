import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


APP_DIR = Path(__file__).parent
REVIEW_STEPS = [1, 3, 7, 14, 30]


def safe_user_id(name: str) -> str:
    name = unicodedata.normalize("NFKC", str(name)).strip()
    name = re.sub(r"[^0-9A-Za-zぁ-んァ-ン一-龥_-]+", "_", name)
    return name[:40] if name else "guest"


def history_path(user_name: str) -> Path:
    return APP_DIR / f"history_{safe_user_id(user_name)}.csv"


def load_history(user_name: str) -> pd.DataFrame:
    cols = ["timestamp", "user", "word", "direction", "user_answer", "result", "mode", "reason", "next_review"]
    path = history_path(user_name)
    if path.exists():
        df = pd.read_csv(path)
        for c in cols:
            if c not in df.columns:
                df[c] = user_name if c == "user" else ""
        return df[cols]
    return pd.DataFrame(columns=cols)


def next_review_date(word: str, result: str, history: pd.DataFrame) -> str:
    today = datetime.now().date()
    if result == "wrong":
        return str(today + timedelta(days=1))
    if result == "almost":
        return str(today + timedelta(days=3))
    correct_count = len(history[(history["word"] == word) & (history["result"] == "correct")])
    days = REVIEW_STEPS[min(correct_count, len(REVIEW_STEPS) - 1)]
    return str(today + timedelta(days=days))


def save_history(user_name, word, direction, user_answer, result, mode, reason, history):
    row = pd.DataFrame([{
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user_name,
        "word": word,
        "direction": direction,
        "user_answer": user_answer,
        "result": result,
        "mode": mode,
        "reason": reason,
        "next_review": next_review_date(word, result, history),
    }])
    pd.concat([history, row], ignore_index=True).to_csv(history_path(user_name), index=False)
