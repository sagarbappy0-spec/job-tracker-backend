import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "job_tracker"),
        port=int(os.getenv("DB_PORT", 3306))
    )

def save_job(title, company, url):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO jobs (title, company, url) 
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE 
        title=VALUES(title), company=VALUES(company)
    """, (title, company, url))
    conn.commit()
    cursor.close()
    conn.close()