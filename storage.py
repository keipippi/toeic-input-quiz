import os

import pandas as pd
import requests


USER_COLUMNS = ["user_id", "display_name", "salt", "pin_hash", "created_at"]
HISTORY_COLUMNS = ["timestamp", "user", "word", "direction", "user_answer", "result", "mode", "reason", "next_review"]
USERS_TABLE = "toeic_users"
HISTORY_TABLE = "toeic_history"


class StorageError(RuntimeError):
    pass


def get_setting(name: str) -> str:
    value = os.environ.get(name, "")
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, ""))
    except Exception:
        return ""


def supabase_configured() -> bool:
    return bool(get_setting("SUPABASE_URL") and get_setting("SUPABASE_KEY"))


def storage_label() -> str:
    return "Supabase" if supabase_configured() else "CSV"


def supabase_request(method: str, table: str, params=None, json=None):
    url = get_setting("SUPABASE_URL").rstrip("/") + f"/rest/v1/{table}"
    key = get_setting("SUPABASE_KEY")
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    try:
        response = requests.request(method, url, headers=headers, params=params, json=json, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        detail = ""
        response = getattr(exc, "response", None)
        if response is not None:
            detail = f" ({response.status_code}: {response.text[:200]})"
        raise StorageError(f"Supabaseへの接続に失敗しました{detail}") from exc
    if response.text:
        return response.json()
    return []


def remote_users() -> pd.DataFrame:
    rows = supabase_request("GET", USERS_TABLE, params={"select": ",".join(USER_COLUMNS), "order": "created_at.asc"})
    return pd.DataFrame(rows, columns=USER_COLUMNS)


def remote_user(user_id: str) -> pd.DataFrame:
    rows = supabase_request(
        "GET",
        USERS_TABLE,
        params={"select": ",".join(USER_COLUMNS), "user_id": f"eq.{user_id}", "limit": "1"},
    )
    return pd.DataFrame(rows, columns=USER_COLUMNS)


def insert_remote_user(row: dict):
    supabase_request("POST", USERS_TABLE, json=row)


def remote_history(user_name: str) -> pd.DataFrame:
    rows = supabase_request(
        "GET",
        HISTORY_TABLE,
        params={"select": ",".join(HISTORY_COLUMNS), "user": f"eq.{user_name}", "order": "timestamp.asc"},
    )
    return pd.DataFrame(rows, columns=HISTORY_COLUMNS)


def append_remote_history(row: dict):
    supabase_request("POST", HISTORY_TABLE, json=row)


def delete_remote_history(user_name: str):
    supabase_request("DELETE", HISTORY_TABLE, params={"user": f"eq.{user_name}"})
