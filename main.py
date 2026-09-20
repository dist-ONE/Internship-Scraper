import os
import time
import json
import sqlite3
import pandas as pd
import requests
from google import genai
from google.genai import types
from jobspy import scrape_jobs

CONFIG = {
    # Scraper Settings
    "search_terms": "internship software",
    "location": "Cluj-Napoca, Romania",
    "platforms": ["linkedin", "indeed", "glassdoor"],
    "max_results": 15,
    
    "candidate_profile": """
    - Education: Second-year Artificial Intelligence student at Babeș-Bolyai University.
    - Languages: C, C++, Python, Luau, Bash.
    - Core Engineering: Game development (client-server architectures, custom physics/UI, Roblox Knit framework), AI applications (local LLMs via Ollama, RAG pipelines, ChromaDB), 3D geometric simulations, and graph algorithms.
    - Notable Projects: 'CADPilot' (AI 3D model generator, Top 80 InnovationLabs) and 'OverEngineered' (multiplayer party game).
    """,
    
    "webhook_delay": 2.0,
    "snippet_max_length": 350
}

class JobDatabase:
    def __init__(self, db_name='internships.db'):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS posted_jobs (
                job_url TEXT PRIMARY KEY,
                date_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def job_exists(self, job_url: str) -> bool:
        self.cursor.execute("SELECT 1 FROM posted_jobs WHERE job_url = ?", (job_url,))
        return self.cursor.fetchone() is not None

    def mark_job_posted(self, job_url: str):
        self.cursor.execute("INSERT INTO posted_jobs (job_url) VALUES (?)", (job_url,))
        self.conn.commit()

class AIEvaluator:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-3.6-flash'

    def evaluate_fit(self, title: str, description: str) -> dict:
        prompt = f"""
        You are an expert technical recruiter evaluating an internship opportunity for a specific candidate.
        
        Candidate Profile:
        {CONFIG['candidate_profile']}
        
        Job Title: {title}
        Job Description: {description}
        
        Evaluate the match. Return a JSON object with exactly two keys:
        - "score": An integer from 1 to 10 representing how well the candidate's skills and level match the job.
        - "reason": A single, concise sentence explaining the score based on the candidate's specific background.
        """
        
        for attempt in range(3):
            try:
                chat = self.client.chats.create(model=self.model_name)
                response = chat.send_message(
                    prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )

                if not response.text:
                    return {"score": 0, "reason": "No response from AI model."}
                
                result = json.loads(response.text)
                return result if isinstance(result, dict) else {"score": 0, "reason": "Invalid JSON format."}
                
            except Exception as e:
                error_msg = str(e)
                if "503" in error_msg or "429" in error_msg:
                    sleep_time = 5 * (2 ** attempt) 
                    print(f"Gemini servers busy. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    print(f"Gemini Error: {e}")
                    return {"score": 0, "reason": "Could not generate AI score due to API error."}

        return {"score": 0, "reason": "Evaluation failed after retries."}

class DiscordWebhook:
    def __init__(self, webhook_url: str):
        self.url = webhook_url

    def _get_color_for_score(self, score: int) -> int:
        """
        Returns a Discord hex color based on the match score.
        """

        if score >= 8: return 0x2ecc71
        if score >= 5: return 0xf1c40f
        return 0xe74c3c

    def _clean_val(self, val, default="Unknown"):
        return default if pd.isna(val) or not val else str(val)

    def send_job_alert(self, job_row: pd.Series, ai_eval: dict) -> bool:
        title = self._clean_val(job_row.get('title'), 'Unknown Title')
        job_url = str(job_row.get('job_url'))
        desc = self._clean_val(job_row.get('description'), 'No description available.')
        
        score = int(ai_eval.get('score', 0))
        color = self._get_color_for_score(score)
        
        if len(desc) > CONFIG['snippet_max_length']:
            desc = desc[:CONFIG['snippet_max_length']].rsplit(' ', 1)[0] + "..."

        min_amt = self._clean_val(job_row.get('min_amount'), '')
        max_amt = self._clean_val(job_row.get('max_amount'), '')
        curr = self._clean_val(job_row.get('currency'), '').upper()
        interval = self._clean_val(job_row.get('interval'), '')
        
        payment = "Not specified"
        if min_amt and max_amt: payment = f"{min_amt} - {max_amt} {curr} {interval}".strip()
        elif min_amt: payment = f"{min_amt} {curr} {interval}".strip()
        elif max_amt: payment = f"{max_amt} {curr} {interval}".strip()

        payload = {
            "embeds": [{
                "title": f"[{score}/10] {title}",
                "url": job_url,
                "description": f"**AI Analysis:**\n{ai_eval.get('reason', 'N/A')}\n\n**Snippet:**\n{desc}",
                "color": color,
                "fields": [
                    {"name": "Company", "value": self._clean_val(job_row.get('company'), 'Unknown'), "inline": True},
                    {"name": "Location", "value": self._clean_val(job_row.get('location'), 'Unknown'), "inline": True},
                    {"name": "Payment", "value": payment, "inline": True}
                ],
                "footer": {"text": f"Source: {self._clean_val(job_row.get('site'), 'Unknown').capitalize()}"}
            }]
        }
        
        response = requests.post(self.url, json=payload)
        if response.status_code == 204:
            return True
        else:
            print(f"Webhook Failed: {response.status_code} - {response.text}")
            return False

def run_scraper():
    WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
    GEMINI_KEY = os.getenv('GEMINI_API_KEY')

    if not WEBHOOK_URL or not GEMINI_KEY:
        raise ValueError("CRITICAL ERROR: Missing DISCORD_WEBHOOK_URL or GEMINI_API_KEY environment variables!")

    db = JobDatabase()
    ai = AIEvaluator(api_key=GEMINI_KEY)
    discord = DiscordWebhook(webhook_url=WEBHOOK_URL)

    print(f"Searching for '{CONFIG['search_terms']}' in {CONFIG['location']}...")
    try:
        jobs = scrape_jobs(
            site_name=CONFIG['platforms'],
            search_term=CONFIG['search_terms'],
            location=CONFIG['location'],
            results_wanted=CONFIG['max_results']
        )
    except Exception as e:
        print(f"Scraper error: {e}")
        return

    if jobs.empty:
        print("No jobs found this run.")
        return

    print(f"Found {len(jobs)} jobs. Checking against database...")
    
    new_jobs_count = 0
    for _, row in jobs.iterrows():
        job_url = row.get('job_url')
        if pd.isna(job_url) or not job_url:
            continue
            
        if db.job_exists(job_url):
            continue
            
        new_jobs_count += 1
        title = row.get('title', 'Unknown')
        print(f"\nProcessing new job: {title}")
        
        ai_eval = ai.evaluate_fit(title, str(row.get('description', '')))
        
        if discord.send_job_alert(row, ai_eval):
            db.mark_job_posted(job_url)
            print(f"Sent to Discord (Score: {ai_eval.get('score', 0)})")
            
            time.sleep(CONFIG['webhook_delay'])
            
    print(f"\nFinished! Processed {new_jobs_count} new postings.")

if __name__ == "__main__":
    run_scraper()