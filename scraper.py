import requests

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

def scrape_remoteok():
    jobs = []
    jobs += scrape_remotive()
    jobs += scrape_arbeitnow()
    print(f"Total jobs scraped: {len(jobs)}")
    return jobs
if __name__ == "__main__":
    jobs = scrape_remoteok()
    for job in jobs:
        print(f"{job['title']} | {job['company']} | {job['source']}")