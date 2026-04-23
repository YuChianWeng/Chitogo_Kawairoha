import sqlite3
import json
import time
import warnings
import os
import pandas as pd
from dotenv import load_dotenv
from apify_client import ApifyClient
from openai import OpenAI


warnings.filterwarnings("ignore")
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client_ai = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

APIFY_API_KEY = os.getenv("APIFY_API_KEY")
client = ApifyClient(APIFY_API_KEY)

# Connect SQLite 
conn = sqlite3.connect('taipei_spots.db')
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
def fetch_threads_via_apify(keyword, max_items=5):
    print("Acquiring threads data via Apify...")
    
    # Actor setup 
    actor_id = "igview-owner/threads-search-scraper" 
    run_input = {
        "maxPosts": max_items,
        "searchQuery": keyword,
        "sort": "top"
    }
    
    try:
        run = client.actor(actor_id).call(run_input=run_input, wait_secs=300)
        
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


# Get threads comments
def fetch_threads_comments_via_apify(post_url, max_items=5):
    print("Acquiring threads data via Apify...")
    
    # Actor setup 
    actor_id = "futurizerush/threads-replies-scraper"
    run_input = {
         "max_replies": 5,
         #"before": "2025-7-15",
        "post_urls": [
        {
            "url": post_url
        }
    ]
}
    try:
        run = client.actor(actor_id).call(run_input=run_input)
        
        threads_data = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            if item.get("original_post") != "comment":
                continue
            text_content = item.get("text_content", "")
            url_link = item.get("reply_url", "")
            
            #[debug] output
            print("commentCaption:", text_content)
            print("URL:", url_link)
            print("-" * 30)

            if text_content:
                threads_data.append({
                    "platform": "Threads_comment",
                    "content": text_content,
                    "link": url_link
                })

    except Exception as e:
        print(f"Apify failure: {e}")
        return []
    
    print(f"Acquired {len(threads_data)} items.")
    return threads_data


# Get instagram posts
def fetch_instagram_via_apify(keyword, max_items=5):
    print("Acquiring instagram data via Apify...")
    
    # Actor setup 
    actor_id = "crawlerbros/instagram-keyword-search-scraper"
    run_input = {
        "humanizeBehavior": True,
        "keywords": [
            keyword
        ],
        "maxPosts": max_items
}
    
    try:
        run = client.actor(actor_id).call(run_input=run_input)
        
        instagram_data = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            text_content = item.get("caption", "")
            url_link = item.get("post_url", "")
            
            #[debug] output
            print("Caption:", text_content)
            print("URL:", url_link)
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


def extract_insights_with_llm(text):
    prompt = f"""
    Analyze the following social media post and extract urban pulse information.

[STRICT FILTERING RULES]:
1. "location": Must be a SPECIFIC entity such as a business name, restaurant, tourist attraction, or landmark (e.g., "Taipei 101", "Din Tai Fung", "Daan Forest Park").
2. DO NOT extract broad areas, districts, or cities (e.g., "Daan District", "Taipei", "East District") as the location.
3. If no specific business or landmark is mentioned, set "location" to null.
4. If "location" is null, you may leave other fields with default values.

[OUTPUT FORMAT]:
Return strictly in JSON format:
{{
  "location": "Specific name of the venue or landmark (string, or null if none)",
  "sentiment_score": "Float between -1.0 (negative) and 1.0 (positive)",
  "crowdedness": "Float between 0.0 (empty) and 1.0 (packed). Use 0.5 as default",
  "vibe_tags": ["tag1", "tag2"]
}}

Post content: "{text}"
    """
    try:
        response = client_ai.chat.completions.create(
            model="llama-3.3-70b-versatile", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Extraction failed: {e}")
        return None



# Main pipeline
def run_pipeline():
    print("Start pipeline...\n")    

    # --- get thread and comments ---
    posts = fetch_threads_via_apify("台北 隱藏景點", 20)
    post_urls = [p['link'] for p in posts if p.get('link')]
    comments = fetch_threads_comments_via_apify(post_urls, 5)
    raw_data = posts + comments
    # -- - end of get thread and comments ---

    raw_data += fetch_instagram_via_apify("台北 隱藏景點", 20)

    for item in raw_data:
        print(f"Handling: {item['content'][:30]}...")
        insights = extract_insights_with_llm(item['content'])
        
        if insights and insights.get('location'):
            tags_str = json.dumps(insights.get('vibe_tags', []), ensure_ascii=False)
            
            # Write to SQLite
            cursor.execute('''
           INSERT OR IGNORE INTO social_trends (platform, location, sentiment_score, crowdedness, vibe_tags, original_text, source_url)
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
df = pd.read_sql_query("SELECT * FROM social_trends", conn)
print(df[['location', 'sentiment_score', 'crowdedness', 'vibe_tags']])

conn.close()