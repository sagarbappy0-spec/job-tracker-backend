import requests
import psycopg2
import os
import xml.etree.ElementTree as ET

def get_db():
    return psycopg2.connect(os.environ.get("DATABASE_URL"), sslmode='require')

def scrape_remotive():
    jobs = []
    try:
        response = requests.get("https://remotive.com/api/remote-jobs?limit=30", timeout=15)
        data = response.json()
        for job in data.get("jobs", []):
            tags = job.get("tags", [])
            jobs.append({
                "title": job.get("title", "N/A"),
                "company": job.get("company_name", "N/A"),
                "url": job.get("url", "N/A"),
                "location": job.get("candidate_required_location") or "Remote",
                "source": "Remotive",
                "tags": ", ".join(tags) if tags else None,
                "experience_level": None,
                "salary_min": None,
                "salary_max": None
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
            tags = job.get("tags", [])
            jobs.append({
                "title": job.get("title", "N/A"),
                "company": job.get("company_name", "N/A"),
                "url": job.get("url", "N/A"),
                "location": job.get("location", "Remote"),
                "source": "Arbeitnow",
                "tags": ", ".join(tags) if tags else None,
                "experience_level": None,
                "salary_min": None,
                "salary_max": None
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
                tags = job.get("tags", [])
                jobs.append({
                    "title": job.get("position", "N/A"),
                    "company": job.get("company", "N/A"),
                    "url": job.get("url", "N/A"),
                    "location": job.get("location") or "Remote",
                    "source": "RemoteOK",
                    "tags": ", ".join(tags) if tags else None,
                    "experience_level": None,
                    "salary_min": job.get("salary_min") or None,
                    "salary_max": job.get("salary_max") or None
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
                    "source": "WeWorkRemotely",
                    "tags": None,
                    "experience_level": None,
                    "salary_min": None,
                    "salary_max": None
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
                "location": job.get("jobGeo") or "Remote",
                "source": "Jobicy",
                "tags": None,
                "experience_level": job.get("jobLevel") or None,
                "salary_min": job.get("annualSalaryMin") or None,
                "salary_max": job.get("annualSalaryMax") or None
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
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM jobs WHERE title = %s AND company = %s",
                    (job["title"], job["company"])
                )
                existing = cursor.fetchone()
                cursor.close()
                if existing:
                    skipped += 1
                    continue
                cursor2 = conn.cursor()
                cursor2.execute(
                    "INSERT INTO jobs (title, company, url, location, source, tags, experience_level, salary_min, salary_max) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (job["title"], job["company"], job["url"], job["location"], job["source"],
                     job.get("tags"), job.get("experience_level"), job.get("salary_min"), job.get("salary_max"))
                )
                cursor2.close()
                conn.commit()
                saved += 1
            except Exception as e:
                print(f"Job save error: {e}")
                continue
        print(f"Saved: {saved}, Skipped: {skipped}")
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