import requests

def scrape_remoteok():
    jobs = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        response = requests.get(
            "https://remoteok.com/api",
            headers=headers,
            timeout=15
        )
        data = response.json()
        for job in data[1:21]:
            if isinstance(job, dict) and job.get("position"):
                jobs.append({
                    "title": job.get("position", "N/A"),
                    "company": job.get("company", "N/A"),
                    "url": job.get("url", "N/A"),
                    "location": "Remote",
                    "source": "RemoteOK"
                })
    except Exception as e:
        print(f"Error: {e}")
    return jobs