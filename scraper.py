import requests

def scrape_remoteok():
    jobs = []
    try:
        response = requests.get(
            "https://remotive.com/api/remote-jobs?limit=20",
            timeout=15
        )
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
        print(f"Error: {e}")
    return jobs