"""Small text helpers shared by the evaluator and segmenter."""
import re

STOPWORDS = set("""a an the is are was were be been being of to in on at for and or but with by from as
that this these those it its into than then so such can may will would should could has have had do does
did not no which who whom what when where why how also very more most some any each other their there
they them we you i he she his her our your""".split())


def stem(word: str) -> str:
    """Very simple stemmer so 'inheriting' ~ 'inherits' ~ 'inherit'."""
    for suffix in ("ing", "ed", "es", "s", "ly"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def tokens(text: str):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [stem(w) for w in words if w not in STOPWORDS]


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+", text or ""))


def split_keywords(raw: str):
    """'inheritance, polymorphism ; base class' -> list"""
    parts = re.split(r"[,;\n]", raw or "")
    return [p.strip() for p in parts if p.strip()]
