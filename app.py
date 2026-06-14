import html
import random
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

APP_DIR = Path(__file__).parent
WORDS_PATH = APP_DIR / "words.csv"
REVIEW_STEPS = [1, 3, 7, 14, 30]
REQUIRED_COLUMNS = ["word", "meaning", "accepted_answers", "example", "note", "level", "pos", "example_ja", "ipa"]
LEVEL_ORDER = ["600", "700", "800"]
LEVEL_PRESETS = {
    "600だけ": ["600"],
    "600+700": ["600", "700"],
    "全部": ["600", "700", "800"],
    "手動で選ぶ": [],
}


def safe_user_id(name: str) -> str:
    name = unicodedata.normalize("NFKC", str(name)).strip()
    name = re.sub(r"[^0-9A-Za-zぁ-んァ-ン一-龥_-]+", "_", name)
    return name[:40] if name else "guest"


def history_path(user_name: str) -> Path:
    return APP_DIR / f"history_{safe_user_id(user_name)}.csv"


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


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", str(text)).strip().lower()
    text = re.sub(r"[、，,／/・\s\n\t]+", "", text)
    text = text.replace("すること", "する")
    text = text.replace("です", "").replace("ます", "")
    text = text.replace("を", "").replace("が", "").replace("に", "").replace("へ", "")
    return text


def split_answers(text: str) -> list[str]:
    if pd.isna(text):
        return []
    return [p.strip() for p in re.split(r"[、，,／/;；|｜]", str(text)) if p.strip()]


def prepare_words(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["level"] = df["level"].apply(normalize_level)
    df = df[REQUIRED_COLUMNS]
    df = df.dropna(subset=["word", "meaning"])
    df["word"] = df["word"].astype(str).str.strip()
    return df[df["word"] != ""]


@st.cache_data
def load_base_words() -> pd.DataFrame:
    return prepare_words(pd.read_csv(WORDS_PATH))


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


def judge_answer(row, answer, direction):
    user = normalize_text(answer)
    if not user:
        return {"result": "wrong", "mode": "未入力", "reason": "答えを入力してください。"}

    if direction == "英→日":
        corrects = split_answers(row["meaning"])
        accepts = split_answers(row["accepted_answers"])
        all_ok = corrects + accepts
    else:
        corrects = [str(row["word"])]
        accepts = []
        all_ok = corrects

    for a in corrects:
        if user == normalize_text(a):
            return {"result": "correct", "mode": "完全一致", "reason": "正解訳と完全一致しました。"}
    for a in accepts:
        if user == normalize_text(a):
            return {"result": "correct", "mode": "類義語一致", "reason": f"『{a}』は許容訳として登録されています。"}
    for a in all_ok:
        aa = normalize_text(a)
        if len(user) >= 2 and len(aa) >= 2 and (user in aa or aa in user):
            return {"result": "almost", "mode": "部分一致", "reason": f"『{a}』に近いですが、少し短い/広い表現です。"}
    return {"result": "wrong", "mode": "辞書判定", "reason": "登録されている正解・類義語とは一致しませんでした。"}


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


def speech_button(word: str):
    safe = html.escape(str(word), quote=True)
    components.html(
        f"""
        <button onclick="speakWord()" style="font-size:16px;padding:8px 14px;border-radius:8px;border:1px solid #ddd;cursor:pointer;">🔊 発音</button>
        <script>
        function speakWord() {{
            const u = new SpeechSynthesisUtterance("{safe}");
            u.lang = "en-US";
            u.rate = 0.85;
            window.speechSynthesis.speak(u);
        }}
        </script>
        """,
        height=45,
    )


def go_next(qdf):
    st.session_state.quiz_word = random.choice(qdf["word"].tolist())
    st.session_state.last = None
    st.session_state.next_enter = ""
    st.rerun()


st.set_page_config(page_title="TOEIC入力式単語練習", page_icon="📘", layout="wide")
st.title("📘 TOEIC入力式単語練習")
st.caption("入力式・ユーザー別成績・英日/日英・忘却曲線復習・発音ボタン対応")

base_df = load_base_words()

with st.sidebar:
    st.header("ユーザー")
    user_name = st.text_input("ユーザー名", value=st.session_state.get("user_name", "Keishi"), placeholder="例：Keishi / Taro")
    user_name = safe_user_id(user_name)
    st.session_state.user_name = user_name
    st.caption(f"現在のユーザー: {user_name}")

    st.header("設定")
    uploaded_files = st.file_uploader("単語CSVを追加（複数可）", type=["csv"], accept_multiple_files=True)
    dfs = [base_df]
    loaded_count = 0
    if uploaded_files:
        for uploaded in uploaded_files:
            try:
                user_df = prepare_words(pd.read_csv(uploaded))
                dfs.append(user_df)
                loaded_count += len(user_df)
            except Exception as e:
                st.error(f"{uploaded.name} を読み込めませんでした: {e}")
        st.success(f"{len(uploaded_files)}個のCSVから合計 {loaded_count} 語を読み込みました")
    df = pd.concat(dfs, ignore_index=True).drop_duplicates(subset=["word"], keep="last")

    st.download_button("CSVテンプレートをダウンロード", data=",".join(REQUIRED_COLUMNS) + "\n", file_name="toeic_words_template.csv", mime="text/csv")

    available_levels = [lv for lv in LEVEL_ORDER if lv in set(df["level"].astype(str))]
    preset = st.radio("レベル選択", ["600だけ", "600+700", "全部", "手動で選ぶ"], index=0)
    if preset == "手動で選ぶ":
        levels = st.multiselect("レベル", available_levels, default=available_levels)
    else:
        levels = [lv for lv in LEVEL_PRESETS[preset] if lv in available_levels]
        st.caption("選択中: " + (" / ".join(levels) if levels else "該当レベルなし"))

    direction = st.radio("出題方向", ["英→日", "日→英", "ランダム"], index=0)
    mode = st.radio("出題モード", ["全単語", "ランダム10問", "間違えた単語だけ", "復習期限の単語"], index=0)
    st.success(f"読み込み語数: {len(df)}語")

history = load_history(user_name)
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
if "next_enter" not in st.session_state:
    st.session_state.next_enter = ""

row = qdf[qdf["word"] == st.session_state.quiz_word].iloc[0]
actual_direction = random.choice(["英→日", "日→英"]) if direction == "ランダム" else direction

left, right = st.columns([2, 1])
with left:
    st.subheader("問題")
    if actual_direction == "英→日":
        st.markdown(f"## **{row['word']}**")
        speech_button(row["word"])
        placeholder = "例：購入する"
    else:
        st.markdown(f"## **{row['meaning']}**")
        placeholder = "例：purchase"

    ipa = str(row.get("ipa", ""))
    if ipa and ipa != "nan":
        st.caption(f"発音記号: {ipa}")
    st.caption(f"User: {user_name} / Level: {row['level']} / 品詞: {row['pos']} / Direction: {actual_direction}")

    with st.form("answer_form"):
        ans = st.text_input("答え", placeholder=placeholder)
        submitted = st.form_submit_button("判定する")

    if submitted:
        judge = judge_answer(row, ans, actual_direction)
        save_history(user_name, row["word"], actual_direction, ans, judge["result"], judge["mode"], judge["reason"], history)
        st.session_state.last = {"judge": judge, "answer": ans}
        history = load_history(user_name)

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
        st.write(f"**許容表現:** {row['accepted_answers']}")
        st.caption("下の入力欄でEnterを押すと次の問題へ進めます。")
        with st.form("next_form"):
            st.text_input("次へ", key="next_enter", placeholder="Enterで次へ")
            next_submitted = st.form_submit_button("次の問題へ")
        if next_submitted:
            go_next(qdf)
        with st.expander("例文・メモ"):
            st.write(row["example"])
            st.write(row["example_ja"])
            st.write(row["note"])

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("次の問題"):
            go_next(qdf)
    with c2:
        if st.button("答えを見る"):
            st.info(f"英単語: {row['word']} / 意味: {row['meaning']} / 許容訳: {row['accepted_answers']}")
    with c3:
        if st.button("このユーザーの履歴リセット"):
            path = history_path(user_name)
            if path.exists():
                path.unlink()
            st.session_state.last = None
            st.rerun()

with right:
    st.subheader("成績")
    st.caption(f"ユーザー: {user_name}")
    if len(history) == 0:
        st.write("まだ履歴はありません。")
    else:
        st.metric("解答数", len(history))
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
    st.dataframe(g.sort_values(["正解率", "attempts"], ascending=[True, False]), use_container_width=True, hide_index=True)
else:
    st.write("まだデータがありません。")

with st.expander("単語リスト"):
    st.dataframe(df, use_container_width=True, hide_index=True)
