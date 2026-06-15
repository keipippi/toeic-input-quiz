import html
import random

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from history import history_path, load_history, safe_user_id, save_history
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
    append_word_to_csv,
    clean_form_value,
    load_base_words,
    prepare_words,
    quality_report,
    validate_new_word,
)

TEN_QUESTION_MODE = "10問連続"
CARD_MODE = "カード"
WEAK_PRIORITY_DEFAULT = True


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
