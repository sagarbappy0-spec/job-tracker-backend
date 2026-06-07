import requests

def scrape_remoteok():
    jobs = []
    
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get("https://remoteok.com/api", headers=headers)
        data = response.json()
        
        # প্রথম item টা skip করো (এটা metadata)
        for job in data[1:20]:
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

if __name__ == "__main__":
    jobs = scrape_remoteok()
    for job in jobs:
        print(f"{job['title']} | {job['company']}")