import base64
import hashlib
import hmac
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from history import safe_user_id
from storage import insert_remote_user, remote_user, remote_users, supabase_configured


APP_DIR = Path(__file__).parent
USERS_PATH = APP_DIR / "users.csv"
USER_COLUMNS = ["user_id", "display_name", "salt", "pin_hash", "created_at"]


def load_users() -> pd.DataFrame:
    if supabase_configured():
        return remote_users()
    if USERS_PATH.exists():
        users = pd.read_csv(USERS_PATH)
        for col in USER_COLUMNS:
            if col not in users.columns:
                users[col] = ""
        return users[USER_COLUMNS]
    return pd.DataFrame(columns=USER_COLUMNS)


def save_users(users: pd.DataFrame):
    tmp_path = USERS_PATH.with_suffix(".tmp")
    users[USER_COLUMNS].to_csv(tmp_path, index=False)
    tmp_path.replace(USERS_PATH)


def hash_pin(pin: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", str(pin).encode("utf-8"), salt.encode("utf-8"), 120_000)
    return base64.b64encode(digest).decode("ascii")


def new_salt() -> str:
    return base64.b64encode(os.urandom(16)).decode("ascii")


def user_exists(user_name: str) -> bool:
    user_id = safe_user_id(user_name)
    users = load_users()
    return user_id in set(users["user_id"].astype(str))


def create_user(user_name: str, pin: str) -> tuple[bool, str, str]:
    user_id = safe_user_id(user_name)
    if len(str(pin)) < 4:
        return False, user_id, "PINは4文字以上にしてください。"
    users = load_users()
    if user_id in set(users["user_id"].astype(str)):
        return False, user_id, "このユーザー名はすでに登録されています。"
    salt = new_salt()
    row = {
        "user_id": user_id,
        "display_name": str(user_name).strip(),
        "salt": salt,
        "pin_hash": hash_pin(pin, salt),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if supabase_configured():
        insert_remote_user(row)
    else:
        save_users(pd.concat([users, pd.DataFrame([row])], ignore_index=True))
    return True, user_id, "登録しました。"


def verify_user(user_name: str, pin: str) -> tuple[bool, str, str]:
    user_id = safe_user_id(user_name)
    if supabase_configured():
        matched = remote_user(user_id)
    else:
        users = load_users()
        matched = users[users["user_id"].astype(str).eq(user_id)]
    if matched.empty:
        return False, user_id, "ユーザーが見つかりません。先に新規登録してください。"
    user = matched.iloc[0]
    expected = str(user["pin_hash"])
    actual = hash_pin(pin, str(user["salt"]))
    if not hmac.compare_digest(actual, expected):
        return False, user_id, "PINが違います。"
    return True, user_id, "ログインしました。"
