import difflib

from . import db, llm

OPEN_STATUSES = ("confirmed", "assessing", "scheduled", "developing")


def _ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def _shortlist(title, description, limit=5):
    placeholders = ",".join("?" for _ in OPEN_STATUSES)
    rows = db.query(
        f"SELECT id, req_no, title, description, status FROM requirements WHERE status IN ({placeholders})",
        OPEN_STATUSES,
    )
    target = (title or "") + (description or "")
    scored = []
    for row in rows:
        cand = (row["title"] or "") + (row["description"] or "")
        score = max(_ratio(title or "", row["title"] or ""), _ratio(target, cand))
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]


def find_similar(title, description, threshold):
    candidates = _shortlist(title, description)
    if not candidates:
        return None
    if db.get_config("model_api_key"):
        best_text_score = candidates[0][0]
        if best_text_score < 0.3:
            return None
        judged = llm.judge_similar(
            title or "",
            description or "",
            [{"req_no": r["req_no"], "title": r["title"], "description": r["description"]} for _, r in candidates],
        )
        if judged is not None and 0 <= judged["index"] < len(candidates) and judged["score"] >= threshold:
            return {"requirement": candidates[judged["index"]][1], "score": round(judged["score"], 2)}
        return None
    effective = min(threshold, 0.5)
    best_score, best = candidates[0]
    if best_score >= effective:
        return {"requirement": best, "score": round(best_score, 2)}
    return None
