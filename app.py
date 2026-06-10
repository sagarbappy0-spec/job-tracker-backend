from flask import Flask, jsonify, request
from flask_cors import CORS
from scraper import scrape_remoteok
import mysql.connector
import os, bcrypt, jwt, datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)
SECRET_KEY = "jobtracker_secret_2024"

def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "job_tracker"),
        port=int(os.getenv("DB_PORT", 3306))
    )

# Jobs scrape
@app.route('/scrape', methods=['GET'])
def get_jobs():
    jobs = scrape_remoteok()
    return jsonify(jobs)

# Jobs list
@app.route('/api/jobs', methods=['GET'])
def api_jobs():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
    jobs = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(jobs)

# Register
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    
    if not name or not email or not password:
        return jsonify({"error": "সব field পূরণ করো"}), 400
    
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (name, email, hashed.decode('utf-8'))
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "Registration সফল!"}), 201
    except Exception as e:
        return jsonify({"error": "Email already exists"}), 400

# Login
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not user:
        return jsonify({"error": "Email পাওয়া যায়নি"}), 401
    
    if bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
        token = jwt.encode({
            'user_id': user['id'],
            'name': user['name'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
        }, SECRET_KEY, algorithm='HS256')
        return jsonify({"token": token, "name": user['name']}), 200
    else:
        return jsonify({"error": "Password ভুল"}), 401

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)