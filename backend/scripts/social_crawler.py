import sqlite3
import json
import time
import warnings
import os

from dotenv import load_dotenv
from apify_client import ApifyClient
import google.generativeai as genai


warnings.filterwarnings("ignore")
load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'app', 'data', 'taipei_spots.db')

GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

APIFY_API_KEY = os.getenv("APIFY_API_KEY")
client = ApifyClient(APIFY_API_KEY)


# Connect SQLite 
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS social_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT,
    location TEXT,
    sentiment_score REAL,
    crowdedness REAL,
    vibe_tags TEXT,
    original_text TEXT,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')
conn.commit()

# Get threads posts
def fetch_threads_via_apify(keyword="台北 夜市", max_items=5):
    print("Acquiring threads data via Apify...")
    
    # Actor setup 
    actor_id = "igview-owner/threads-search-scraper" 
    run_input = {
        "maxPosts": 20,
        "searchQuery": "台北 隱藏版",
        "sort": "top"
    }
    
    try:
        run = client.actor(actor_id).call(run_input=run_input)
        
        threads_data = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            text_content = item.get("captionText", "")
            url_link = item.get("postUrl", "")
            
            #[debug] output
            print("Caption:", item.get("captionText"))
            print("URL:", item.get("postUrl"))
            print("-" * 30)

            if text_content:
                threads_data.append({
                    "platform": "Threads",
                    "content": text_content,
                    "link": url_link
                })

    except Exception as e:
        print(f"Apify failure: {e}")
        return []
    
    print(f"Acquired {len(threads_data)} items.")
    return threads_data


# Get instagram posts
def fetch_instagram_via_apify(keyword="台北 夜市", max_items=5):
    print("Acquiring instagram data via Apify...")
    
    # Actor setup 
    actor_id = "crawlerbros/instagram-keyword-search-scraper"
    run_input = {
        "humanizeBehavior": True,
        "keywords": [
            "台北隱藏景點",
            "台北秘境"
        ],
        "maxPosts": 5
}
    
    try:
        run = client.actor(actor_id).call(run_input=run_input)
        
        instagram_data = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            text_content = item.get("caption", "")
            url_link = item.get("post_url", "")
            
            #[debug] output
            print("Caption:", item.get("caption"))
            print("URL:", item.get("post_url"))
            print("-" * 30)

            if text_content:
                instagram_data.append({
                    "platform": "Instagram",
                    "content": text_content,
                    "link": url_link
                })

    except Exception as e:
        print(f"Apify failure: {e}")
        return []
    
    print(f"Acquired {len(instagram_data)} items.")
    return instagram_data



# Gemini extraction
def extract_insights_with_gemini(text):
    prompt = f"""
Analyze the following social media post and extract the urban pulse information.
The output must be strictly in JSON format with the following fields:
- "location": The specific location, venue, or area mentioned (return null if not mentioned).
- "sentiment_score": A float representing the sentiment score (from -1.0 for highly negative to 1.0 for highly positive).
- "crowdedness": A float representing the crowdedness index (from 0.0 for completely empty to 1.0 for extremely packed. Use 0.5 if not mentioned).
- "vibe_tags": An array of strings representing the atmosphere or vibe (e.g., ["noisy", "hipster", "chill"]).

Post content: "{text}"
"""
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini extraction failed: {e}")
        return None

# Main pipeline
def run_pipeline():
    print("Start pipeline...\n")
    
    raw_data = fetch_threads_via_apify("台北 隱藏景點", 3)
    #raw_data += fetch_instagram_via_apify("台北 隱藏景點", 3)
    
    for item in raw_data:
        print(f"Handling: {item['content'][:30]}...")
        insights = extract_insights_with_gemini(item['content'])
        
        if insights and insights.get('location'):
            tags_str = json.dumps(insights.get('vibe_tags', []), ensure_ascii=False)
            
            # Write to SQLite
            cursor.execute('''
            INSERT INTO social_trends (platform, location, sentiment_score, crowdedness, vibe_tags, original_text, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['platform'], 
                insights['location'], 
                insights.get('sentiment_score', 0),
                insights.get('crowdedness', 0.5),
                tags_str,
                item['content'],
                item['link']
            ))
            conn.commit()
            print(f"Successfully inserted: {insights['location']}")
        else:
            print("No valid location extracted, skipping...")
            
        time.sleep(2) 

    print("\nAll done")


run_pipeline()

# Test print
print("\nCurrent social trends in database:")
import pandas as pd
df = pd.read_sql_query("SELECT * FROM social_trends", conn)
print(df[['location', 'sentiment_score', 'crowdedness', 'vibe_tags']])

conn.close()