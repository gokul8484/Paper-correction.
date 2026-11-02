"""Demo data: one teacher + a sample exam with 3 questions."""
from werkzeug.security import generate_password_hash

SAMPLE_QUESTIONS = [
    (1, "Explain photosynthesis.",
     "Photosynthesis is the process in which green plants use sunlight, water and carbon dioxide "
     "to produce glucose and release oxygen. It takes place in chloroplasts using chlorophyll.",
     "sunlight, carbon dioxide, water, chlorophyll, oxygen, glucose", 5),
    (2, "What is a CPU? Describe its main parts.",
     "The CPU (Central Processing Unit) is the brain of the computer that executes instructions. "
     "Its main parts are the Arithmetic Logic Unit for calculations, the Control Unit that directs "
     "operations, and registers for fast temporary storage.",
     "brain, instructions, ALU, control unit, registers", 5),
    (3, "Define an operating system and give two examples.",
     "An operating system is system software that manages hardware and software resources and "
     "provides services to programs. Examples are Windows, Linux and Android.",
     "system software, manages, hardware, Windows, Linux", 5),
]


def seed_demo(db, username, password):
    if db.execute("SELECT 1 FROM teachers WHERE username=?", (username,)).fetchone():
        return
    cur = db.execute("INSERT INTO teachers(username, password_hash) VALUES (?,?)",
                     (username, generate_password_hash(password)))
    tid = cur.lastrowid
    ex = db.execute("INSERT INTO exams(teacher_id,title,subject) VALUES (?,?,?)",
                    (tid, "Unit Test 1 (Sample)", "General Science & Computing")).lastrowid
    for n, text, ref, kw, mx in SAMPLE_QUESTIONS:
        db.execute("INSERT INTO questions(exam_id,number,text,reference_answer,keywords,max_marks) "
                   "VALUES (?,?,?,?,?,?)", (ex, n, text, ref, kw, mx))
    db.commit()
