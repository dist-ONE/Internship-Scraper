import os
import sqlite3
import pandas as pd
import requests
from jobspy import scrape_jobs

WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

if not WEBHOOK_URL:
    raise ValueError("CRITICAL ERROR: DISCORD_WEBHOOK_URL is missing!")

def setup_database():
    conn = sqlite3.connect('internships.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posted_jobs (
            job_url TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    return conn

def clean_val(val, default):
    return default if pd.isna(val) else str(val)

print("Checking for new internships...")

try:
    jobs = scrape_jobs(
        site_name=["linkedin", "indeed"],
        search_term="internship OR intern AI OR software",
        location="Cluj-Napoca, Romania",
        results_wanted=10
    )
except Exception as e:
    print(f"Scraper error: {e}")
    exit(1)

print(f"Total jobs scraped: {len(jobs)}")
if not jobs.empty:
    print(jobs[['title', 'company', 'location']].to_string())

db_conn = setup_database()
cursor = db_conn.cursor()

for index, row in jobs.iterrows():
    job_url = row.get('job_url')
    if pd.isna(job_url) or not job_url:
        continue
        
    cursor.execute("SELECT 1 FROM posted_jobs WHERE job_url = ?", (job_url,))
    if not cursor.fetchone():
        desc = clean_val(row.get('description'), 'No description available.')
        if len(desc) > 300:
            desc = desc[:300] + "..."

        payload = {
            "embeds": [{
                "title": clean_val(row.get('title'), 'Unknown Title'),
                "url": job_url,
                "description": desc,
                "color": 65280,
                "fields": [
                    {"name": "🏢 Company", "value": clean_val(row.get('company'), 'Unknown Company'), "inline": True},
                    {"name": "📍 Location", "value": clean_val(row.get('location'), 'Cluj-Napoca'), "inline": True},
                    {"name": "💼 Type", "value": clean_val(row.get('job_type'), 'Not specified'), "inline": True}
                ],
                "footer": {"text": f"Source: {clean_val(row.get('site'), 'Unknown').capitalize()}"}
            }]
        }
        
        response = requests.post(WEBHOOK_URL, json=payload)
        
        if response.status_code == 204:
            cursor.execute("INSERT INTO posted_jobs (job_url) VALUES (?)", (job_url,))
            db_conn.commit()
        else:
            print(f"Failed to send webhook: {response.status_code}")

print("Finished checking for new postings.")