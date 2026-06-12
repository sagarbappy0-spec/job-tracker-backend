import requests
import mysql.connector
import os

def get_db():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("MYSQLHOST"),
        user=os.environ.get("DB_USER") or os.environ.get("MYSQLUSER"),
        password=os.environ.get("DB_PASSWORD") or os.environ.get("MYSQLPASSWORD"),
        database=os.environ.get("DB_NAME") or os.environ.get("MYSQLDB"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("MYSQLPORT") or 3306)
    )

def scrape_remotive():
    jobs = []
    try:
        response = requests.get("https://remotive.com/api/remote-jobs?limit=20", timeout=15)
        data = response.json()
        for job in data.get("jobs", []):
            jobs.append({
                "title": job.get("title", "N/A"),
                "company": job.get("company_name", "N/A"),
                "url": job.get("url", "N/A"),
                "location": "Remote",
                "source": "Remotive"
            })
    except Exception as e:
        print(f"Remotive Error: {e}")
    return jobs

def scrape_arbeitnow():
    jobs = []
    try:
        response = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=15)
        data = response.json()
        for job in data.get("data", [])[:20]:
            jobs.append({
                "title": job.get("title", "N/A"),
                "company": job.get("company_name", "N/A"),
                "url": job.get("url", "N/A"),
                "location": job.get("location", "Remote"),
                "source": "Arbeitnow"
            })
    except Exception as e:
        print(f"Arbeitnow Error: {e}")
    return jobs

def save_jobs(jobs):
    conn = None
    cursor = None
    saved = 0
    skipped = 0
    try:
        conn = get_db()
        cursor = conn.cursor()
        for job in jobs:
            # Deduplication check — same title + company আগে আছে কিনা
            cursor.execute(
                "SELECT id FROM jobs WHERE title = %s AND company = %s",
                (job["title"], job["company"])
            )
            existing = cursor.fetchone()
            if existing:
                skipped += 1
                continue
            # Duplicate নেই — insert করো
            cursor.execute(
                "INSERT INTO jobs (title, company, url, location, source) VALUES (%s, %s, %s, %s, %s)",
                (job["title"], job["company"], job["url"], job["location"], job["source"])
            )
            saved += 1
        conn.commit()
        print(f"Saved: {saved}, Skipped (duplicate): {skipped}")
    except Exception as e:
        print(f"DB Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def scrape_all():
    jobs = []
    jobs += scrape_remotive()
    jobs += scrape_arbeitnow()
    print(f"Total scraped: {len(jobs)}")
    return jobs

if __name__ == "__main__":
    jobs = scrape_all()
    save_jobs(jobs)