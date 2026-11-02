"""CSV and PDF marksheet generation (all in memory)."""
import csv
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def final_mark(row):
    return row["final_marks"] if row["final_marks"] is not None else row["ai_marks"]


def exam_csv(exam, questions, sheets_with_marks) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Roll No", "Student"] + [f"Q{q['number']} (/{q['max_marks']:g})" for q in questions]
               + ["Total", f"Out of {sum(q['max_marks'] for q in questions):g}", "Status"])
    for s, marks, total in sheets_with_marks:
        w.writerow([s["roll_no"], s["student_name"]] + [f"{m:g}" for m in marks]
                   + [f"{total:g}", "", s["status"]])
    return buf.getvalue()


def sheet_pdf(exam, sheet, rows, total, max_total) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="SmartEval Marksheet")
    st = getSampleStyleSheet()
    el = [Paragraph("SmartEval – Marksheet", st["Title"]),
          Paragraph(f"<b>Exam:</b> {exam['title']} ({exam['subject']})", st["Normal"]),
          Paragraph(f"<b>Student:</b> {sheet['student_name']} &nbsp; <b>Roll No:</b> {sheet['roll_no']}",
                    st["Normal"]),
          Paragraph(f"<b>Status:</b> {sheet['status']}", st["Normal"]), Spacer(1, 14)]
    data = [["Q", "Marks", "Max", "Feedback"]]
    for r in rows:
        data.append([f"Q{r['number']}", f"{r['marks']:g}", f"{r['max_marks']:g}",
                     Paragraph(r["feedback"] or "-", st["BodyText"])])
    data.append(["Total", f"{total:g}", f"{max_total:g}", ""])
    t = Table(data, colWidths=[40, 50, 40, 380], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
    el.append(t)
    doc.build(el)
    return buf.getvalue()
