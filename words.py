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


def is_blank(value) -> bool:
    return pd.isna(value) or str(value).strip() == ""


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


def validate_word_update(row: dict, existing_df: pd.DataFrame, original_word: str) -> list[str]:
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

    original_key = normalize_word_key(original_word)
    new_key = normalize_word_key(row.get("word", ""))
    existing_keys = set(existing_df["word"].astype(str).map(normalize_word_key))
    if new_key != original_key and new_key in existing_keys:
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


def update_word_in_csv(original_word: str, row: dict):
    current = pd.read_csv(WORDS_PATH)
    for col in REQUIRED_COLUMNS:
        if col not in current.columns:
            current[col] = ""

    word_keys = current["word"].astype(str).map(normalize_word_key)
    target_key = normalize_word_key(original_word)
    matches = current.index[word_keys == target_key].tolist()
    if not matches:
        raise ValueError("修正対象の単語が見つかりませんでした。")

    for col in REQUIRED_COLUMNS:
        current.loc[matches[0], col] = row.get(col, "")
    current[REQUIRED_COLUMNS].to_csv(WORDS_PATH, index=False)
    load_base_words.clear()


def quality_report(words_df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    report_df = words_df.copy()
    for col in REQUIRED_COLUMNS:
        if col not in report_df.columns:
            report_df[col] = ""
    report_df["word_key"] = report_df["word"].astype(str).map(normalize_word_key)
    issues = []
    required_labels = {
        "word": "英単語",
        "meaning": "意味",
        "accepted_answers": "許容表現",
        "example": "英語例文",
        "level": "レベル",
        "pos": "品詞",
        "example_ja": "例文の日本語訳",
    }
    for index, row in report_df.iterrows():
        word = str(row["word"])
        row_number = index + 2
        for col, label_text in required_labels.items():
            value = row.get(col, "")
            if is_blank(value):
                issues.append({"row": row_number, "word": word, "type": "空欄", "issue": f"{label_text}が空欄です"})
        if str(row.get("level", "")) not in LEVEL_ORDER:
            issues.append({"row": row_number, "word": word, "type": "レベル", "issue": "レベルが 600 / 700 / 800 以外です"})

        meaning = str(row.get("meaning", "")).strip()
        meaning_parts = split_answers(meaning) or ([meaning] if meaning else [])
        meaning_keys = {normalize_word_key(part) for part in meaning_parts}
        if meaning and len(meaning) <= 1:
            issues.append({"row": row_number, "word": word, "type": "意味", "issue": "意味が短すぎる可能性があります"})
        if len(meaning) >= 40:
            issues.append({"row": row_number, "word": word, "type": "意味", "issue": "意味が長すぎる可能性があります"})

        answers = split_answers(row.get("accepted_answers", ""))
        if not answers:
            issues.append({"row": row_number, "word": word, "type": "許容表現", "issue": "許容表現が空欄または分割できません"})
        answer_keys = [normalize_word_key(answer) for answer in answers]
        if len(answer_keys) != len(set(answer_keys)):
            issues.append({"row": row_number, "word": word, "type": "許容表現", "issue": "許容表現の中に重複があります"})
        duplicated_with_meaning = [answer for answer in answers if normalize_word_key(answer) in meaning_keys]
        if duplicated_with_meaning:
            joined = "／".join(duplicated_with_meaning)
            issues.append({"row": row_number, "word": word, "type": "許容表現", "issue": f"意味と許容表現が重複しています: {joined}"})

        if is_blank(row.get("example", "")) or is_blank(row.get("example_ja", "")):
            issues.append({"row": row_number, "word": word, "type": "例文", "issue": "英語例文または日本語訳が空欄です"})

    duplicated = report_df[report_df["word_key"].duplicated(keep=False)].sort_values("word_key")
    for _, row in duplicated.iterrows():
        issues.append({"row": int(row.name) + 2, "word": row["word"], "type": "重複", "issue": "英単語が重複しています"})

    issue_df = pd.DataFrame(issues, columns=["row", "word", "type", "issue"])
    level_counts = report_df["level"].astype(str).value_counts().to_dict()
    summary = {
        "total": len(words_df),
        "duplicates": int(report_df["word_key"].duplicated().sum()),
        "issues": len(issue_df),
        "missing_ipa": int(report_df["ipa"].isna().sum() + report_df["ipa"].astype(str).str.strip().eq("").sum()),
        "level_counts": {level: int(level_counts.get(level, 0)) for level in LEVEL_ORDER},
    }
    return summary, issue_df


@st.cache_data
def load_base_words() -> pd.DataFrame:
    return prepare_words(pd.read_csv(WORDS_PATH))
