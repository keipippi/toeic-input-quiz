import html
import random
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from auth import create_user, verify_user
from history import clear_history, load_history, save_history
from quiz import (
    choose_weighted_word,
    judge_answer,
    label,
    make_quiz_df,
    priority_label,
    priority_scores,
    weighted_words,
)
from words import (
    LEVEL_ORDER,
    LEVEL_PRESETS,
    REQUIRED_COLUMNS,
    WORDS_PATH,
    append_word_to_csv,
    clean_form_value,
    load_base_words,
    prepare_words,
    quality_report,
    validate_new_word,
)
from storage import storage_label
from storage import StorageError

TEN_QUESTION_MODE = "10問連続"
CARD_MODE = "カード"
WEAK_PRIORITY_DEFAULT = True
MODE_OPTIONS = [
    {
        "label": "通常練習",
        "mode": "全単語",
        "description": "選んだレベルの単語から入力式で練習します。",
    },
    {
        "label": "10問チャレンジ",
        "mode": TEN_QUESTION_MODE,
        "description": "10問を1セットにして、最後に結果を確認します。",
    },
    {
        "label": "カード学習",
        "mode": CARD_MODE,
        "description": "単語カードをめくりながら暗記します。",
    },
    {
        "label": "苦手復習",
        "mode": "間違えた単語だけ",
        "description": "過去に間違えた単語や、ほぼ正解だった単語を復習します。",
    },
    {
        "label": "期限復習",
        "mode": "復習期限の単語",
        "description": "今日までに復習予定になっている単語を出題します。",
    },
]
MODE_LABEL_TO_OPTION = {option["label"]: option for option in MODE_OPTIONS}


def speech_button(word: str):
    safe = html.escape(str(word), quote=True)
    components.html(f"""
        <style>
        html, body {{ margin: 0; padding: 0; background: transparent; }}
        button {{
            font-size: 16px;
            padding: 8px 14px;
            border-radius: 8px;
            border: 1px solid #d1d5db;
            background: #ffffff;
            cursor: pointer;
        }}
        </style>
        <button onclick="speakWord()">発音</button>
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
        html, body, .stApp {
            max-width: 100%;
            overflow-x: hidden;
        }
        .stApp {
            background: #f8fafc;
        }
        header[data-testid="stHeader"] {
            background: transparent;
        }
        .block-container {
            max-width: 760px;
            width: 100%;
            padding-top: 0.75rem;
            padding-bottom: 2rem;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.75rem;
        }
        .stButton > button,
        .stDownloadButton > button,
        div[data-testid="stFormSubmitButton"] > button {
            min-height: 3rem;
            width: 100%;
            border-radius: 8px;
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
            padding: 1.1rem;
            background: #ffffff;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
            width: 100%;
            box-sizing: border-box;
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
            margin-top: 0.9rem;
        }
        .card-answer {
            font-size: clamp(1.4rem, 6vw, 2.2rem);
            line-height: 1.25;
            font-weight: 700;
            overflow-wrap: anywhere;
            margin: 0.25rem 0 0.75rem;
        }
        .card-hint {
            color: #64748b;
            font-size: 0.9rem;
            margin: 0.7rem 0 0.25rem;
            text-align: center;
        }
        .st-key-card_primary_actions .stButton > button,
        .st-key-card_secondary_actions .stButton > button {
            display: flex;
            align-items: center;
            justify-content: center;
            min-width: 0 !important;
            white-space: nowrap;
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }
        .st-key-card_primary_actions .stButton > button {
            min-height: 3.25rem;
            font-weight: 700;
        }
        .st-key-card_secondary_actions .stButton > button {
            min-height: 2.8rem;
        }
        .app-kicker {
            color: #475569;
            font-size: 0.95rem;
            margin-bottom: 0.75rem;
        }
        .stTabs [role="tablist"] {
            overflow-x: auto;
            max-width: 100%;
        }
        @media (max-width: 640px) {
            .block-container {
                padding-left: 0.85rem;
                padding-right: 0.85rem;
                max-width: 100vw;
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


def render_login():
    if st.session_state.get("authenticated_user"):
        return st.session_state.authenticated_user

    st.subheader("ログイン")
    login_tab, signup_tab = st.tabs(["ログイン", "新規登録"])

    with login_tab:
        with st.form("login_form"):
            login_name = st.text_input("ユーザー名", placeholder="例: Keishi")
            login_pin = st.text_input("PIN", type="password", placeholder="4文字以上")
            submitted = st.form_submit_button("ログイン")
        if submitted:
            try:
                ok, user_id, message = verify_user(login_name, login_pin)
            except StorageError as exc:
                st.error(str(exc))
                return None
            if ok:
                st.session_state.authenticated_user = user_id
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    with signup_tab:
        with st.form("signup_form"):
            signup_name = st.text_input("ユーザー名", placeholder="例: Keishi")
            signup_pin = st.text_input("PIN", type="password", placeholder="4文字以上")
            signup_pin_confirm = st.text_input("PIN確認", type="password", placeholder="もう一度入力")
            submitted = st.form_submit_button("登録して始める")
        if submitted:
            if signup_pin != signup_pin_confirm:
                st.error("PINが一致しません。")
            else:
                try:
                    ok, user_id, message = create_user(signup_name, signup_pin)
                except StorageError as exc:
                    st.error(str(exc))
                    return None
                if ok:
                    st.session_state.authenticated_user = user_id
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

    st.info("ユーザー名とPINで成績を分けます。PINはそのまま保存せず、確認用の値だけを保存します。")
    return None


def choose_direction(direction):
    return random.choice(["英→日", "日→英"]) if direction == "ランダム" else direction


def scroll_to_top_on_new_question():
    token = st.session_state.get("scroll_to_top_token", 0)
    if st.session_state.get("last_scroll_to_top_token") == token:
        return
    st.session_state.last_scroll_to_top_token = token
    components.html(
        """
        <script>
        window.parent.scrollTo({ top: 0, behavior: "smooth" });
        </script>
        """,
        height=0,
    )


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
    st.session_state.scroll_to_top_token = st.session_state.get("scroll_to_top_token", 0) + 1


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


def record_card_result(user_name, row, actual_direction, result, history, qdf, mode, direction, prefer_weak):
    if result == "correct":
        save_history(user_name, row["word"], f"カード:{actual_direction}", "覚えた", "correct", "カード", "カードで覚えたとして記録しました。", history)
    else:
        save_history(user_name, row["word"], f"カード:{actual_direction}", "苦手", "wrong", "カード", "カードで苦手として記録しました。", history)
    next_history = load_history(user_name)
    go_next(qdf, next_history, mode, direction, prefer_weak)


def prepare_history_for_stats(history):
    h = history.copy()
    h["timestamp_dt"] = pd.to_datetime(h["timestamp"], errors="coerce")
    h["date"] = h["timestamp_dt"].dt.date
    h["next_review_dt"] = pd.to_datetime(h["next_review"], errors="coerce").dt.date
    return h


def learning_streak(history):
    dates = sorted(set(history["date"].dropna()), reverse=True)
    if not dates:
        return 0
    today = datetime.now().date()
    current = today if dates[0] == today else today - timedelta(days=1)
    streak = 0
    date_set = set(dates)
    while current in date_set:
        streak += 1
        current -= timedelta(days=1)
    return streak


def due_review_table(history, words_df):
    h = prepare_history_for_stats(history)
    latest = h.sort_values("timestamp_dt").drop_duplicates("word", keep="last")
    today = datetime.now().date()
    due = latest[latest["next_review_dt"].le(today)].copy()
    if due.empty:
        return due

    attempts = h.groupby("word").agg(
        解答数=("result", "count"),
        ミス回数=("result", lambda s: int((s != "correct").sum())),
    ).reset_index()
    due = due.merge(words_df[["word", "meaning", "level"]], on="word", how="left")
    due = due.merge(attempts, on="word", how="left")
    due["期限超過"] = due["next_review_dt"].apply(lambda d: max((today - d).days, 0) if pd.notna(d) else 0)
    due = due.rename(columns={
        "word": "単語",
        "meaning": "意味",
        "level": "レベル",
        "result": "前回結果",
        "next_review": "復習予定日",
    })
    return due[["単語", "意味", "レベル", "前回結果", "復習予定日", "期限超過", "解答数", "ミス回数"]].sort_values(
        ["期限超過", "ミス回数", "単語"],
        ascending=[False, False, True],
    )


def render_score_dashboard(history, words_df, user_name):
    st.subheader("成績")
    st.caption(f"ユーザー: {user_name}")
    if len(history) == 0:
        st.write("まだ履歴はありません。")
        return

    h = prepare_history_for_stats(history)
    today = datetime.now().date()
    week_start = today - timedelta(days=6)
    today_history = h[h["date"].eq(today)]
    week_history = h[h["date"].between(week_start, today, inclusive="both")]
    due_table = due_review_table(history, words_df)

    total_rate = h["result"].eq("correct").mean() * 100
    today_rate = today_history["result"].eq("correct").mean() * 100 if len(today_history) else 0

    top_cols = st.columns(3)
    top_cols[0].metric("今日の学習", f"{len(today_history)}問")
    top_cols[1].metric("今日の正解率", f"{today_rate:.1f}%")
    top_cols[2].metric("連続学習", f"{learning_streak(h)}日")

    bottom_cols = st.columns(3)
    bottom_cols[0].metric("累計解答", f"{len(h)}問")
    bottom_cols[1].metric("累計正解率", f"{total_rate:.1f}%")
    bottom_cols[2].metric("復習待ち", f"{len(due_table)}語")

    st.write("直近7日")
    st.metric("7日間の学習数", f"{len(week_history)}問")

    with st.expander("復習待ち単語", expanded=len(due_table) > 0):
        if due_table.empty:
            st.write("復習待ちの単語はありません。")
        else:
            st.dataframe(due_table, use_container_width=True, hide_index=True)

    with st.expander("レベル別の正解率", expanded=True):
        level_history = h.merge(words_df[["word", "level"]], on="word", how="left")
        level_stats = level_history.groupby("level", dropna=False).agg(
            解答数=("result", "count"),
            正解数=("result", lambda s: int((s == "correct").sum())),
        ).reset_index()
        level_stats["正解率"] = (level_stats["正解数"] / level_stats["解答数"] * 100).round(1)
        level_stats["level"] = level_stats["level"].fillna("追加CSV")
        st.dataframe(level_stats.sort_values("level"), use_container_width=True, hide_index=True)

    weak = h[h["result"].ne("correct")]
    if len(weak):
        st.write("よく間違える単語")
        weak_top = weak.groupby("word").size().reset_index(name="ミス回数").sort_values("ミス回数", ascending=False).head(5)
        st.dataframe(weak_top, use_container_width=True, hide_index=True)

    st.write("最近の履歴")
    st.dataframe(
        h.sort_values("timestamp_dt", ascending=False).head(8)[["word", "result", "direction", "next_review"]],
        use_container_width=True,
        hide_index=True,
    )


def render_quality_panel():
    st.subheader("品質チェック")
    raw_words = pd.read_csv(WORDS_PATH)
    summary, issue_df = quality_report(raw_words)
    q1, q2, q3 = st.columns(3)
    q1.metric("登録語数", summary["total"])
    q2.metric("重複", summary["duplicates"])
    q3.metric("要確認", summary["issues"])
    st.caption(f"発音記号が未入力の単語: {summary['missing_ipa']}語")

    level_df = pd.DataFrame(
        [{"レベル": level, "語数": count} for level, count in summary["level_counts"].items()]
    )
    st.dataframe(level_df, use_container_width=True, hide_index=True)

    if issue_df.empty:
        st.success("大きな問題は見つかりませんでした。")
        return

    issue_types = ["すべて"] + sorted(issue_df["type"].dropna().unique().tolist())
    selected_type = st.selectbox("問題タイプ", issue_types)
    filtered = issue_df if selected_type == "すべて" else issue_df[issue_df["type"].eq(selected_type)]
    st.caption(f"{len(filtered)}件を表示中")
    st.dataframe(filtered, use_container_width=True, hide_index=True)


st.set_page_config(page_title="TOEIC入力式単語練習", layout="centered")
apply_mobile_styles()
st.title("TOEIC入力式単語練習")
st.markdown(
    '<div class="app-kicker">入力式・カード・ユーザー別成績・英日/日英・忘却曲線復習・10問連続モード</div>',
    unsafe_allow_html=True,
)

user_name = render_login()
if not user_name:
    st.stop()

base_df = load_base_words()

with st.sidebar:
    st.header("ユーザー")
    st.caption(f"現在のユーザー: {user_name}")
    st.caption(f"保存先: {storage_label()}")
    if st.button("ログアウト"):
        for key in [
            "authenticated_user",
            "quiz_signature",
            "quiz_word",
            "quiz_direction",
            "card_flipped",
            "last",
            "ten_words",
            "ten_results",
        ]:
            st.session_state.pop(key, None)
        st.query_params.clear()
        st.rerun()

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

    mode_label = st.radio("学習メニュー", [option["label"] for option in MODE_OPTIONS], index=0)
    mode_option = MODE_LABEL_TO_OPTION[mode_label]
    mode = mode_option["mode"]
    st.caption(mode_option["description"])

    direction = st.radio("出題方向", ["英→日", "日→英", "ランダム"], index=0)
    prefer_weak = st.checkbox("苦手単語を優先", value=WEAK_PRIORITY_DEFAULT)
    st.info(
        f"{mode_label} / {direction} / "
        + (" / ".join(levels) if levels else "レベル未選択")
    )
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
scroll_to_top_on_new_question()

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
st.caption(
    f"学習メニュー: {mode_label} / 今回: {actual_direction} / "
    f"レベル: {', '.join(levels) if levels else '未選択'}"
)

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

    with st.container(key="card_secondary_actions"):
        flip_cols = st.columns(2, gap="small")
        with flip_cols[0]:
            if st.button("めくる" if not st.session_state.get("card_flipped", False) else "表に戻す", use_container_width=True):
                st.session_state.card_flipped = not st.session_state.get("card_flipped", False)
                st.rerun()
        with flip_cols[1]:
            if st.button("次のカード", use_container_width=True):
                go_next(qdf, history, mode, direction, prefer_weak)

    st.markdown('<div class="card-hint">左: 苦手 / 右: 覚えた</div>', unsafe_allow_html=True)
    with st.container(key="card_primary_actions"):
        result_cols = st.columns(2, gap="small")
        with result_cols[0]:
            if st.button("苦手", use_container_width=True):
                record_card_result(user_name, row, actual_direction, "wrong", history, qdf, mode, direction, prefer_weak)
        with result_cols[1]:
            if st.button("覚えた", use_container_width=True):
                record_card_result(user_name, row, actual_direction, "correct", history, qdf, mode, direction, prefer_weak)

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

    tab_score, tab_weak, tab_add, tab_quality, tab_words = st.tabs(["成績", "苦手", "単語追加", "品質", "単語"])

    with tab_score:
        render_score_dashboard(history, df, user_name)

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
        render_quality_panel()

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
    render_score_dashboard(history, df, user_name)
    if st.button("このユーザーの履歴リセット"):
        clear_history(user_name)
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
    render_quality_panel()

with tab_words:
    st.subheader("単語リスト")
    st.dataframe(df, use_container_width=True, hide_index=True)
