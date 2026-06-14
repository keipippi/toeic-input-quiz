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
TEN_QUESTION_MODE = "10問連続"
CARD_MODE = "カード"
WEAK_PRIORITY_DEFAULT = True


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


def priority_scores(qdf: pd.DataFrame, history: pd.DataFrame) -> dict[str, float]:
    scores = {word: 1.0 for word in qdf["word"].astype(str)}
    if history.empty:
        return scores

    h = history.copy()
    h["timestamp_dt"] = pd.to_datetime(h["timestamp"], errors="coerce")
    h["next_review_dt"] = pd.to_datetime(h["next_review"], errors="coerce").dt.date
    today = datetime.now().date()

    for word, group in h.groupby("word"):
        word = str(word)
        if word not in scores:
            continue
        attempts = len(group)
        correct = int(group["result"].eq("correct").sum())
        wrong = int(group["result"].eq("wrong").sum())
        almost = int(group["result"].eq("almost").sum())
        accuracy = correct / attempts if attempts else 0
        score = 1.0
        score += wrong * 2.0
        score += almost * 1.2
        score += (1 - accuracy) * 3.0

        latest = group.sort_values("timestamp_dt").tail(1).iloc[0]
        if latest["result"] == "wrong":
            score += 2.0
        elif latest["result"] == "almost":
            score += 1.2

        due_dates = group["next_review_dt"].dropna()
        if len(due_dates) and due_dates.max() <= today:
            overdue_days = max((today - due_dates.max()).days, 0)
            score += 2.5 + min(overdue_days, 7) * 0.25

        scores[word] = round(score, 3)
    return scores


def choose_weighted_word(qdf: pd.DataFrame, history: pd.DataFrame, prefer_weak: bool) -> str:
    words = qdf["word"].astype(str).tolist()
    if not prefer_weak:
        return random.choice(words)
    scores = priority_scores(qdf, history)
    weights = [scores.get(word, 1.0) for word in words]
    return random.choices(words, weights=weights, k=1)[0]


def weighted_words(qdf: pd.DataFrame, history: pd.DataFrame, prefer_weak: bool, limit: int) -> list[str]:
    words = qdf["word"].astype(str).tolist()
    if not prefer_weak:
        random.shuffle(words)
        return words[:limit]

    scores = priority_scores(qdf, history)
    remaining = words.copy()
    selected = []
    while remaining and len(selected) < limit:
        weights = [scores.get(word, 1.0) for word in remaining]
        picked = random.choices(remaining, weights=weights, k=1)[0]
        selected.append(picked)
        remaining.remove(picked)
    return selected


def priority_label(word: str, history: pd.DataFrame) -> str:
    if history.empty or word not in set(history["word"].astype(str)):
        return "初出"
    word_history = history[history["word"].astype(str) == str(word)]
    attempts = len(word_history)
    correct = int(word_history["result"].eq("correct").sum())
    wrong = int(word_history["result"].ne("correct").sum())
    accuracy = correct / attempts * 100 if attempts else 0
    return f"苦手度: {wrong}回ミス / 正解率 {accuracy:.0f}%"


def speech_button(word: str):
    safe = html.escape(str(word), quote=True)
    components.html(f"""
        <button onclick="speakWord()" style="font-size:16px;padding:8px 14px;border-radius:8px;border:1px solid #ddd;cursor:pointer;">🔊 発音</button>
        <script>
        function speakWord() {{
            const u = new SpeechSynthesisUtterance("{safe}");
            u.lang = "en-US";
            u.rate = 0.85;
            window.speechSynthesis.speak(u);
        }}
        </script>
    """, height=45)


def apply_mobile_styles():
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 760px;
            padding-top: 1rem;
            padding-bottom: 2rem;
        }
        div[data-testid="stMetric"] {
            background: #f8fafc;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.75rem;
        }
        .stButton > button,
        .stDownloadButton > button,
        div[data-testid="stFormSubmitButton"] > button {
            min-height: 3rem;
            width: 100%;
        }
        .stTextInput input {
            font-size: 16px;
            min-height: 3rem;
        }
        .stTextArea textarea {
            font-size: 16px;
        }
        .quiz-card {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 1rem;
            background: #ffffff;
        }
        .quiz-word {
            font-size: clamp(2rem, 8vw, 3.4rem);
            line-height: 1.1;
            font-weight: 700;
            overflow-wrap: anywhere;
            margin: 0.25rem 0 0.5rem;
        }
        .quiz-meta {
            color: #64748b;
            font-size: 0.9rem;
        }
        .card-back {
            border-top: 1px solid #e5e7eb;
            margin-top: 1rem;
            padding-top: 1rem;
        }
        .card-answer {
            font-size: clamp(1.4rem, 6vw, 2.2rem);
            line-height: 1.25;
            font-weight: 700;
            overflow-wrap: anywhere;
            margin: 0.25rem 0 0.75rem;
        }
        @media (max-width: 640px) {
            .block-container {
                padding-left: 0.85rem;
                padding-right: 0.85rem;
            }
            h1 {
                font-size: 1.7rem !important;
            }
            h2, h3 {
                font-size: 1.25rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def choose_direction(direction):
    return random.choice(["英→日", "日→英"]) if direction == "ランダム" else direction


def quiz_signature(qdf, mode, levels, direction, user_name, prefer_weak):
    return {
        "mode": mode,
        "levels": tuple(str(x) for x in levels),
        "direction": direction,
        "user": user_name,
        "prefer_weak": prefer_weak,
        "words": tuple(qdf["word"].tolist()),
    }


def set_question(word, direction):
    st.session_state.quiz_word = word
    st.session_state.quiz_direction = choose_direction(direction)
    st.session_state.card_flipped = False
    st.session_state.last = None
    st.session_state.answer_version = st.session_state.get("answer_version", 0) + 1


def start_ten_question_round(qdf, direction, history, prefer_weak):
    st.session_state.ten_words = weighted_words(qdf, history, prefer_weak, min(10, len(qdf)))
    st.session_state.ten_index = 0
    st.session_state.ten_results = []
    st.session_state.ten_finished = False
    set_question(st.session_state.ten_words[0], direction)


def ensure_quiz_state(qdf, history, mode, levels, direction, user_name, prefer_weak):
    signature = quiz_signature(qdf, mode, levels, direction, user_name, prefer_weak)
    if st.session_state.get("quiz_signature") != signature:
        st.session_state.quiz_signature = signature
        if mode == TEN_QUESTION_MODE:
            start_ten_question_round(qdf, direction, history, prefer_weak)
        else:
            st.session_state.ten_finished = False
            st.session_state.ten_words = []
            st.session_state.ten_index = 0
            st.session_state.ten_results = []
            set_question(choose_weighted_word(qdf, history, prefer_weak), direction)
    elif "quiz_word" not in st.session_state or st.session_state.quiz_word not in qdf["word"].tolist():
        if mode == TEN_QUESTION_MODE:
            start_ten_question_round(qdf, direction, history, prefer_weak)
        else:
            set_question(choose_weighted_word(qdf, history, prefer_weak), direction)


def go_next(qdf, history, mode, direction, prefer_weak):
    if mode == TEN_QUESTION_MODE:
        next_index = st.session_state.get("ten_index", 0) + 1
        ten_words = st.session_state.get("ten_words", [])
        if next_index >= len(ten_words):
            st.session_state.ten_finished = True
            st.session_state.last = None
            st.session_state.answer_version = st.session_state.get("answer_version", 0) + 1
            st.rerun()
        st.session_state.ten_index = next_index
        set_question(ten_words[next_index], direction)
    else:
        set_question(choose_weighted_word(qdf, history, prefer_weak), direction)
    st.rerun()


st.set_page_config(page_title="TOEIC入力式単語練習", page_icon="📘", layout="centered")
apply_mobile_styles()
st.title("📘 TOEIC入力式単語練習")
st.caption("入力式・カード・ユーザー別成績・英日/日英・忘却曲線復習・10問連続モード")

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
    mode = st.radio("出題モード", ["全単語", TEN_QUESTION_MODE, CARD_MODE, "間違えた単語だけ", "復習期限の単語"], index=0)
    prefer_weak = st.checkbox("苦手単語を優先", value=WEAK_PRIORITY_DEFAULT)
    st.success(f"読み込み語数: {len(df)}語")

history = load_history(user_name)
qdf = make_quiz_df(df, history, mode, levels)
if qdf.empty:
    st.warning("出題できる単語がありません。モードかレベルを変えてください。")
    st.stop()

if "last" not in st.session_state:
    st.session_state.last = None
if "answer_version" not in st.session_state:
    st.session_state.answer_version = 0

ensure_quiz_state(qdf, history, mode, levels, direction, user_name, prefer_weak)

if mode == TEN_QUESTION_MODE and st.session_state.get("ten_finished"):
    results = st.session_state.get("ten_results", [])
    correct_count = sum(1 for r in results if r["result"] == "correct")
    almost_count = sum(1 for r in results if r["result"] == "almost")
    wrong_count = sum(1 for r in results if r["result"] == "wrong")
    st.subheader("10問の結果")
    m1, m2, m3 = st.columns(3)
    m1.metric("正解", correct_count)
    m2.metric("ほぼ正解", almost_count)
    m3.metric("不正解", wrong_count)
    if results:
        st.dataframe(pd.DataFrame(results)[["word", "result", "user_answer"]], use_container_width=True, hide_index=True)
    if st.button("もう一度10問に挑戦"):
        start_ten_question_round(qdf, direction, history, prefer_weak)
        st.rerun()
    st.stop()

row = qdf[qdf["word"] == st.session_state.quiz_word].iloc[0]
actual_direction = st.session_state.quiz_direction

if mode == CARD_MODE:
    if actual_direction == "英→日":
        card_front = row["word"]
        card_back_label = "意味"
        card_back = row["meaning"]
        card_sub_label = "許容表現"
        card_sub = row["accepted_answers"]
    else:
        card_front = row["meaning"]
        card_back_label = "英単語"
        card_back = row["word"]
        card_sub_label = "許容表現"
        card_sub = row["accepted_answers"]

    st.subheader("カード")
    st.markdown(
        f"""
        <div class="quiz-card">
          <div class="quiz-meta">Level {row['level']} / {row['pos']} / {actual_direction}</div>
          <div class="quiz-word">{html.escape(str(card_front))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if actual_direction == "英→日" or st.session_state.get("card_flipped", False):
        speech_button(row["word"])
    if prefer_weak:
        st.caption(priority_label(row["word"], history))

    if st.session_state.get("card_flipped", False):
        st.markdown(
            f"""
            <div class="quiz-card card-back">
              <div class="quiz-meta">{html.escape(card_back_label)}</div>
              <div class="card-answer">{html.escape(str(card_back))}</div>
              <div class="quiz-meta">{html.escape(card_sub_label)}</div>
              <p>{html.escape(str(card_sub))}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("例文・メモ", expanded=True):
            st.write(row["example"])
            st.write(row["example_ja"])
            st.write(row["note"])

    flip_cols = st.columns(2)
    with flip_cols[0]:
        if st.button("めくる" if not st.session_state.get("card_flipped", False) else "表に戻す"):
            st.session_state.card_flipped = not st.session_state.get("card_flipped", False)
            st.rerun()
    with flip_cols[1]:
        if st.button("次のカード"):
            go_next(qdf, history, mode, direction, prefer_weak)

    result_cols = st.columns(2)
    with result_cols[0]:
        if st.button("覚えた"):
            save_history(user_name, row["word"], f"カード:{actual_direction}", "覚えた", "correct", "カード", "カードで覚えたとして記録しました。", history)
            history = load_history(user_name)
            go_next(qdf, history, mode, direction, prefer_weak)
    with result_cols[1]:
        if st.button("苦手"):
            save_history(user_name, row["word"], f"カード:{actual_direction}", "苦手", "wrong", "カード", "カードで苦手として記録しました。", history)
            history = load_history(user_name)
            go_next(qdf, history, mode, direction, prefer_weak)

    tab_score, tab_weak, tab_add, tab_quality, tab_words = st.tabs(["成績", "苦手", "単語追加", "品質", "単語"])

    with tab_score:
        st.subheader("成績")
        st.caption(f"ユーザー: {user_name}")
        if len(history) == 0:
            st.write("まだ履歴はありません。")
        else:
            score_cols = st.columns(2)
            score_cols[0].metric("解答数", len(history))
            score_cols[1].metric("正解率", f"{(history['result'].eq('correct').mean()*100):.1f}%")
            st.write("次回復習予定")
            st.dataframe(history.tail(5)[["word", "result", "next_review"]], use_container_width=True, hide_index=True)

    with tab_weak:
        st.subheader("苦手ランキング")
        if len(history):
            g = history.groupby("word").agg(
                attempts=("result", "count"),
                correct=("result", lambda s: (s == "correct").sum()),
                wrong=("result", lambda s: (s != "correct").sum()),
            ).reset_index()
            g["正解率"] = (g["correct"] / g["attempts"] * 100).round(1)
            scores = priority_scores(df, history)
            g["優先度"] = g["word"].map(scores).fillna(1.0)
            st.dataframe(g.sort_values(["優先度", "正解率", "attempts"], ascending=[False, True, False]), use_container_width=True, hide_index=True)
        else:
            st.write("まだデータがありません。")

    with tab_add:
        st.subheader("単語追加")
        st.write("カードモード中も、通常画面と同じ単語追加フォームを使えます。")

    with tab_quality:
        st.subheader("品質チェック")
        summary, issue_df = quality_report(base_df)
        q1, q2, q3 = st.columns(3)
        q1.metric("登録語数", summary["total"])
        q2.metric("重複", summary["duplicates"])
        q3.metric("要確認", summary["issues"])
        st.caption(f"発音記号が未入力の単語: {summary['missing_ipa']}語")
        if issue_df.empty:
            st.success("大きな問題は見つかりませんでした。")
        else:
            st.dataframe(issue_df, use_container_width=True, hide_index=True)

    with tab_words:
        st.subheader("単語リスト")
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.stop()

if mode == TEN_QUESTION_MODE:
    total = len(st.session_state.get("ten_words", []))
    current = st.session_state.get("ten_index", 0) + 1
    st.progress(current / total, text=f"{current} / {total} 問")

st.subheader("問題")
if actual_direction == "英→日":
    prompt_text = row["word"]
    placeholder = "例：購入する"
else:
    prompt_text = row["meaning"]
    placeholder = "例：purchase"

st.markdown(
    f"""
    <div class="quiz-card">
      <div class="quiz-meta">Level {row['level']} / {row['pos']} / {actual_direction}</div>
      <div class="quiz-word">{html.escape(str(prompt_text))}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if actual_direction == "英→日":
    speech_button(row["word"])

ipa = str(row.get("ipa", ""))
if ipa and ipa != "nan":
    st.caption(f"発音記号: {ipa}")
st.caption(f"ユーザー: {user_name}")
if prefer_weak:
    st.caption(priority_label(row["word"], history))

answer_key = f"answer_input_{st.session_state.answer_version}"
with st.form("answer_form"):
    ans = st.text_input("答え", key=answer_key, placeholder=placeholder)
    button_label = "次へ" if st.session_state.last else "判定する"
    submitted = st.form_submit_button(button_label)

if submitted:
    if st.session_state.last:
        go_next(qdf, history, mode, direction, prefer_weak)
    else:
        judge = judge_answer(row, ans, actual_direction)
        save_history(user_name, row["word"], actual_direction, ans, judge["result"], judge["mode"], judge["reason"], history)
        if mode == TEN_QUESTION_MODE:
            st.session_state.ten_results.append({
                "word": row["word"],
                "result": judge["result"],
                "user_answer": ans,
            })
        st.session_state.last = {"judge": judge, "answer": ans}
        history = load_history(user_name)
        st.rerun()

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
    with st.expander("例文・メモ"):
        st.write(row["example"])
        st.write(row["example_ja"])
        st.write(row["note"])

action_cols = st.columns(2)
with action_cols[0]:
    next_disabled = mode == TEN_QUESTION_MODE and not st.session_state.last
    if st.button("次の問題", disabled=next_disabled):
        go_next(qdf, history, mode, direction, prefer_weak)
with action_cols[1]:
    if st.button("答えを見る"):
        st.info(f"英単語: {row['word']} / 意味: {row['meaning']} / 許容訳: {row['accepted_answers']}")

tab_score, tab_weak, tab_add, tab_quality, tab_words = st.tabs(["成績", "苦手", "単語追加", "品質", "単語"])

with tab_score:
    st.subheader("成績")
    st.caption(f"ユーザー: {user_name}")
    if len(history) == 0:
        st.write("まだ履歴はありません。")
    else:
        score_cols = st.columns(2)
        score_cols[0].metric("解答数", len(history))
        score_cols[1].metric("正解率", f"{(history['result'].eq('correct').mean()*100):.1f}%")
        st.write("次回復習予定")
        st.dataframe(history.tail(5)[["word", "result", "next_review"]], use_container_width=True, hide_index=True)
    if st.button("このユーザーの履歴リセット"):
        path = history_path(user_name)
        if path.exists():
            path.unlink()
        st.session_state.last = None
        st.session_state.answer_version = st.session_state.get("answer_version", 0) + 1
        st.rerun()

with tab_weak:
    st.subheader("苦手ランキング")
    if len(history):
        g = history.groupby("word").agg(
            attempts=("result", "count"),
            correct=("result", lambda s: (s == "correct").sum()),
            wrong=("result", lambda s: (s != "correct").sum()),
        ).reset_index()
        g["正解率"] = (g["correct"] / g["attempts"] * 100).round(1)
        scores = priority_scores(df, history)
        g["優先度"] = g["word"].map(scores).fillna(1.0)
        st.dataframe(g.sort_values(["優先度", "正解率", "attempts"], ascending=[False, True, False]), use_container_width=True, hide_index=True)
    else:
        st.write("まだデータがありません。")

with tab_add:
    st.subheader("単語追加")
    if st.session_state.get("add_word_success"):
        st.success(st.session_state.pop("add_word_success"))
    with st.form("add_word_form", clear_on_submit=True):
        new_word = st.text_input("英単語", placeholder="例：purchase")
        new_meaning = st.text_input("意味", placeholder="例：購入する")
        new_accepted = st.text_input("許容表現", placeholder="例：買う／購入")
        new_level = st.selectbox("レベル", LEVEL_ORDER)
        new_pos = st.text_input("品詞", placeholder="例：verb")
        new_example = st.text_area("例文", placeholder="例：We purchased new equipment.")
        new_example_ja = st.text_area("例文の日本語訳", placeholder="例：私たちは新しい設備を購入しました。")
        new_note = st.text_input("メモ", placeholder="例：購買・経理で頻出")
        new_ipa = st.text_input("発音記号", placeholder="例：/ˈpɜːrtʃəs/")
        add_submitted = st.form_submit_button("単語を追加")

    if add_submitted:
        new_row = {
            "word": clean_form_value(new_word),
            "meaning": clean_form_value(new_meaning),
            "accepted_answers": clean_form_value(new_accepted),
            "example": clean_form_value(new_example),
            "note": clean_form_value(new_note),
            "level": clean_form_value(new_level),
            "pos": clean_form_value(new_pos),
            "example_ja": clean_form_value(new_example_ja),
            "ipa": clean_form_value(new_ipa),
        }
        validation_errors = validate_new_word(new_row, df)
        if validation_errors:
            for error in validation_errors:
                st.error(error)
        else:
            append_word_to_csv(new_row)
            st.session_state.quiz_signature = None
            st.session_state.add_word_success = f"{new_row['word']} を追加しました。"
            st.rerun()

with tab_quality:
    st.subheader("品質チェック")
    summary, issue_df = quality_report(base_df)
    q1, q2, q3 = st.columns(3)
    q1.metric("登録語数", summary["total"])
    q2.metric("重複", summary["duplicates"])
    q3.metric("要確認", summary["issues"])
    st.caption(f"発音記号が未入力の単語: {summary['missing_ipa']}語")
    if issue_df.empty:
        st.success("大きな問題は見つかりませんでした。")
    else:
        st.dataframe(issue_df, use_container_width=True, hide_index=True)

with tab_words:
    st.subheader("単語リスト")
    st.dataframe(df, use_container_width=True, hide_index=True)
