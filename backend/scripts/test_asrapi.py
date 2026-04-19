import os
import requests
from dotenv import load_dotenv
load_dotenv()


API_KEY = os.getenv("HF_API_KEY")
ENDPOINT_URL = os.getenv("HF_ENDPOINT_URL")

def transcribe_with_endpoint(audio_path: str) -> str:
    print(f"Sending ({audio_path}) to dedicated GPU server...")
    
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "audio/flac"  
    }
    
    try:
        response = requests.post(ENDPOINT_URL, headers=headers, data=audio_data)
        
        if response.status_code == 200:
            result = response.json()
            return result.get("text", "沒有辨識出文字")
        else:
            print(f"伺服器回傳錯誤 ({response.status_code}): {response.text}")
            return None
            
    except Exception as e:
         print(f"連線失敗: {e}")
         return None

if __name__ == "__main__":
    test_file = "C:/Users/shell/Downloads/ASR_test_audio_3.wav" # cannot be mp4
    
    text = transcribe_with_endpoint(test_file)
    if text:
        print("\n--- Result ---")
        print(text)
        print("----------------\n")