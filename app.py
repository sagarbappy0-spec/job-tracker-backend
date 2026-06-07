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
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

# Scraper endpoint (n8n ব্যবহার করে)
@app.route('/scrape', methods=['GET'])
def get_jobs():
    jobs = scrape_remoteok()
    return jsonify(jobs)

# Dashboard এর জন্য নতুন endpoint
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