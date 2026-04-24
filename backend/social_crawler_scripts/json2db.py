import json
import sqlite3
import requests
import time
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
INPUT_FILE = "yourdata.json"
DB_FILE = "yourdatabase.db"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client_ai = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS social_trends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        location TEXT,
        address TEXT,
        google_place_id TEXT,
        sentiment_score REAL,
        crowdedness REAL,
        vibe_tags TEXT,
        original_text TEXT,
        source_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    return conn

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
        print(f"LLM Extraction failed: {e}")
        return None

def get_google_info(location_name):
    if not location_name: 
        return "", ""
    
    endpoint = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        'input': location_name,
        'inputtype': 'textquery',
        'fields': 'place_id,formatted_address',
        'language': 'zh-TW',
        'key': GOOGLE_API_KEY
    }
    try:
        res = requests.get(endpoint, params=params).json()
        candidates = res.get('candidates', [])
        if candidates:
            return candidates[0].get('formatted_address', ''), candidates[0].get('place_id', '')
    except Exception as e:
        print(f"Google API search {location_name} fail: {e}")
    return "", ""

def process_data():
    conn = init_db()
    cursor = conn.cursor()

    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
    except FileNotFoundError:
        print(f"Cannot find {INPUT_FILE}")
        return

    print(f"-- Starting to process {len(data_list)} pieces of data --")

    for item in data_list:
        original_text = item.get("preview", "")
        if not original_text:
            continue
            
        print(f"\n-- Processing -- Analyzing text: {original_text[:30]}...")
        
        
        insights = extract_insights_with_llm(original_text)
        if not insights:
            print("Skipped: LLM failed to return valid format")
            continue

        location_name = insights.get("location")
        sentiment_score = insights.get("sentiment_score", 0.0)
        crowdedness = insights.get("crowdedness", 0.5)
        
        vibe_tags_list = insights.get("vibe_tags", [])
        vibe_tags_str = ",".join(vibe_tags_list) if isinstance(vibe_tags_list, list) else ""

        addr, place_id = "", ""
        
        if location_name:
            print(f"LLM extracted [{location_name}] Successfully，Searching on Google Maps...")
            addr, place_id = get_google_info(location_name)
            time.sleep(0.5) 
        else:
            print("ℹLLM cannot extract location (location is null)")

       
        data_tuple = (
            "ifoodie",      # platform
            location_name or "",   # location
            addr,                  # address
            place_id,              # google_place_id
            sentiment_score,       # sentiment_score
            crowdedness,           # crowdedness
            vibe_tags_str,         # vibe_tags
            original_text,         # original_text
            item.get("url", "")    # source_url
        )

        cursor.execute('''
            INSERT INTO social_trends (
                platform, location, address, google_place_id, 
                sentiment_score, crowdedness, vibe_tags, original_text, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data_tuple)
        
        conn.commit()
        print("Successfully inserted into DB.")
    conn.close()
    print("\n-- Processing completed --")

if __name__ == "__main__":
    process_data()