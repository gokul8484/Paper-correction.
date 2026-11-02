"""
Transparent scoring:

    score = 0.50 * semantic + 0.35 * keyword + 0.15 * completeness

semantic     : meaning similarity between student and reference answer (0-1)
keyword      : fraction of important keywords/concepts found (0-1)
completeness : answer length compared with reference answer length (0-1)

marks = round_to_half(score * max_marks)
"""
from .text_utils import tokens, word_count, split_keywords

W_SEMANTIC, W_KEYWORD, W_COMPLETE = 0.50, 0.35, 0.15
UNANSWERED_MIN_WORDS = 3

_model_cache = {}


def _similarity_light(a: str, b: str) -> float:
    """TF-IDF cosine on word + character n-grams. No download needed."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    ta, tb = " ".join(tokens(a)), " ".join(tokens(b))
    if not ta or not tb:
        return 0.0
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
    m = vec.fit_transform([ta, tb])
    return float(cosine_similarity(m[0], m[1])[0][0])


def _similarity_transformer(a: str, b: str) -> float:
    """Sentence-Transformers (all-MiniLM-L6-v2, ~90 MB). Understands paraphrases."""
    from sentence_transformers import SentenceTransformer, util
    if "st" not in _model_cache:
        _model_cache["st"] = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    emb = _model_cache["st"].encode([a, b], convert_to_tensor=True)
    cos = float(util.cos_sim(emb[0], emb[1]))
    # Raw cosine of related answers is usually 0.3-0.85; stretch to 0-1.
    return max(0.0, min(1.0, (cos - 0.25) / 0.6))


def semantic_similarity(student: str, reference: str, engine: str = "light") -> float:
    if engine == "transformer":
        try:
            return _similarity_transformer(student, reference)
        except Exception:  # model missing -> fall back instead of crashing
            pass
    return max(0.0, min(1.0, _similarity_light(student, reference)))


def keyword_match(student: str, keywords):
    """Return (matched, missing). A keyword matches if all its (stemmed) words appear."""
    student_tokens = set(tokens(student))
    matched, missing = [], []
    for kw in keywords:
        kw_tokens = tokens(kw)
        if kw_tokens and all(t in student_tokens for t in kw_tokens):
            matched.append(kw)
        else:
            missing.append(kw)
    return matched, missing


def completeness(student: str, reference: str) -> float:
    ref_len = max(word_count(reference), 1)
    return min(1.0, word_count(student) / (0.8 * ref_len))


def round_half(x: float) -> float:
    return round(x * 2) / 2


def evaluate_answer(student: str, reference: str, keywords_raw: str, max_marks: float,
                    engine: str = "light") -> dict:
    keywords = split_keywords(keywords_raw)
    student = (student or "").strip()

    if word_count(student) < UNANSWERED_MIN_WORDS:
        return {"semantic": 0.0, "keyword": 0.0, "completeness": 0.0, "ai_marks": 0.0,
                "matched": [], "missing": keywords, "answered": False,
                "feedback": "Question not answered (no meaningful text found)."}

    sem = semantic_similarity(student, reference, engine)
    matched, missing = keyword_match(student, keywords)
    kw = len(matched) / len(keywords) if keywords else sem   # no keywords -> use semantic
    comp = completeness(student, reference)
    score = W_SEMANTIC * sem + W_KEYWORD * kw + W_COMPLETE * comp
    marks = min(max_marks, round_half(score * max_marks))

    return {"semantic": round(sem, 3), "keyword": round(kw, 3), "completeness": round(comp, 3),
            "ai_marks": marks, "matched": matched, "missing": missing, "answered": True,
            "feedback": build_feedback(sem, matched, missing, comp, score)}


def build_feedback(sem, matched, missing, comp, score) -> str:
    parts = []
    if sem >= 0.7:
        parts.append("Meaning closely matches the reference answer.")
    elif sem >= 0.4:
        parts.append("Answer is partly related to the reference answer.")
    else:
        parts.append("Answer differs a lot from the reference answer.")
    if matched:
        parts.append("Covered concepts: " + ", ".join(matched) + ".")
    if missing:
        parts.append("Missing key points: " + ", ".join(missing) + ".")
    if comp < 0.5:
        parts.append("Answer is too short / incomplete.")
    parts.append(f"Overall score {score * 100:.0f}%.")
    return " ".join(parts)
