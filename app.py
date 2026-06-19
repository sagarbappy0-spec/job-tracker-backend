from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import mysql.connector
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)
bcrypt = Bcrypt(app)
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "supersecretkey")
jwt = JWTManager(app)

def get_db():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("MYSQLHOST"),
        user=os.environ.get("DB_USER") or os.environ.get("MYSQLUSER"),
        password=os.environ.get("DB_PASSWORD") or os.environ.get("MYSQLPASSWORD"),
        database=os.environ.get("DB_NAME") or os.environ.get("MYSQLDB"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("MYSQLPORT") or 3306)
    )

def send_email(to_email, subject, html_body):
    """Gmail SMTP দিয়ে একটা email পাঠায়"""
    try:
        sender_email = os.environ.get("EMAIL_USER")
        sender_password = os.environ.get("EMAIL_PASS")

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(html_body, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email send error for {to_email}: {e}")
        return False

@app.route('/')
def home():
    return jsonify({"status": "Backend is running!"})

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    conn = None
    cursor = None
    try:
        hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (data['username'], data['email'], hashed_pw)
        )
        conn.commit()
        return jsonify({"message": "User registered successfully"}), 201
    except Exception as e:
        return jsonify({"message": "User already exists"}), 400
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (data['email'],))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user and bcrypt.check_password_hash(user['password'], data['password']):
            token = create_access_token(identity=str(user['id']))
            return jsonify({"token": token}), 200
        return jsonify({"message": "Invalid credentials"}), 401
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/scrape')
def run_scrape():
    from scraper import scrape_all, save_jobs
    jobs = scrape_all()
    save_jobs(jobs)
    return jsonify({"message": f"Done! {len(jobs)} jobs scraped."})

@app.route('/jobs', methods=['GET'])
@jwt_required()
def get_jobs():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DELETE FROM jobs WHERE created_at < NOW() - INTERVAL 30 DAY")
        conn.commit()
        cursor.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 200")
        jobs = cursor.fetchall()
        return jsonify(jobs), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/setup-saved-jobs')
def setup_saved_jobs():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_jobs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                job_id INT NOT NULL,
                saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_save (user_id, job_id)
            )
        """)
        conn.commit()
        return jsonify({"message": "saved_jobs table created!"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/save-job/<int:job_id>', methods=['POST'])
@jwt_required()
def save_job(job_id):
    user_id = get_jwt_identity()
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO saved_jobs (user_id, job_id) VALUES (%s, %s)",
            (user_id, job_id)
        )
        conn.commit()
        return jsonify({"message": "Job saved!"}), 201
    except Exception as e:
        return jsonify({"message": "Already saved!"}), 400
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/unsave-job/<int:job_id>', methods=['DELETE'])
@jwt_required()
def unsave_job(job_id):
    user_id = get_jwt_identity()
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM saved_jobs WHERE user_id = %s AND job_id = %s",
            (user_id, job_id)
        )
        conn.commit()
        return jsonify({"message": "Job unsaved!"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/saved-jobs', methods=['GET'])
@jwt_required()
def get_saved_jobs():
    user_id = get_jwt_identity()
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT j.* FROM jobs j
            INNER JOIN saved_jobs sj ON j.id = sj.job_id
            WHERE sj.user_id = %s
            ORDER BY sj.saved_at DESC
        """, (user_id,))
        jobs = cursor.fetchall()
        return jsonify(jobs), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/setup-apply-tracker')
def setup_apply_tracker():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apply_tracker (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                job_id INT NOT NULL,
                status VARCHAR(20) DEFAULT 'Applied',
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_apply (user_id, job_id)
            )
        """)
        conn.commit()
        return jsonify({"message": "apply_tracker table created!"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/apply-job/<int:job_id>', methods=['POST'])
@jwt_required()
def apply_job(job_id):
    user_id = get_jwt_identity()
    data = request.json or {}
    status = data.get('status', 'Applied')
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO apply_tracker (user_id, job_id, status) VALUES (%s, %s, %s)",
            (user_id, job_id, status)
        )
        conn.commit()
        return jsonify({"message": "Application tracked!"}), 201
    except Exception as e:
        return jsonify({"message": "Already applied!"}), 400
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/update-apply-status/<int:job_id>', methods=['PUT'])
@jwt_required()
def update_apply_status(job_id):
    user_id = get_jwt_identity()
    data = request.json
    status = data.get('status', 'Applied')
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE apply_tracker SET status = %s WHERE user_id = %s AND job_id = %s",
            (status, user_id, job_id)
        )
        conn.commit()
        return jsonify({"message": "Status updated!"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/applied-jobs', methods=['GET'])
@jwt_required()
def get_applied_jobs():
    user_id = get_jwt_identity()
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT j.*, at.status, at.applied_at FROM jobs j
            INNER JOIN apply_tracker at ON j.id = at.job_id
            WHERE at.user_id = %s
            ORDER BY at.applied_at DESC
        """, (user_id,))
        jobs = cursor.fetchall()
        return jsonify(jobs), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# ============ EMAIL ALERTS ============

@app.route('/setup-email-alerts')
def setup_email_alerts():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            ALTER TABLE jobs ADD COLUMN is_alerted TINYINT DEFAULT 0
        """)
        conn.commit()
        return jsonify({"message": "Email alerts setup complete! is_alerted column added."}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/send-alerts')
def send_alerts():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM jobs WHERE is_alerted = 0 ORDER BY id DESC LIMIT 50")
        new_jobs = cursor.fetchall()

        if not new_jobs:
            return jsonify({"message": "No new jobs to alert about right now."}), 200

        cursor.execute("SELECT email FROM users")
        users = cursor.fetchall()

        if not users:
            return jsonify({"message": "No users found to send alerts to."}), 200

        job_list_html = ""
        for job in new_jobs:
            title = job.get('title') or 'Untitled Job'
            company = job.get('company') or ''
            url = job.get('url') or job.get('link') or '#'
            job_list_html += f"<li><b>{title}</b> at {company} &nbsp; <a href='{url}'>Apply Here</a></li>"

        subject = f"{len(new_jobs)} New Remote Jobs Found!"
        body = f"""
        <h3>Hi there!</h3>
        <p>We found {len(new_jobs)} new remote jobs for you:</p>
        <ul>{job_list_html}</ul>
        <p>Visit your dashboard to see more and apply!</p>
        """

        sent_count = 0
        for user in users:
            if send_email(user['email'], subject, body):
                sent_count += 1

        job_ids = [job['id'] for job in new_jobs]
        placeholders = ','.join(['%s'] * len(job_ids))
        cursor.execute(f"UPDATE jobs SET is_alerted = 1 WHERE id IN ({placeholders})", job_ids)
        conn.commit()

        return jsonify({
            "message": f"Alerts sent to {sent_count} users about {len(new_jobs)} new jobs!"
        }), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)