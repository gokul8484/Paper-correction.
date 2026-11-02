"""All web routes. Teachers can only see their own exams."""
import functools
import secrets
from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .services import ocr, reports
from .services.evaluator import evaluate_answer
from .services.segmenter import segment_answers

bp = Blueprint("main", __name__)


# ---------- helpers ----------
@bp.app_context_processor
def inject_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return {"csrf_token": session["csrf"]}


@bp.before_app_request
def check_csrf():
    token = session.get("csrf")
    if request.method == "POST" and (not token or request.form.get("csrf") != token):
        abort(400, "Invalid form token. Reload the page and try again.")


def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        if "teacher_id" not in session:
            return redirect(url_for("main.login"))
        return view(*a, **kw)
    return wrapped


def get_exam(exam_id):
    exam = get_db().execute("SELECT * FROM exams WHERE id=? AND teacher_id=?",
                            (exam_id, session["teacher_id"])).fetchone()
    if exam is None:
        abort(404)
    return exam


def get_questions(exam_id):
    return get_db().execute("SELECT * FROM questions WHERE exam_id=? ORDER BY number",
                            (exam_id,)).fetchall()


def get_sheet(sheet_id):
    sheet = get_db().execute("SELECT * FROM sheets WHERE id=?", (sheet_id,)).fetchone()
    if sheet is None:
        abort(404)
    return sheet, get_exam(sheet["exam_id"])


def sheet_rows(sheet_id):
    return get_db().execute(
        "SELECT a.*, q.number, q.text AS question, q.max_marks, q.reference_answer, q.keywords "
        "FROM answers a JOIN questions q ON q.id=a.question_id "
        "WHERE a.sheet_id=? ORDER BY q.number", (sheet_id,)).fetchall()


def sheet_total(sheet_id):
    rows = sheet_rows(sheet_id)
    return (sum(reports.final_mark(r) for r in rows), sum(r["max_marks"] for r in rows))


def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


def evaluate_sheet(sheet_id):
    """(Re)run AI evaluation on every answer of a sheet. Keeps teacher overrides cleared."""
    db = get_db()
    engine = current_app.config["EVAL_ENGINE"]
    for r in sheet_rows(sheet_id):
        res = evaluate_answer(r["text"], r["reference_answer"], r["keywords"], r["max_marks"], engine)
        db.execute("UPDATE answers SET semantic=?, keyword=?, completeness=?, ai_marks=?, "
                   "matched=?, missing=?, feedback=?, final_marks=NULL WHERE id=?",
                   (res["semantic"], res["keyword"], res["completeness"], res["ai_marks"],
                    "; ".join(res["matched"]), "; ".join(res["missing"]), res["feedback"], r["id"]))
    db.execute("UPDATE sheets SET status='evaluated' WHERE id=?", (sheet_id,))
    db.commit()


# ---------- auth ----------
@bp.route("/")
def index():
    return redirect(url_for("main.dashboard" if "teacher_id" in session else "main.login"))


@bp.route("/health")
def health():
    return {"status": "ok"}


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pw = request.form.get("password", "")
        row = get_db().execute("SELECT * FROM teachers WHERE username=?", (user,)).fetchone()
        if row and check_password_hash(row["password_hash"], pw):
            session.clear()
            session["teacher_id"], session["username"] = row["id"], row["username"]
            return redirect(url_for("main.dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pw = request.form.get("password", "")
        if len(user) < 3 or len(pw) < 6:
            flash("Username needs 3+ characters and password 6+ characters.", "error")
        elif get_db().execute("SELECT 1 FROM teachers WHERE username=?", (user,)).fetchone():
            flash("Username already taken.", "error")
        else:
            get_db().execute("INSERT INTO teachers(username,password_hash) VALUES (?,?)",
                             (user, generate_password_hash(pw)))
            get_db().commit()
            flash("Account created. Please log in.", "success")
            return redirect(url_for("main.login"))
    return render_template("register.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("main.login"))


# ---------- dashboard & exams ----------
@bp.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    tid = session["teacher_id"]
    exams = db.execute(
        "SELECT e.*, (SELECT COUNT(*) FROM sheets s WHERE s.exam_id=e.id) AS n_sheets, "
        "(SELECT COUNT(*) FROM questions q WHERE q.exam_id=e.id) AS n_q FROM exams e "
        "WHERE e.teacher_id=? ORDER BY e.id DESC", (tid,)).fetchall()
    sheets = db.execute(
        "SELECT s.*, e.title FROM sheets s JOIN exams e ON e.id=s.exam_id "
        "WHERE e.teacher_id=? ORDER BY s.id DESC LIMIT 15", (tid,)).fetchall()
    totals = {s["id"]: sheet_total(s["id"]) for s in sheets}
    stats = {"exams": len(exams),
             "sheets": db.execute("SELECT COUNT(*) FROM sheets s JOIN exams e ON e.id=s.exam_id "
                                  "WHERE e.teacher_id=?", (tid,)).fetchone()[0],
             "evaluated": db.execute("SELECT COUNT(*) FROM sheets s JOIN exams e ON e.id=s.exam_id "
                                     "WHERE e.teacher_id=? AND s.status!='uploaded'", (tid,)).fetchone()[0],
             "approved": db.execute("SELECT COUNT(*) FROM sheets s JOIN exams e ON e.id=s.exam_id "
                                    "WHERE e.teacher_id=? AND s.status='approved'", (tid,)).fetchone()[0]}
    return render_template("dashboard.html", exams=exams, sheets=sheets, totals=totals, stats=stats)


def parse_questions(form):
    """Read repeated form fields q_text, q_ref, q_kw, q_max. Returns (list, error)."""
    texts, refs = form.getlist("q_text"), form.getlist("q_ref")
    kws, maxes = form.getlist("q_kw"), form.getlist("q_max")
    out = []
    for i, (t, r, k, m) in enumerate(zip(texts, refs, kws, maxes), start=1):
        if not (t.strip() or r.strip()):
            continue
        try:
            mx = float(m)
        except ValueError:
            return None, f"Question {i}: maximum marks must be a number."
        if not t.strip() or not r.strip():
            return None, f"Question {i}: question text and reference answer are required."
        if mx <= 0 or mx > 100:
            return None, f"Question {i}: maximum marks must be between 0 and 100."
        out.append((t.strip(), r.strip(), k.strip(), mx))
    if not out:
        return None, "Add at least one question."
    return out, None


@bp.route("/exams/new", methods=["GET", "POST"])
@login_required
def exam_new():
    if request.method == "POST":
        title, subject = request.form.get("title", "").strip(), request.form.get("subject", "").strip()
        questions, err = parse_questions(request.form)
        if not title or not subject:
            err = "Exam title and subject are required."
        if err:
            flash(err, "error")
            return render_template("exam_new.html", form=request.form), 400
        db = get_db()
        eid = db.execute("INSERT INTO exams(teacher_id,title,subject) VALUES (?,?,?)",
                         (session["teacher_id"], title, subject)).lastrowid
        for n, (t, r, k, m) in enumerate(questions, start=1):
            db.execute("INSERT INTO questions(exam_id,number,text,reference_answer,keywords,max_marks)"
                       " VALUES (?,?,?,?,?,?)", (eid, n, t, r, k, m))
        db.commit()
        flash("Exam created.", "success")
        return redirect(url_for("main.exam_detail", exam_id=eid))
    return render_template("exam_new.html", form={})


@bp.route("/exams/<int:exam_id>")
@login_required
def exam_detail(exam_id):
    exam = get_exam(exam_id)
    questions = get_questions(exam_id)
    sheets = get_db().execute("SELECT * FROM sheets WHERE exam_id=? ORDER BY roll_no", (exam_id,)).fetchall()
    totals = {s["id"]: sheet_total(s["id"]) for s in sheets}
    return render_template("exam_detail.html", exam=exam, questions=questions, sheets=sheets,
                           totals=totals, max_total=sum(q["max_marks"] for q in questions))


@bp.route("/exams/<int:exam_id>/delete", methods=["POST"])
@login_required
def exam_delete(exam_id):
    get_exam(exam_id)
    get_db().execute("DELETE FROM exams WHERE id=?", (exam_id,))
    get_db().commit()
    flash("Exam deleted.", "success")
    return redirect(url_for("main.dashboard"))


# ---------- upload & OCR ----------
@bp.route("/exams/<int:exam_id>/upload", methods=["GET", "POST"])
@login_required
def upload(exam_id):
    exam = get_exam(exam_id)
    questions = get_questions(exam_id)
    if request.method == "POST":
        name, roll = request.form.get("student_name", "").strip(), request.form.get("roll_no", "").strip()
        file = request.files.get("sheet")
        if not name or not roll:
            flash("Student name and roll number are required.", "error")
        elif file is None or file.filename == "":
            flash("Please choose a file.", "error")
        elif not allowed(file.filename):
            flash("Allowed file types: PNG, JPG, PDF (or TXT for demo).", "error")
        else:
            try:
                text = ocr.extract_text(file.filename, file.read(), current_app.config["OCR_ENGINE"])
            except Exception as exc:  # show a friendly message instead of a crash page
                flash(f"Could not read the file: {exc}", "error")
                return render_template("upload.html", exam=exam), 400
            db = get_db()
            sid = db.execute("INSERT INTO sheets(exam_id,student_name,roll_no,raw_ocr) VALUES (?,?,?,?)",
                             (exam_id, name, roll, text)).lastrowid
            parts = segment_answers(text, [q["number"] for q in questions])
            for q in questions:
                db.execute("INSERT INTO answers(sheet_id,question_id,text) VALUES (?,?,?)",
                           (sid, q["id"], parts.get(q["number"], "")))
            db.commit()
            return redirect(url_for("main.review", sheet_id=sid))
    return render_template("upload.html", exam=exam)


@bp.route("/sheets/<int:sheet_id>/review", methods=["GET", "POST"])
@login_required
def review(sheet_id):
    sheet, exam = get_sheet(sheet_id)
    if request.method == "POST":
        db = get_db()
        for r in sheet_rows(sheet_id):
            new_text = request.form.get(f"text_{r['id']}", "").strip()
            db.execute("UPDATE answers SET text=? WHERE id=?", (new_text, r["id"]))
        db.commit()
        evaluate_sheet(sheet_id)
        return redirect(url_for("main.results", sheet_id=sheet_id))
    return render_template("review.html", sheet=sheet, exam=exam, rows=sheet_rows(sheet_id))


# ---------- results / approval ----------
@bp.route("/sheets/<int:sheet_id>/results", methods=["GET", "POST"])
@login_required
def results(sheet_id):
    sheet, exam = get_sheet(sheet_id)
    if request.method == "POST":
        db = get_db()
        for r in sheet_rows(sheet_id):
            raw = request.form.get(f"marks_{r['id']}", "").strip()
            try:
                val = float(raw)
            except ValueError:
                flash(f"Q{r['number']}: marks must be a number.", "error")
                return redirect(url_for("main.results", sheet_id=sheet_id))
            if val < 0 or val > r["max_marks"]:
                flash(f"Q{r['number']}: marks must be between 0 and {r['max_marks']:g}.", "error")
                return redirect(url_for("main.results", sheet_id=sheet_id))
            db.execute("UPDATE answers SET final_marks=? WHERE id=?", (val, r["id"]))
        db.execute("UPDATE sheets SET status='approved' WHERE id=?", (sheet_id,))
        db.commit()
        flash("Marks approved and saved.", "success")
        return redirect(url_for("main.marksheet", sheet_id=sheet_id))
    total, max_total = sheet_total(sheet_id)
    return render_template("results.html", sheet=sheet, exam=exam, rows=sheet_rows(sheet_id),
                           total=total, max_total=max_total)


@bp.route("/sheets/<int:sheet_id>/marksheet")
@login_required
def marksheet(sheet_id):
    sheet, exam = get_sheet(sheet_id)
    total, max_total = sheet_total(sheet_id)
    return render_template("marksheet.html", sheet=sheet, exam=exam, rows=sheet_rows(sheet_id),
                           total=total, max_total=max_total, final_mark=reports.final_mark)


@bp.route("/sheets/<int:sheet_id>/marksheet.pdf")
@login_required
def marksheet_pdf(sheet_id):
    sheet, exam = get_sheet(sheet_id)
    total, max_total = sheet_total(sheet_id)
    rows = [{"number": r["number"], "marks": reports.final_mark(r), "max_marks": r["max_marks"],
             "feedback": r["feedback"]} for r in sheet_rows(sheet_id)]
    pdf = reports.sheet_pdf(exam, sheet, rows, total, max_total)
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=marksheet_{sheet['roll_no']}.pdf"})


@bp.route("/exams/<int:exam_id>/export.csv")
@login_required
def export_csv(exam_id):
    exam = get_exam(exam_id)
    questions = get_questions(exam_id)
    db = get_db()
    out = []
    for s in db.execute("SELECT * FROM sheets WHERE exam_id=? ORDER BY roll_no", (exam_id,)):
        rows = {r["question_id"]: reports.final_mark(r) for r in sheet_rows(s["id"])}
        marks = [rows.get(q["id"], 0) for q in questions]
        out.append((s, marks, sum(marks)))
    csv_text = reports.exam_csv(exam, questions, out)
    return Response(csv_text, mimetype="text/csv", headers={
        "Content-Disposition": f"attachment; filename=exam_{exam_id}_marks.csv"})


@bp.app_errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, message="Page not found."), 404


@bp.app_errorhandler(400)
def bad_request(e):
    return render_template("error.html", code=400, message=getattr(e, "description", "Bad request")), 400


@bp.app_errorhandler(413)
def too_large(_e):
    return render_template("error.html", code=413, message="File too large (max 10 MB)."), 413
