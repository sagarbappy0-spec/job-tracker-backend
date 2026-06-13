import requests
import mysql.connector
import os
import xml.etree.ElementTree as ET

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
        response = requests.get("https://remotive.com/api/remote-jobs?limit=30", timeout=15)
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
        for job in data.get("data", [])[:30]:
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

def scrape_remoteok():
    jobs = []
    try:
        response = requests.get(
            "https://remoteok.com/api",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        data = response.json()
        for job in data[1:31]:
            if isinstance(job, dict) and job.get("position"):
                jobs.append({
                    "title": job.get("position", "N/A"),
                    "company": job.get("company", "N/A"),
                    "url": job.get("url", "N/A"),
                    "location": "Remote",
                    "source": "RemoteOK"
                })
    except Exception as e:
        print(f"RemoteOK Error: {e}")
    return jobs

def scrape_weworkremotely():
    jobs = []
    try:
        response = requests.get(
            "https://weworkremotely.com/remote-jobs.rss",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        root = ET.fromstring(response.content)
        count = 0
        for item in root.findall(".//item"):
            if count >= 30:
                break
            title = item.find("title")
            link = item.find("link")
            if title is not None and link is not None:
                title_text = title.text or "N/A"
                parts = title_text.split(":")
                job_title = parts[1].strip() if len(parts) > 1 else title_text
                company = parts[0].strip() if len(parts) > 1 else "N/A"
                jobs.append({
                    "title": job_title,
                    "company": company,
                    "url": link.text or "N/A",
                    "location": "Remote",
                    "source": "WeWorkRemotely"
                })
                count += 1
    except Exception as e:
        print(f"WeWorkRemotely Error: {e}")
    return jobs

def scrape_jobicy():
    jobs = []
    try:
        response = requests.get(
            "https://jobicy.com/api/v2/remote-jobs?count=30",
            timeout=15
        )
        data = response.json()
        for job in data.get("jobs", []):
            jobs.append({
                "title": job.get("jobTitle", "N/A"),
                "company": job.get("companyName", "N/A"),
                "url": job.get("url", "N/A"),
                "location": job.get("jobGeo", "Remote"),
                "source": "Jobicy"
            })
    except Exception as e:
        print(f"Jobicy Error: {e}")
    return jobs

def save_jobs(jobs):
    conn = None
    saved = 0
    skipped = 0
    try:
        conn = get_db()
        for job in jobs:
            try:
                cursor = conn.cursor(buffered=True)
                cursor.execute(
                    "SELECT id FROM jobs WHERE title = %s AND company = %s",
                    (job["title"], job["company"])
                )
                existing = cursor.fetchone()
                cursor.close()
                if existing:
                    skipped += 1
                    continue
                cursor2 = conn.cursor(buffered=True)
                cursor2.execute(
                    "INSERT INTO jobs (title, company, url, location, source) VALUES (%s, %s, %s, %s, %s)",
                    (job["title"], job["company"], job["url"], job["location"], job["source"])
                )
                cursor2.close()
                conn.commit()
                saved += 1
            except Exception as e:
                print(f"Job save error: {e}")
                continue
        print(f"Saved: {saved}, Skipped (duplicate): {skipped}")
        return {"saved": saved, "skipped": skipped}
    except Exception as e:
        print(f"DB Error: {e}")
        return {"saved": 0, "skipped": 0}
    finally:
        if conn: conn.close()

def scrape_all():
    jobs = []
    jobs += scrape_remotive()
    jobs += scrape_arbeitnow()
    jobs += scrape_remoteok()
    jobs += scrape_weworkremotely()
    jobs += scrape_jobicy()
    print(f"Total scraped: {len(jobs)}")
    return jobs

if __name__ == "__main__":
    jobs = scrape_all()
    save_jobs(jobs)