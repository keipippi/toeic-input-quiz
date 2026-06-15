import random
import re
import unicodedata
from datetime import datetime

import pandas as pd

from words import split_answers


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", str(text)).strip().lower()
    text = re.sub(r"[、，,／/・\s\n\t]+", "", text)
    text = text.replace("すること", "する")
    text = text.replace("です", "").replace("ます", "")
    text = text.replace("を", "").replace("が", "").replace("に", "").replace("へ", "")
    return text


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
        h["timestamp_dt"] = pd.to_datetime(h["timestamp"], errors="coerce")
        h["next_review_dt"] = pd.to_datetime(h["next_review"], errors="coerce").dt.date
        latest = h.sort_values("timestamp_dt").drop_duplicates("word", keep="last")
        words = latest.loc[latest["next_review_dt"].le(today), "word"].unique().tolist()
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
