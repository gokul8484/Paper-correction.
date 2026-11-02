"""Split OCR text into answers: finds markers like 'Q1', 'Q.2)', 'Ans 3', '4.'"""
import re

STRICT = re.compile(r"^\s*(?:(?:q(?:uestion)?|ans(?:wer)?)\.?\s*(\d{1,2})|(\d{1,2})(?=\s*[\.\)]))"
                    r"\s*[\.\):\-]?\s*(.*)$", re.IGNORECASE)


def segment_answers(text: str, question_numbers):
    """Return {question_number: answer_text}. Missing questions -> ''."""
    result = {n: "" for n in question_numbers}
    current = None
    for line in (text or "").splitlines():
        m = STRICT.match(line)
        if m:
            num = int(m.group(1) or m.group(2))
            if num in result:
                current = num
                result[current] += m.group(3).strip() + " "
                continue
        if current is not None and line.strip():
            result[current] += line.strip() + " "
    return {k: v.strip() for k, v in result.items()}
