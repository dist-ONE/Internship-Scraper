# Internship Scraper

An automated tool that scrapes software engineering and AI internship listings, evaluates them against your personal resume using the Gemini API, and delivers color-coded alerts directly to a Discord server via webhooks.

Instead of manually scrolling through job boards, this script runs in the background, scores each position based on your specific skills, and pings your Discord channel only when new matches are found.

## Features

* **Discord Webhook Integration:** Delivers rich, formatted job alerts directly to Discord. Scores are color-coded (Green for great matches, Yellow for okay, Red for poor) for instant visual triage.
* **Automated Scraping:** Uses [JobSpy](https://github.com/Bunsly/JobSpy) to pull job postings across major platforms (LinkedIn, Indeed, Glassdoor) simultaneously.
* **AI-Powered Scoring:** Integrates with the Gemini API to analyze job descriptions against a highly customizable candidate profile.
* **Centralized Configuration:** A single `CONFIG` dictionary at the top of the script makes it incredibly easy to change search terms, locations, and your personal resume prompt.
* **Local Tracking:** Uses a local SQLite database to store listings, preventing duplicate Discord pings for jobs you've already seen.
* **Rate-Limit Safe:** Built-in delays ensure Discord's webhook rate limits are respected.

## Prerequisites

1. **Python 3.9+**
2. A **Gemini API Key** (available for free from Google AI Studio).
3. A **Discord Webhook URL** (created in your Discord server's channel integration settings).

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/Internship-Scraper.git
   cd internship-scraper
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *(Ensure your `requirements.txt` includes `jobspy`, `google-generativeai`, `pandas`, and `requests`)*

3. Set up your environment variables. Create a `.env` file in the root directory (or export them in your terminal):
   ```text
   GEMINI_API_KEY=your_gemini_api_key_here
   DISCORD_WEBHOOK_URL=your_discord_webhook_url_here
   ```

## Usage

1. **Configure your search:** Open the Python script and locate the `CONFIG` dictionary at the top. 
2. Update the `search_terms`, `location`, and most importantly, the `candidate_profile` with your actual education, tech stack, and projects.
3. Run the scraper:
   ```bash
   python main.py
   ```
4. The script will fetch the latest listings, score them, send the alerts to your Discord channel, and save the processed URLs to the local SQLite database.

## How it Works (Under the Hood)

1. **Extraction:** JobSpy queries the configured job boards and returns a DataFrame of active listings.
2. **Filtering:** The script checks the local `internships.db` SQLite database to filter out URLs it has already processed.
3. **Evaluation:** The Gemini API processes the job description for each new entry, comparing it against your custom profile to generate a match score (1-10) and a concise reasoning sentence.
4. **Delivery:** The parsed data and AI score are formatted into a Discord rich embed and sent to your webhook. If successful, the job is logged in the database to prevent future duplicate pings.