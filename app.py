from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
import psycopg2
import psycopg2.extras
import os
import requests
import re
import secrets
from datetime import datetime, timedelta

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

CORS(app, origins="*", supports_credentials=True)
bcrypt = Bcrypt(app)
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "supersecretkey")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=15)
jwt = JWTManager(app)

limiter = Limiter(key_func=get_remote_address, app=app, default_limits=[])

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
REFRESH_TOKEN_DAYS = 30
FRONTEND_URL = "https://job-dashboard-psi-lovat.vercel.app"
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"message": "Too many attempts. Please wait a bit and try again."}), 429

@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

def is_valid_email(email):
    return bool(email) and bool(EMAIL_REGEX.match(email))

def get_db():
    return psycopg2.connect(os.environ.get("DATABASE_URL"), sslmode='require')

def send_email(to_email, subject, html_body):
    try:
        api_key = os.environ.get("BREVO_API_KEY")
        sender_email = os.environ.get("EMAIL_USER")
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json"
        }
        payload = {
            "sender": {"name": "JobTracker", "email": sender_email},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html_body
        }
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"Email send error for {to_email}: {e}")
        return False

def create_refresh_token(cursor, conn, user_id):
    new_token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=REFRESH_TOKEN_DAYS)
    cursor.execute(
        "INSERT INTO refresh_tokens (user_id, token, expires_at) VALUES (%s, %s, %s)",
        (user_id, new_token, expires_at)
    )
    conn.commit()
    return new_token

@app.route('/')
def home():
    return jsonify({"status": "Backend is running on Render + PostgreSQL!"})

@app.route('/setup-all')
def setup_all():
    """একবারেই সব table বানায়"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) NOT NULL,
                email VARCHAR(150) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                failed_login_attempts INT DEFAULT 0,
                account_locked_until TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id SERIAL PRIMARY KEY,
                title VARCHAR(300),
                company VARCHAR(200),
                url TEXT,
                location VARCHAR(200),
                source VARCHAR(100),
                tags VARCHAR(500),
                experience_level VARCHAR(50),
                salary_min INT,
                salary_max INT,
                is_alerted SMALLINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_jobs (
                id SERIAL PRIMARY KEY,
                user_id INT NOT NULL,
                job_id INT NOT NULL,
                saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, job_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apply_tracker (
                id SERIAL PRIMARY KEY,
                user_id INT NOT NULL,
                job_id INT NOT NULL,
                status VARCHAR(20) DEFAULT 'Applied',
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, job_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id SERIAL PRIMARY KEY,
                user_id INT NOT NULL,
                token VARCHAR(100) NOT NULL UNIQUE,
                expires_at TIMESTAMP NOT NULL,
                used SMALLINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id SERIAL PRIMARY KEY,
                user_id INT NOT NULL,
                token VARCHAR(100) NOT NULL UNIQUE,
                expires_at TIMESTAMP NOT NULL,
                revoked SMALLINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        return jsonify({"message": "All tables created successfully! Ready to use."}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/register', methods=['POST'])
@limiter.limit("5 per hour")
def register():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    if not username:
        return jsonify({"message": "Username cannot be empty."}), 400
    if not is_valid_email(email):
        return jsonify({"message": "Please enter a valid email address."}), 400
    if len(password) < 6:
        return jsonify({"message": "Password must be at least 6 characters."}), 400

    conn = None
    cursor = None
    try:
        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, hashed_pw)
        )
        conn.commit()
        return jsonify({"message": "User registered successfully"}), 201
    except Exception as e:
        return jsonify({"message": "User already exists"}), 400
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.json or {}
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({"message": "Email and password are required."}), 400

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"message": "Invalid credentials"}), 401

        locked_until = user.get('account_locked_until')
        if locked_until and locked_until > datetime.now():
            remaining = int((locked_until - datetime.now()).total_seconds() / 60) + 1
            return jsonify({"message": f"Account locked. Try again in {remaining} minute(s), or reset your password."}), 403

        if bcrypt.check_password_hash(user['password'], password):
            cursor.execute(
                "UPDATE users SET failed_login_attempts = 0, account_locked_until = NULL WHERE id = %s",
                (user['id'],)
            )
            conn.commit()
            access_token = create_access_token(identity=str(user['id']))
            refresh_token = create_refresh_token(cursor, conn, user['id'])
            return jsonify({"token": access_token, "refresh_token": refresh_token}), 200
        else:
            new_attempts = (user.get('failed_login_attempts') or 0) + 1
            if new_attempts >= MAX_FAILED_ATTEMPTS:
                lock_until = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
                cursor.execute(
                    "UPDATE users SET failed_login_attempts = %s, account_locked_until = %s WHERE id = %s",
                    (new_attempts, lock_until, user['id'])
                )
                conn.commit()
                return jsonify({"message": f"Account locked for {LOCKOUT_MINUTES} minute(s). Reset your password to unlock."}), 403
            else:
                cursor.execute(
                    "UPDATE users SET failed_login_attempts = %s WHERE id = %s",
                    (new_attempts, user['id'])
                )
                conn.commit()
                remaining = MAX_FAILED_ATTEMPTS - new_attempts
                return jsonify({"message": f"Invalid credentials. {remaining} attempt(s) remaining before lockout."}), 401
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/refresh', methods=['POST'])
@limiter.limit("30 per hour")
def refresh():
    data = request.json or {}
    old_token = (data.get('refresh_token') or '').strip()
    if not old_token:
        return jsonify({"message": "Refresh token is required."}), 400
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM refresh_tokens WHERE token = %s AND revoked = 0", (old_token,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"message": "Invalid or revoked session. Please log in again."}), 401
        if row['expires_at'] < datetime.now():
            return jsonify({"message": "Session expired. Please log in again."}), 401
        cursor.execute("UPDATE refresh_tokens SET revoked = 1 WHERE id = %s", (row['id'],))
        new_refresh_token = create_refresh_token(cursor, conn, row['user_id'])
        new_access_token = create_access_token(identity=str(row['user_id']))
        return jsonify({"token": new_access_token, "refresh_token": new_refresh_token}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/logout', methods=['POST'])
def logout():
    data = request.json or {}
    refresh_token = (data.get('refresh_token') or '').strip()
    if refresh_token:
        conn = None
        cursor = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE refresh_tokens SET revoked = 1 WHERE token = %s", (refresh_token,))
            conn.commit()
        except Exception:
            pass
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    return jsonify({"message": "Logged out successfully."}), 200

@app.route('/forgot-password', methods=['POST'])
@limiter.limit("3 per hour")
def forgot_password():
    data = request.json or {}
    email = (data.get('email') or '').strip()
    if not is_valid_email(email):
        return jsonify({"message": "Please enter a valid email address."}), 400
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(minutes=30)
            cursor.execute(
                "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (%s, %s, %s)",
                (user['id'], token, expires_at)
            )
            conn.commit()
            reset_link = f"{FRONTEND_URL}/?reset_token={token}"
            send_email(email, "Reset your Job Tracker password", f"""
            <h3>Password Reset Request</h3>
            <p>Click the link below to reset your password:</p>
            <p><a href="{reset_link}">Reset My Password</a></p>
            <p>This link expires in 30 minutes.</p>
            """)
        return jsonify({"message": "If that email is registered, a password reset link has been sent."}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/reset-password', methods=['POST'])
@limiter.limit("5 per hour")
def reset_password():
    data = request.json or {}
    token = (data.get('token') or '').strip()
    new_password = data.get('new_password') or ''
    if not token:
        return jsonify({"message": "Reset token is missing."}), 400
    if len(new_password) < 6:
        return jsonify({"message": "Password must be at least 6 characters."}), 400
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM password_reset_tokens WHERE token = %s AND used = 0", (token,))
        reset_row = cursor.fetchone()
        if not reset_row:
            return jsonify({"message": "Invalid or already-used reset link."}), 400
        if reset_row['expires_at'] < datetime.now():
            return jsonify({"message": "This reset link has expired. Please request a new one."}), 400
        hashed_pw = bcrypt.generate_password_hash(new_password).decode('utf-8')
        cursor.execute(
            "UPDATE users SET password = %s, failed_login_attempts = 0, account_locked_until = NULL WHERE id = %s",
            (hashed_pw, reset_row['user_id'])
        )
        cursor.execute("UPDATE password_reset_tokens SET used = 1 WHERE id = %s", (reset_row['id'],))
        cursor.execute("UPDATE refresh_tokens SET revoked = 1 WHERE user_id = %s", (reset_row['user_id'],))
        conn.commit()
        return jsonify({"message": "Password reset successful! You can now log in."}), 200
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
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("DELETE FROM jobs WHERE created_at < NOW() - INTERVAL '30 days'")
        conn.commit()

        keyword = request.args.get('keyword', '').strip()
        location = request.args.get('location', '').strip()
        experience = request.args.get('experience', '').strip()
        salary_min = request.args.get('salary_min', '').strip()

        query = "SELECT * FROM jobs WHERE 1=1"
        params = []

        if keyword:
            query += " AND (title ILIKE %s OR company ILIKE %s OR tags ILIKE %s)"
            kw = f"%{keyword}%"
            params += [kw, kw, kw]
        if location:
            query += " AND location ILIKE %s"
            params.append(f"%{location}%")
        if experience:
            query += " AND experience_level ILIKE %s"
            params.append(f"%{experience}%")
        if salary_min:
            query += " AND (salary_min >= %s OR salary_max >= %s)"
            params += [salary_min, salary_min]

        query += " ORDER BY id DESC LIMIT 200"
        cursor.execute(query, tuple(params))
        jobs = cursor.fetchall()
        return jsonify([dict(j) for j in jobs]), 200
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
        cursor.execute("INSERT INTO saved_jobs (user_id, job_id) VALUES (%s, %s)", (user_id, job_id))
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
        cursor.execute("DELETE FROM saved_jobs WHERE user_id = %s AND job_id = %s", (user_id, job_id))
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
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("""
            SELECT j.* FROM jobs j
            INNER JOIN saved_jobs sj ON j.id = sj.job_id
            WHERE sj.user_id = %s ORDER BY sj.saved_at DESC
        """, (user_id,))
        jobs = cursor.fetchall()
        return jsonify([dict(j) for j in jobs]), 200
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
    data = request.json or {}
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
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("""
            SELECT j.*, at.status, at.applied_at FROM jobs j
            INNER JOIN apply_tracker at ON j.id = at.job_id
            WHERE at.user_id = %s ORDER BY at.applied_at DESC
        """, (user_id,))
        jobs = cursor.fetchall()
        return jsonify([dict(j) for j in jobs]), 200
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
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM jobs WHERE is_alerted = 0 ORDER BY id DESC LIMIT 50")
        new_jobs = cursor.fetchall()
        if not new_jobs:
            return jsonify({"message": "No new jobs to alert about."}), 200
        cursor.execute("SELECT email FROM users")
        users = cursor.fetchall()
        if not users:
            return jsonify({"message": "No users found."}), 200

        job_list_html = ""
        for job in new_jobs:
            title = job.get('title') or 'Untitled'
            company = job.get('company') or ''
            url = job.get('url') or '#'
            job_list_html += f"<li><b>{title}</b> at {company} &nbsp; <a href='{url}'>Apply Here</a></li>"

        subject = f"{len(new_jobs)} New Remote Jobs Found!"
        body = f"<h3>Hi there!</h3><p>We found {len(new_jobs)} new remote jobs:</p><ul>{job_list_html}</ul>"

        sent_count = sum(1 for u in users if send_email(u['email'], subject, body))

        job_ids = [job['id'] for job in new_jobs]
        placeholders = ','.join(['%s'] * len(job_ids))
        cursor.execute(f"UPDATE jobs SET is_alerted = 1 WHERE id IN ({placeholders})", job_ids)
        conn.commit()
        return jsonify({"message": f"Alerts sent to {sent_count} users about {len(new_jobs)} jobs!"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/reset-alerts')
def reset_alerts():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET is_alerted = 0")
        conn.commit()
        return jsonify({"message": "All jobs reset!"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)