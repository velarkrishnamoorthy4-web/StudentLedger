from flask import Flask, render_template, jsonify, request
import mysql.connector
import os
import hmac

app = Flask(__name__)


def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="student_ledger"
    )


@app.route("/")
def home():
    return render_template("index.html")


# Get all students
@app.route("/api/students", methods=["GET"])
def get_students():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT student_id, student_name, roll_no
            FROM students
            ORDER BY student_id ASC
        """)

        students = cursor.fetchall()
        return jsonify(students)

    finally:
        cursor.close()
        conn.close()
# Export student data for Google Sheets
@app.route("/api/students/export", methods=["GET"])
def export_students():
    expected_token = os.environ.get("STUDENTLEDGER_API_TOKEN", "")
    supplied_token = request.headers.get("X-API-Token", "")

    if not expected_token or not hmac.compare_digest(
        supplied_token, expected_token
    ):
        return jsonify({"message": "Unauthorized"}), 401
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                student_id,
                student_name,
                roll_no,
                branch,
                admission_year,
                email
            FROM students
            ORDER BY student_id ASC
        """)

        students = cursor.fetchall()
        return jsonify(students)

    except mysql.connector.Error:
        app.logger.exception("Student export API error")
        return jsonify({
            "success": False,
            "message": "Database error"
        }), 500

    finally:
        cursor.close()
        conn.close()


# Add a new student
@app.route("/api/students", methods=["POST"])
def add_student():
    data = request.get_json(silent=True) or {}

    student_name = str(data.get("student_name", "")).strip()
    roll_no = str(data.get("roll_no", "")).strip()
    branch = str(data.get("branch", "")).strip()
    admission_year = data.get("admission_year")
    email = str(data.get("email", "")).strip()

    if not student_name or not roll_no or not branch or not admission_year:
        return jsonify({
            "success": False,
            "message": "Please fill all required fields."
        }), 400

    try:
        admission_year = int(admission_year)

        if admission_year < 1900 or admission_year > 2100:
            raise ValueError

    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Enter a valid admission year."
        }), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Maximum 100 students
        cursor.execute("SELECT COUNT(*) AS total FROM students")
        total = cursor.fetchone()["total"]

        if total >= 100:
            return jsonify({
                "success": False,
                "message": "Maximum limit of 100 students reached."
            }), 400

        # Check duplicate roll number
        cursor.execute(
            "SELECT student_id FROM students WHERE roll_no = %s",
            (roll_no,)
        )

        if cursor.fetchone():
            return jsonify({
                "success": False,
                "message": "This roll number already exists."
            }), 409

        # Insert student
        cursor.execute("""
            INSERT INTO students
            (student_name, roll_no, branch, admission_year, email)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            student_name,
            roll_no,
            branch,
            admission_year,
            email or None
        ))

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Student added successfully!",
            "student_id": cursor.lastrowid
        }), 201

    except mysql.connector.Error:
        conn.rollback()
        app.logger.exception("Database error while adding student")

        return jsonify({
            "success": False,
            "message": "Database error. Check the Flask terminal."
        }), 500

    finally:
        cursor.close()
        conn.close()
# Get academic performance of a particular student
@app.route("/api/students/<int:student_id>/performance", methods=["GET"])
def get_student_performance(student_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT student_id, student_name, roll_no
            FROM students
            WHERE student_id = %s
        """, (student_id,))

        student = cursor.fetchone()

        if not student:
            return jsonify({
                "success": False,
                "message": "Student not found"
            }), 404

        cursor.execute("""
            SELECT semester, sgpa, cgpa
            FROM student_performance
            WHERE student_id = %s
            ORDER BY semester ASC
        """, (student_id,))

        performance = cursor.fetchall()

        return jsonify({
            "success": True,
            "student": student,
            "performance": performance
        })

    except mysql.connector.Error:
        app.logger.exception("Academic performance API error")
        return jsonify({
            "success": False,
            "message": "Database error. Check Flask terminal."
        }), 500

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    app.run(debug=False)