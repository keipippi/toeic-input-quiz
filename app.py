import json
import random
import re
import unicodedata
from datetime import datetime, timedelta
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
REVIEW_STEPS = [1, 3, 7, 14, 30]


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", str(text)).strip().lower()
    text = re.sub(r"[、，,／/・\s]+", "", text)
    return text.replace("すること", "する")


def split_answers(text: str) -> list[str]:
    if pd.isna(text):
        return []
    return [p.strip() for p in re.split(r"[、，,／/;；|｜]", str(text)) if p.strip()]


@st.cache_data
def load_words() -> pd.DataFrame:
    df = pd.read_csv(WORDS_PATH)
    if "level" not in df.columns:
        df["level"] = "未設定"
    return df


def load_history() -> pd.DataFrame:
    cols = ["timestamp", "word", "direction", "user_answer", "result", "mode", "reason", "next_review"]
    if HISTORY_PATH.exists():
        df = pd.read_csv(HISTORY_PATH)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]
    return pd.DataFrame(columns=cols)


def get_api_key():
    try:
        return str(st.secrets["OPENAI_API_KEY"]).strip().strip('"').strip("'")
    except Exception:
        return ""


def api_key_problem() -> str:
    key = get_api_key()
    if not key:
        return "SecretsにOPENAI_API_KEYが設定されていません。"
    try:
        key.encode("ascii")
    except UnicodeEncodeError:
        return "OPENAI_API_KEYに日本語などの全角文字が入っています。実際のAPIキーだけを貼ってください。"
    if "実際" in key or "あなた" in key or "xxxx" in key.lower():
        return "OPENAI_API_KEYが仮の文字列のままです。実際のAPIキーに置き換えてください。"
    if not key.startswith("sk-"):
        return "OPENAI_API_KEYは通常 sk- から始まります。貼り間違いを確認してください。"
    return ""


def next_review_date(word: str, result: str, history: pd.DataFrame) -> str:
    today = datetime.now().date()
    if result == "wrong":
        return str(today + timedelta(days=1))
    if result == "almost":
        return str(today + timedelta(days=3))
    correct_count = len(history[(history["word"] == word) & (history["result"] == "correct")])
    days = REVIEW_STEPS[min(correct_count, len(REVIEW_STEPS) - 1)]
    return str(today + timedelta(days=days))


def save_history(word, direction, user_answer, result, mode, reason, history):
    row = pd.DataFrame([{
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "word": word,
        "direction": direction,
        "user_answer": user_answer,
        "result": result,
        "mode": mode,
        "reason": reason,
        "next_review": next_review_date(word, result, history),
    }])
    new = pd.concat([history, row], ignore_index=True)
    new.to_csv(HISTORY_PATH, index=False)


def local_judge(row, answer, direction):
    user = normalize_text(answer)
    if direction == "英→日":
        corrects = split_answers(row["meaning"])
        accepts = split_answers(row["accepted_answers"])
    else:
        corrects = [row["word"]]
        accepts = []
    for a in corrects:
        if user == normalize_text(a):
            return {"result": "correct", "mode": "完全一致", "reason": "正解と完全一致しました。"}
    for a in accepts:
        if user == normalize_text(a):
            return {"result": "correct", "mode": "許容訳一致", "reason": "許容訳として登録されています。"}
    for a in corrects + accepts:
        aa = normalize_text(a)
        if len(user) >= 2 and len(aa) >= 2 and (user in aa or aa in user):
            return {"result": "almost", "mode": "部分一致", "reason": f"『{a}』に近い表現です。"}
    return None


def ai_judge(row, answer, direction, model):
    problem = api_key_problem()
    if problem:
        return {"result": "wrong", "mode": "AI判定なし", "reason": problem}
    if OpenAI is None:
        return {"result": "wrong", "mode": "AI判定なし", "reason": "openaiパッケージが使えません。"}
    client = OpenAI(api_key=get_api_key())
    prompt = f"""
あなたはTOEIC単語学習アプリの採点者です。
方向: {direction}
英単語: {row['word']}
正解訳: {row['meaning']}
許容訳: {row['accepted_answers']}
例文: {row['example']}
学習者の回答: {answer}

判定は correct / almost / wrong のどれか。
短い日本語解説も付けてください。
JSONだけで返してください。
""".strip()
    try:
        res = client.responses.create(
            model=model,
            input=prompt,
            text={"format": {"type": "json_schema", "name": "judge", "schema": {
                "type": "object",
                "properties": {
                    "result": {"type": "string", "enum": ["correct", "almost", "wrong"]},
                    "reason": {"type": "string"},
                    "better_answer": {"type": "string"}
                },
                "required": ["result", "reason", "better_answer"],
                "additionalProperties": False
            }, "strict": True}}
        )
        d = json.loads(res.output_text)
        return {"result": d["result"], "mode": "AI判定", "reason": f"{d['reason']} 正解例: {d['better_answer']}"}
    except Exception as e:
        return {"result": "wrong", "mode": "AI判定エラー", "reason": f"APIキー・課金設定・モデル名を確認してください。詳細: {e}"}


def ai_tutor(row, answer, judgement, direction, model):
    problem = api_key_problem()
    if problem:
        return problem
    if OpenAI is None:
        return "openaiパッケージが使えません。"
    client = OpenAI(api_key=get_api_key())
    prompt = f"""
TOEIC単語の家庭教師として、短くわかりやすく日本語で解説してください。
方向: {direction}
英単語: {row['word']}
意味: {row['meaning']}
例文: {row['example']}
回答: {answer}
判定: {judgement['result']}
判定理由: {judgement['reason']}
出力は、1.どこが違うか 2.覚え方 3.例文訳 の順で簡潔に。
""".strip()
    try:
        res = client.responses.create(model=model, input=prompt)
        return res.output_text
    except Exception as e:
        return f"APIキー・課金設定・モデル名を確認してください。詳細: {e}"


def label(r):
    return {"correct": "✅ 正解", "almost": "△ ほぼ正解", "wrong": "❌ 不正解"}.get(r, r)


def make_quiz_df(df, history, mode, levels):
    q = df[df["level"].astype(str).isin([str(x) for x in levels])] if levels else df.copy()
    today = datetime.now().date()
    if mode == "間違えた単語だけ":
        words = history.loc[history["result"].isin(["wrong", "almost"]), "word"].unique().tolist()
        q = q[q["word"].isin(words)]
    elif mode == "復習期限の単語":
        h = history.copy()
        h["next_review_dt"] = pd.to_datetime(h["next_review"], errors="coerce").dt.date
        words = h.loc[h["next_review_dt"].le(today), "word"].unique().tolist()
        q = q[q["word"].isin(words)]
    return q


st.set_page_config(page_title="TOEIC入力式単語練習", page_icon="📘", layout="wide")
st.title("📘 TOEIC入力式単語練習")
st.caption("入力式・AI採点・AI家庭教師・英日/日英・忘却曲線復習・苦手ランキング対応")

df = load_words()
history = load_history()

with st.sidebar:
    st.header("設定")
    levels = st.multiselect("レベル", sorted(df["level"].astype(str).unique()), default=sorted(df["level"].astype(str).unique()))
    direction = st.radio("出題方向", ["英→日", "日→英", "ランダム"], index=0)
    mode = st.radio("出題モード", ["全単語", "ランダム10問", "間違えた単語だけ", "復習期限の単語"], index=0)
    use_ai = st.toggle("AI判定を使う", value=True)
    use_tutor = st.toggle("AI家庭教師解説", value=True)
    model = st.text_input("AIモデル", value="gpt-4.1-mini")
    problem = api_key_problem()
    st.write("AI:", "有効" if not problem else "未設定/要確認")
    if problem:
        st.warning(problem)

qdf = make_quiz_df(df, history, mode, levels)
if mode == "ランダム10問":
    qdf = qdf.sample(min(10, len(qdf))) if len(qdf) else qdf
if qdf.empty:
    st.warning("出題できる単語がありません。モードかレベルを変えてください。")
    st.stop()

if "quiz_word" not in st.session_state or st.session_state.quiz_word not in qdf["word"].tolist():
    st.session_state.quiz_word = random.choice(qdf["word"].tolist())
if "last" not in st.session_state:
    st.session_state.last = None

row = qdf[qdf["word"] == st.session_state.quiz_word].iloc[0]
actual_direction = random.choice(["英→日", "日→英"]) if direction == "ランダム" else direction

left, right = st.columns([2, 1])
with left:
    st.subheader("問題")
    if actual_direction == "英→日":
        st.markdown(f"## **{row['word']}**")
        placeholder = "例：増加する"
    else:
        st.markdown(f"## **{row['meaning']}**")
        placeholder = "例：increase"
    st.caption(f"Level: {row['level']} / Direction: {actual_direction}")

    with st.form("answer_form"):
        ans = st.text_input("答え", placeholder=placeholder)
        submitted = st.form_submit_button("判定する")

    if submitted and ans.strip():
        judge = local_judge(row, ans, actual_direction)
        if judge is None:
            judge = ai_judge(row, ans, actual_direction, model) if use_ai else {"result": "wrong", "mode": "ローカル判定", "reason": "登録訳と一致しませんでした。"}
        save_history(row["word"], actual_direction, ans, judge["result"], judge["mode"], judge["reason"], history)
        tutor = ai_tutor(row, ans, judge, actual_direction, model) if use_tutor and judge["result"] != "correct" else ""
        st.session_state.last = {"judge": judge, "answer": ans, "tutor": tutor}
        history = load_history()

    if st.session_state.last:
        j = st.session_state.last["judge"]
        if j["result"] == "correct":
            st.success(label(j["result"]))
        elif j["result"] == "almost":
            st.warning(label(j["result"]))
        else:
            st.error(label(j["result"]))
        st.write(f"**判定:** {j['mode']}")
        st.write(f"**理由:** {j['reason']}")
        st.info(f"英単語: {row['word']} / 意味: {row['meaning']}")
        if st.session_state.last["tutor"]:
            st.markdown("### AI家庭教師")
            st.write(st.session_state.last["tutor"])
        with st.expander("例文"):
            st.write(row["example"])
            st.write(row["note"])

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("次の問題"):
            st.session_state.quiz_word = random.choice(qdf["word"].tolist())
            st.session_state.last = None
            st.rerun()
    with c2:
        if st.button("答えを見る"):
            st.info(f"英単語: {row['word']} / 意味: {row['meaning']} / 許容訳: {row['accepted_answers']}")
    with c3:
        if st.button("履歴リセット"):
            if HISTORY_PATH.exists():
                HISTORY_PATH.unlink()
            st.session_state.last = None
            st.rerun()

with right:
    st.subheader("成績")
    if len(history) == 0:
        st.write("まだ履歴はありません。")
    else:
        total = len(history)
        st.metric("解答数", total)
        st.metric("正解率", f"{(history['result'].eq('correct').mean()*100):.1f}%")
        st.write("次回復習予定")
        st.dataframe(history.tail(5)[["word", "result", "next_review"]], use_container_width=True, hide_index=True)

st.divider()
st.subheader("苦手ランキング")
if len(history):
    g = history.groupby("word").agg(
        attempts=("result", "count"),
        correct=("result", lambda s: (s == "correct").sum()),
        wrong=("result", lambda s: (s != "correct").sum()),
    ).reset_index()
    g["正解率"] = (g["correct"] / g["attempts"] * 100).round(1)
    g = g.sort_values(["正解率", "attempts"], ascending=[True, False])
    st.dataframe(g, use_container_width=True, hide_index=True)
else:
    st.write("まだデータがありません。")

with st.expander("単語リスト"):
    st.dataframe(df, use_container_width=True, hide_index=True)
