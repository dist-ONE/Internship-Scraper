import os
import sqlite3
import pandas as pd
import requests
import json
from google import genai
from google.genai import types
from jobspy import scrape_jobs

WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

if not WEBHOOK_URL or not GEMINI_KEY:
    raise ValueError("CRITICAL ERROR: Missing Webhook URL or Gemini API Key!")

client = genai.Client(api_key=GEMINI_KEY)

def setup_database():
    conn = sqlite3.connect('internships.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS posted_jobs (job_url TEXT PRIMARY KEY)')
    conn.commit()
    return conn

def clean_val(val, default):
    return default if pd.isna(val) else str(val)

def evaluate_fit(title, description):
    prompt = f"""
    You are an expert technical recruiter evaluating an internship opportunity for a specific candidate.
    
    Candidate Profile:
    - Education: Second-year Artificial Intelligence student at Babeș-Bolyai University.
    - Languages: C, C++, Python, Luau, Bash.
    - Core Engineering: Game development (client-server architectures, custom physics/UI, Roblox Knit framework), AI applications (local LLMs via Ollama, RAG pipelines, ChromaDB), 3D geometric simulations, and graph algorithms.
    - Notable Projects: 'CADPilot' (AI 3D model generator, Top 80 InnovationLabs) and 'OverEngineered' (multiplayer party game).
    
    Job Title: {title}
    Job Description: {description}
    
    Evaluate the match. Return a JSON object with exactly two keys:
    - "score": An integer from 1 to 10 representing how well the candidate's skills and level match the job.
    - "reason": A single, concise sentence explaining the score based on the candidate's specific background.
    """
    try:
        chat = client.chats.create(model='gemini-2.5-flash')
        
        response = chat.send_message(
            prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        if not response.text:
            return {"score": 0, "reason": "No response from AI model."}
        
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini Error: {e}")
        return {"score": 0, "reason": "Could not generate AI score."}

print("Checking for new internships...")

try:
    jobs = scrape_jobs(
        site_name=["linkedin", "indeed"],
        search_term="internship software",
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
        title = clean_val(row.get('title'), 'Unknown Title')
        desc = clean_val(row.get('description'), 'No description available.')
        
        print(f"Scoring: {title}...")
        ai_eval = evaluate_fit(title, desc)
        score = int(ai_eval.get('score', 0))
        
        score_color = 0x00ff00 if score >= 7 else 0xffa500
        
        if len(desc) > 300:
            desc = desc[:300] + "..."
            
        min_amt = clean_val(row.get('min_amount'), '')
        max_amt = clean_val(row.get('max_amount'), '')
        curr = clean_val(row.get('currency'), '').upper()
        interval = clean_val(row.get('interval'), '')
        
        if min_amt and max_amt:
            payment = f"{min_amt} - {max_amt} {curr} {interval}".strip()
        elif min_amt:
            payment = f"{min_amt} {curr} {interval}".strip()
        elif max_amt:
            payment = f"{max_amt} {curr} {interval}".strip()
        else:
            payment = "Not specified"

        payload = {
            "embeds": [{
                "title": f"[{ai_eval['score']}/10] {title}",
                "url": job_url,
                "description": f"**AI Analysis:** {ai_eval['reason']}\n\n**Snippet:** {desc}",
                "color": score_color,
                "fields": [
                    {"name": "🏢 Company", "value": clean_val(row.get('company'), 'Unknown Company'), "inline": True},
                    {"name": "📍 Location", "value": clean_val(row.get('location'), 'Cluj-Napoca'), "inline": True},
                    {"name": "💰 Payment", "value": payment, "inline": True}
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