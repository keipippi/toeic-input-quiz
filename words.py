import re
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).parent
WORDS_PATH = APP_DIR / "words.csv"
REQUIRED_COLUMNS = ["word", "meaning", "accepted_answers", "example", "note", "level", "pos", "example_ja", "ipa"]
LEVEL_ORDER = ["600", "700", "800"]
LEVEL_PRESETS = {
    "600だけ": ["600"],
    "600+700": ["600", "700"],
    "全部": ["600", "700", "800"],
    "手動で選ぶ": [],
}


def normalize_level(value) -> str:
    s = str(value).strip()
    if s in ["600", "600点", "TOEIC600"]:
        return "600"
    if s in ["700", "730", "730-860", "730〜860", "730–860", "TOEIC730"]:
        return "700"
    if s in ["800", "860", "860+", "900", "900+", "TOEIC860"]:
        return "800"
    try:
        n = int(float(s))
        if n < 700:
            return "600"
        if n < 800:
            return "700"
        return "800"
    except Exception:
        return "600"


def split_answers(text: str) -> list[str]:
    if pd.isna(text):
        return []
    return [p.strip() for p in re.split(r"[、，,／/;；|｜]", str(text)) if p.strip()]


def clean_accepted_answers(meaning: str, accepted_answers: str) -> str:
    meaning_key = normalize_word_key(meaning)
    cleaned = []
    seen = set()
    for answer in split_answers(accepted_answers):
        key = normalize_word_key(answer)
        if key == meaning_key or key in seen:
            continue
        seen.add(key)
        cleaned.append(answer)
    return "／".join(cleaned)


def prepare_words(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["level"] = df["level"].apply(normalize_level)
    df = df[REQUIRED_COLUMNS]
    df = df.dropna(subset=["word", "meaning"])
    df["word"] = df["word"].astype(str).str.strip()
    df["accepted_answers"] = df.apply(lambda row: clean_accepted_answers(row["meaning"], row["accepted_answers"]), axis=1)
    return df[df["word"] != ""]


def normalize_word_key(word: str) -> str:
    return unicodedata.normalize("NFKC", str(word)).strip().lower()


def clean_form_value(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip()


def validate_new_word(row: dict, existing_df: pd.DataFrame) -> list[str]:
    errors = []
    required = {
        "word": "英単語",
        "meaning": "意味",
        "accepted_answers": "許容表現",
        "example": "例文",
        "pos": "品詞",
        "example_ja": "例文の日本語訳",
    }
    for key, label_text in required.items():
        if not row.get(key):
            errors.append(f"{label_text}を入力してください。")
    existing_keys = set(existing_df["word"].astype(str).map(normalize_word_key))
    if normalize_word_key(row.get("word", "")) in existing_keys:
        errors.append("同じ英単語がすでに登録されています。")
    return errors


def append_word_to_csv(row: dict):
    current = pd.read_csv(WORDS_PATH)
    for col in REQUIRED_COLUMNS:
        if col not in current.columns:
            current[col] = ""
    next_df = pd.concat([current[REQUIRED_COLUMNS], pd.DataFrame([row], columns=REQUIRED_COLUMNS)], ignore_index=True)
    next_df.to_csv(WORDS_PATH, index=False)
    load_base_words.clear()


def quality_report(words_df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    report_df = words_df.copy()
    report_df["word_key"] = report_df["word"].astype(str).map(normalize_word_key)
    issues = []
    optional_columns = {"ipa", "note"}
    for index, row in report_df.iterrows():
        word = str(row["word"])
        for col in REQUIRED_COLUMNS:
            if col in optional_columns:
                continue
            value = row.get(col, "")
            if pd.isna(value) or str(value).strip() == "":
                issues.append({"word": word, "issue": f"{col} が空欄です", "row": index + 2})
        if str(row.get("level", "")) not in LEVEL_ORDER:
            issues.append({"word": word, "issue": "level が 600 / 700 / 800 以外です", "row": index + 2})
        if len(split_answers(row.get("accepted_answers", ""))) == 0:
            issues.append({"word": word, "issue": "accepted_answers が分割できません", "row": index + 2})

    duplicated = report_df[report_df["word_key"].duplicated(keep=False)].sort_values("word_key")
    for _, row in duplicated.iterrows():
        issues.append({"word": row["word"], "issue": "英単語が重複しています", "row": int(row.name) + 2})

    issue_df = pd.DataFrame(issues, columns=["row", "word", "issue"])
    summary = {
        "total": len(words_df),
        "duplicates": int(report_df["word_key"].duplicated().sum()),
        "issues": len(issue_df),
        "missing_ipa": int(words_df["ipa"].isna().sum() + words_df["ipa"].astype(str).str.strip().eq("").sum()),
    }
    return summary, issue_df


@st.cache_data
def load_base_words() -> pd.DataFrame:
    return prepare_words(pd.read_csv(WORDS_PATH))
