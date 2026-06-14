import json
import random
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

APP_DIR = Path(__file__).parent
WORDS_PATH = APP_DIR / "words.csv"
HISTORY_PATH = APP_DIR / "history.csv"


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = text.strip().lower()
    text = re.sub(r"[、，,／/・\s]+", "", text)
    text = text.replace("すること", "する")
    return text


def split_answers(text: str) -> list[str]:
    if pd.isna(text):
        return []
    parts = re.split(r"[、，,／/;；|｜]", str(text))
    return [p.strip() for p in parts if p.strip()]


@st.cache_data
def load_words() -> pd.DataFrame:
    df = pd.read_csv(WORDS_PATH)
    required = {"word", "meaning", "accepted_answers", "example", "note"}
    missing = required - set(df.columns)
    if missing:
        st.error(f"words.csv に必要な列がありません: {missing}")
        st.stop()
    return df


def load_history() -> pd.DataFrame:
    if HISTORY_PATH.exists():
        return pd.read_csv(HISTORY_PATH)
    return pd.DataFrame(columns=["timestamp", "word", "user_answer", "result", "mode", "reason"])


def save_history(word: str, user_answer: str, result: str, mode: str, reason: str):
    row = pd.DataFrame([{
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "word": word,
        "user_answer": user_answer,
        "result": result,
        "mode": mode,
        "reason": reason,
    }])
    if HISTORY_PATH.exists():
        old = pd.read_csv(HISTORY_PATH)
        new = pd.concat([old, row], ignore_index=True)
    else:
        new = row
    new.to_csv(HISTORY_PATH, index=False)


def local_judge(word_row: pd.Series, user_answer: str):
    user_norm = normalize_text(user_answer)
    meaning_list = split_answers(word_row["meaning"])
    accepted_list = split_answers(word_row["accepted_answers"])
    all_answers = meaning_list + accepted_list

    for ans in meaning_list:
        if user_norm == normalize_text(ans):
            return {"result": "correct", "mode": "完全一致", "reason": "登録されている正解訳と完全一致しました。"}

    for ans in accepted_list:
        if user_norm == normalize_text(ans):
            return {"result": "correct", "mode": "許容訳一致", "reason": "許容訳リストに含まれる表現と一致しました。"}

    for ans in all_answers:
        a = normalize_text(ans)
        if len(user_norm) >= 2 and len(a) >= 2 and (user_norm in a or a in user_norm):
            return {"result": "almost", "mode": "部分一致", "reason": f"登録訳『{ans}』と近い表現です。"}

    return None


def get_api_key():
    try:
        return st.secrets["OPENAI_API_KEY"]
    except Exception:
        return ""


def ai_judge(word_row: pd.Series, user_answer: str, model: str):
    api_key = get_api_key()

    if not api_key:
        return {"result": "wrong", "mode": "AI判定なし", "reason": "OPENAI_API_KEY が Streamlit Secrets に設定されていません。"}

    if OpenAI is None:
        return {"result": "wrong", "mode": "AI判定なし", "reason": "openai パッケージがインストールされていません。"}

    client = OpenAI(api_key=api_key)
    prompt = f"""
あなたはTOEIC英単語学習アプリの採点者です。
英単語と正解訳を見て、学習者の日本語回答が意味として合っているか判定してください。

判定は必ず次の3つのどれかにしてください。
- correct: TOEIC単語の意味として十分正しい
- almost: 近いが、少しズレている・文脈による
- wrong: 意味が違う

英単語: {word_row['word']}
正解訳: {word_row['meaning']}
許容訳: {word_row['accepted_answers']}
例文: {word_row['example']}
学習者の回答: {user_answer}

JSONだけで返してください。
形式:
{{"result":"correct / almost / wrong","reason":"短い日本語の理由","better_answer":"より自然な正解例"}}
""".strip()

    try:
        response = client.responses.create(
            model=model,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "toeic_judgement",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "result": {"type": "string", "enum": ["correct", "almost", "wrong"]},
                            "reason": {"type": "string"},
                            "better_answer": {"type": "string"},
                        },
                        "required": ["result", "reason", "better_answer"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                }
            },
        )
        data = json.loads(response.output_text)
        return {
            "result": data["result"],
            "mode": "AI判定",
            "reason": f"{data['reason']} 正解例: {data['better_answer']}",
        }
    except Exception as e:
        return {"result": "wrong", "mode": "AI判定エラー", "reason": f"AI判定でエラーが出ました: {e}"}


def result_label(result: str) -> str:
    if result == "correct":
        return "✅ 正解"
    if result == "almost":
        return "△ だいたい合っています"
    return "❌ 不正解"


st.set_page_config(page_title="TOEIC 入力式単語練習", page_icon="📘", layout="centered")

st.title("📘 TOEIC 入力式単語練習")
st.caption("4択ではなく、日本語訳を入力して覚えるアプリです。完全一致・許容訳・AIニュアンス判定に対応。")

df = load_words()
history = load_history()

with st.sidebar:
    st.header("設定")
    mode = st.radio("出題モード", ["全単語", "間違えた単語だけ", "ランダム10問"], index=0)
    use_ai = st.toggle("AI判定を使う", value=True)
    model = st.text_input("AIモデル", value="gpt-4.1-mini")

    if use_ai:
        if get_api_key():
            st.success("AI判定: 有効")
        else:
            st.warning("AI判定: SecretsにAPIキーが未設定")

    st.divider()
    st.subheader("学習履歴")
    if len(history) == 0:
        st.write("まだ履歴はありません。")
    else:
        total = len(history)
        correct = (history["result"] == "correct").sum()
        almost = (history["result"] == "almost").sum()
        wrong = (history["result"] == "wrong").sum()
        st.write(f"解答数: {total}")
        st.write(f"正解: {correct} / ほぼ正解: {almost} / 不正解: {wrong}")

    if st.button("履歴をリセット"):
        if HISTORY_PATH.exists():
            HISTORY_PATH.unlink()
        st.cache_data.clear()
        st.rerun()

quiz_df = df.copy()
if mode == "間違えた単語だけ" and len(history) > 0:
    wrong_words = history.loc[history["result"].isin(["wrong", "almost"]), "word"].unique().tolist()
    quiz_df = df[df["word"].isin(wrong_words)]
    if quiz_df.empty:
        st.success("復習対象の単語はありません。全単語モードに戻してください。")
        st.stop()

if mode == "ランダム10問":
    quiz_df = df.sample(min(10, len(df)), random_state=None)

if "current_index" not in st.session_state:
    st.session_state.current_index = random.randrange(len(quiz_df))
if "last_result" not in st.session_state:
    st.session_state.last_result = None

if st.session_state.current_index >= len(quiz_df):
    st.session_state.current_index = 0

word_row = quiz_df.iloc[st.session_state.current_index]

st.subheader("問題")
st.markdown(f"## **{word_row['word']}**")
st.write("この英単語の意味を日本語で入力してください。")

with st.form("answer_form", clear_on_submit=False):
    user_answer = st.text_input("あなたの答え", placeholder="例：増加する")
    submitted = st.form_submit_button("判定する")

if submitted:
    if not user_answer.strip():
        st.warning("答えを入力してください。")
    else:
        judgement = local_judge(word_row, user_answer)
        if judgement is None:
            if use_ai:
                judgement = ai_judge(word_row, user_answer, model)
            else:
                judgement = {
                    "result": "wrong",
                    "mode": "ローカル判定",
                    "reason": "登録されている正解訳・許容訳とは一致しませんでした。AI判定をオンにするとニュアンス判定できます。",
                }
        st.session_state.last_result = judgement
        save_history(word_row["word"], user_answer, judgement["result"], judgement["mode"], judgement["reason"])

if st.session_state.last_result:
    judgement = st.session_state.last_result
    if judgement["result"] == "correct":
        st.success(result_label(judgement["result"]))
    elif judgement["result"] == "almost":
        st.warning(result_label(judgement["result"]))
    else:
        st.error(result_label(judgement["result"]))

    st.write(f"**判定方法:** {judgement['mode']}")
    st.write(f"**理由:** {judgement['reason']}")
    st.info(f"正解例：{word_row['meaning']}")

    with st.expander("例文・メモを見る"):
        st.write(f"**例文:** {word_row['example']}")
        st.write(f"**メモ:** {word_row['note']}")

col1, col2 = st.columns(2)
with col1:
    if st.button("次の問題へ"):
        st.session_state.current_index = random.randrange(len(quiz_df))
        st.session_state.last_result = None
        st.rerun()

with col2:
    if st.button("この単語の答えを見る"):
        st.info(f"正解例：{word_row['meaning']}")
        st.write(f"許容訳：{word_row['accepted_answers']}")

st.divider()
st.subheader("単語データ")
with st.expander("登録単語を見る"):
    st.dataframe(df, use_container_width=True)

st.caption("単語を増やしたい場合は words.csv に行を追加してください。")
