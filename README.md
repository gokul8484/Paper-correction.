# 🎓 SmartEval – AI-Based Handwritten Exam Paper Correction System

SmartEval reads handwritten answer sheets, converts them to text, compares each answer with the
teacher's reference answer, **suggests marks with reasons**, and lets the teacher review, edit and
approve before generating a marksheet (PDF / CSV).

## Features
- Teacher login, dashboard (exams, sheets evaluated, approved)
- Create exams: questions, reference answers, keywords, max marks
- Upload sheets (PNG / JPG / PDF); OpenCV preprocessing + OCR (TrOCR)
- Edit OCR text before evaluation
- Transparent scoring: **50 % semantic similarity + 35 % keyword match + 15 % completeness**
- Matched concepts, missing points, unanswered detection, partial marks
- Teacher can override marks, then approve; export marksheet PDF / exam CSV

## Architecture
```
Browser (HTML/CSS/JS) → Flask routes → services/
                                        ├─ ocr.py        OpenCV → line split → TrOCR (or demo)
                                        ├─ segmenter.py  splits text into Q1, Q2 ... answers
                                        ├─ evaluator.py  similarity + keywords + completeness → marks
                                        └─ reports.py    CSV / PDF
                         SQLite (teachers, exams, questions, sheets, answers)
```

## Folder structure
```
smarteval/
├── wsgi.py  Procfile  render.yaml  requirements.txt  requirements-ml.txt
├── .env.example  .gitignore  README.md
├── smarteval/ (app package: __init__, config, db, schema.sql, routes, seed, services/, templates/, static/)
├── tests/test_core.py
├── sample_data/   (fake sample answers + generated sample image)
├── scripts/make_sample_sheets.py
└── docs/screenshots/
```

## Database schema
`teachers(id, username, password_hash)` →
`exams(id, teacher_id, title, subject)` →
`questions(id, exam_id, number, text, reference_answer, keywords, max_marks)`;
`sheets(id, exam_id, student_name, roll_no, raw_ocr, status)` →
`answers(id, sheet_id, question_id, text, semantic, keyword, completeness, ai_marks, final_marks, matched, missing, feedback)`.
See `smarteval/schema.sql`.

## Run locally
```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # Windows: copy .env.example .env
python wsgi.py                    # open http://127.0.0.1:5000
```
Demo login: **teacher / teacher123** (a sample exam is pre-loaded).

### Quick demo (2 minutes)
1. Log in → open *Unit Test 1 (Sample)* → **Upload answer sheet**.
2. Upload `sample_data/student_good.txt` (or `student_average.txt`, `student_weak.txt`).
3. Review/edit the extracted text → **Evaluate** → see marks, matched/missing concepts.
4. Change a mark → **Approve** → download PDF / CSV.

### Real handwriting recognition (optional, heavy)
```bash
pip install -r requirements-ml.txt
# in .env:  OCR_ENGINE=trocr   EVAL_ENGINE=transformer
```
| Mode | Pros | Cons |
|---|---|---|
| `demo` / `light` | Instant, tiny, free-tier friendly | Demo OCR is simulated; TF-IDF can't fully understand paraphrases |
| `trocr` / `transformer` | Real OCR, true semantic matching | ~2 GB RAM, ~1 GB download, slow on CPU, TrOCR works best on neat single lines |

## Tests
```bash
python -m unittest discover -s tests -v
```

## GitHub
```bash
git init
git add .
git commit -m "Initial commit: SmartEval"
git branch -M main
git remote add origin https://github.com/<your-username>/smarteval.git
git push -u origin main
```
Never commit `.env`, databases, or real student sheets (already in `.gitignore`).

## Deploy on Render
1. Push the repo to GitHub.
2. Render dashboard → **New → Blueprint** (uses `render.yaml`) or **New → Web Service**.
3. Build: `pip install -r requirements.txt` · Start: `gunicorn wsgi:app --workers 1 --timeout 120`
4. Environment: `SECRET_KEY` (random), `OCR_ENGINE=demo`, `EVAL_ENGINE=light`, `DEMO_MODE=1`, `DATABASE_PATH=/tmp/smarteval.db`, `PYTHON_VERSION=3.11.9`.
5. Test: open `https://<app>.onrender.com/health` → `{"status":"ok"}`, then log in and repeat the quick demo.

> Uploaded files are processed in memory and **never saved to disk**. Render's free disk is
> temporary, so the SQLite data resets on redeploy. For permanent data use a Render Disk
> (set `DATABASE_PATH` to the mount path) or move to PostgreSQL.
> Turn `DEMO_MODE=0` and register your own teacher account for real use.

## Screenshots
Add images to `docs/screenshots/` and link them here:
`![Dashboard](docs/screenshots/dashboard.png)` · `![Results](docs/screenshots/results.png)`

## Future enhancements
PostgreSQL, student login, diagram/maths answers, multi-page auto-matching, better handwriting
model fine-tuning, plagiarism check, analytics charts, email results, role-based admin.

## Limitations (be honest in your viva)
OCR accuracy depends on handwriting quality; AI marks are *suggestions* – the teacher always
approves. Light mode uses TF-IDF, not deep semantics.
