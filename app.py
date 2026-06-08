from flask import Flask, jsonify
from flask_cors import CORS
from scraper import scrape_remoteok
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "job_tracker"),
        port=int(os.getenv("DB_PORT", 3306))
    )

@app.route('/scrape', methods=['GET'])
def get_jobs():
    jobs = scrape_remoteok()
    if jobs:
        try:
            conn = get_db()
            cursor = conn.cursor()
            for job in jobs:
                cursor.execute("""
                    INSERT INTO jobs (title, company, url, location, source)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE title=VALUES(title)
                """, (job['title'], job['company'], job['url'], job['location'], job['source']))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"DB Error: {e}")
    return jsonify(jobs)

@app.route('/api/jobs', methods=['GET'])
def api_jobs():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
    jobs = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(jobs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)