"""Run with:  python -m unittest discover -s tests -v"""
import os
import re
import tempfile
import unittest

from smarteval import create_app
from smarteval.services.evaluator import (evaluate_answer, keyword_match, round_half)
from smarteval.services.ocr import extract_text, preprocess_image, split_lines
from smarteval.services.segmenter import segment_answers
from smarteval.services.text_utils import split_keywords, stem

REF = ("Photosynthesis is the process in which green plants use sunlight, water and carbon dioxide "
       "to produce glucose and release oxygen using chlorophyll.")
KW = "sunlight, carbon dioxide, water, chlorophyll, oxygen, glucose"


class EvaluatorTests(unittest.TestCase):
    def test_round_half(self):
        self.assertEqual(round_half(2.3), 2.5)
        self.assertEqual(round_half(2.2), 2.0)

    def test_keywords_and_stemming(self):
        m, miss = keyword_match("Plants use sunlight and release oxygen", split_keywords(KW))
        self.assertIn("sunlight", m)
        self.assertIn("oxygen", m)
        self.assertIn("chlorophyll", miss)
        self.assertEqual(stem("inheriting"), "inherit")

    def test_good_answer_beats_weak_answer(self):
        good = evaluate_answer("Green plants use sunlight, water and carbon dioxide to make glucose "
                               "and give out oxygen with chlorophyll.", REF, KW, 5)
        weak = evaluate_answer("Plants grow in soil and need care every day.", REF, KW, 5)
        self.assertGreater(good["ai_marks"], weak["ai_marks"])
        self.assertGreaterEqual(good["ai_marks"], 4)
        self.assertLessEqual(weak["ai_marks"], 2)

    def test_unanswered(self):
        r = evaluate_answer("", REF, KW, 5)
        self.assertFalse(r["answered"])
        self.assertEqual(r["ai_marks"], 0)

    def test_marks_never_exceed_max(self):
        r = evaluate_answer(REF, REF, KW, 3)
        self.assertLessEqual(r["ai_marks"], 3)
        self.assertEqual(r["ai_marks"], 3)

    def test_paraphrase_gets_partial_credit(self):
        r = evaluate_answer("Using light from the sun, water and CO2 gas, leaves make sugar and "
                            "release oxygen.", REF, KW, 5)
        self.assertGreater(r["ai_marks"], 0)


class SegmenterTests(unittest.TestCase):
    def test_basic_split(self):
        text = "Q1. first answer\ncontinues here\nQ2) second answer\nAns 3: third"
        r = segment_answers(text, [1, 2, 3, 4])
        self.assertEqual(r[1], "first answer continues here")
        self.assertEqual(r[2], "second answer")
        self.assertEqual(r[3], "third")
        self.assertEqual(r[4], "")

    def test_number_style(self):
        r = segment_answers("1. alpha\n2. beta", [1, 2])
        self.assertEqual((r[1], r[2]), ("alpha", "beta"))


class OcrTests(unittest.TestCase):
    def test_txt_upload(self):
        self.assertEqual(extract_text("a.txt", b"Q1. hello", "demo"), "Q1. hello")

    def test_demo_image_returns_sample(self):
        sample = os.path.join(os.path.dirname(__file__), "..", "sample_data", "sample_sheet_1.png")
        with open(sample, "rb") as f:
            text = extract_text("x.png", f.read(), "demo")
        self.assertIn("Q1", text)

    def test_bad_image_rejected(self):
        with self.assertRaises(ValueError):
            extract_text("bad.png", b"not an image", "demo")

    def test_preprocess_and_lines(self):
        import numpy as np
        img = np.full((200, 400, 3), 255, np.uint8)
        img[40:70, 20:380] = 0
        img[120:150, 20:380] = 0
        binary = preprocess_image(img)
        self.assertEqual(len(split_lines(binary)), 2)


class AppFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({"TESTING": True, "DATABASE_PATH": os.path.join(self.tmp, "t.db"),
                               "DEMO_MODE": True, "OCR_ENGINE": "demo", "EVAL_ENGINE": "light"})
        self.c = self.app.test_client()

    def csrf(self, path="/login"):
        html = self.c.get(path).get_data(as_text=True)
        return re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    def login(self):
        return self.c.post("/login", data={"csrf": self.csrf(), "username": "teacher",
                                           "password": "teacher123"}, follow_redirects=True)

    def test_requires_login(self):
        self.assertEqual(self.c.get("/dashboard").status_code, 302)

    def test_wrong_password(self):
        r = self.c.post("/login", data={"csrf": self.csrf(), "username": "teacher", "password": "x"})
        self.assertIn("Invalid username", r.get_data(as_text=True))

    def test_csrf_blocked(self):
        self.assertEqual(self.c.post("/login", data={"username": "a", "password": "b"}).status_code, 400)

    def test_full_flow(self):
        self.assertIn("Teacher Dashboard", self.login().get_data(as_text=True))
        token = self.csrf("/exams/1/upload")
        sample = os.path.join(os.path.dirname(__file__), "..", "sample_data", "student_good.txt")
        with open(sample, "rb") as f:
            r = self.c.post("/exams/1/upload", data={"csrf": token, "student_name": "Asha",
                            "roll_no": "101", "sheet": (f, "student_good.txt")},
                            content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("Review extracted text", r.get_data(as_text=True))
        # evaluate (submit review form unchanged)
        db_rows = self.app.test_request_context()
        with self.app.app_context():
            from smarteval.db import get_db
            ids = [x["id"] for x in get_db().execute("SELECT id FROM answers ORDER BY id")]
        form = {"csrf": token}
        form.update({f"text_{i}": "" for i in ids})
        r = self.c.post("/sheets/1/review", data=form, follow_redirects=True)  # blanks -> unanswered
        self.assertIn("Evaluation results", r.get_data(as_text=True))
        self.assertIn("not answered", r.get_data(as_text=True))
        # approve with invalid then valid marks
        bad = {"csrf": token, **{f"marks_{i}": "999" for i in ids}}
        r = self.c.post("/sheets/1/results", data=bad, follow_redirects=True)
        self.assertIn("must be between", r.get_data(as_text=True))
        ok = {"csrf": token, **{f"marks_{i}": "4" for i in ids}}
        r = self.c.post("/sheets/1/results", data=ok, follow_redirects=True)
        self.assertIn("Student marksheet", r.get_data(as_text=True))
        pdf = self.c.get("/sheets/1/marksheet.pdf")
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        csv = self.c.get("/exams/1/export.csv").get_data(as_text=True)
        self.assertIn("Asha", csv)
        self.assertIn("12", csv)

    def test_invalid_upload_type(self):
        self.login()
        token = self.csrf("/exams/1/upload")
        import io
        r = self.c.post("/exams/1/upload", data={"csrf": token, "student_name": "A", "roll_no": "1",
                        "sheet": (io.BytesIO(b"x"), "evil.exe")}, content_type="multipart/form-data")
        self.assertIn("Allowed file types", r.get_data(as_text=True))

    def test_create_exam_validation(self):
        self.login()
        token = self.csrf("/exams/new")
        r = self.c.post("/exams/new", data={"csrf": token, "title": "T", "subject": "S",
                        "q_text": "Q?", "q_ref": "ans", "q_kw": "", "q_max": "abc"})
        self.assertEqual(r.status_code, 400)
        r = self.c.post("/exams/new", data={"csrf": token, "title": "T", "subject": "S",
                        "q_text": "Q?", "q_ref": "ans", "q_kw": "k", "q_max": "5"})
        self.assertEqual(r.status_code, 302)


if __name__ == "__main__":
    unittest.main()
