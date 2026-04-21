# Taipei Trip Agent - Taiwanese speech-to-text

This is the backend API for the Taipei Trip Agent, featuring Taiwanese speech-to-text capabilities integrated with the Breeze-ASR-26 model.

## Prerequisites

- Python 3.10 or higher
- A Hugging Face Inference Endpoint running Breeze-ASR-26

## Installation

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux/macOS
   source .venv/bin/activate


   pip install -r requirements.txt


## Configuration
1. Create a `.env` file in the root directory based on `.env.example`

2. Provide your Hugging Face API key and Endpoint URL:
```
HF_API_KEY=your_actual_key
HF_ENDPOINT_URL=your_actual_endpoint_url
```

## API Reference
### Speech Transcription
* Endpoint: `POST /api/v1/transcribe`

* Description: Transcribes uploaded audio files into Traditional Chinese text using the Breeze-ASR-26 model.

* Request:

    * Content-Type: multipart/form-data
    * Body: file (Binary audio data)
    * Supported Formats: .wav, .m4a, .webm

* Example Request (curl):

```Bash
curl -X POST "(http://127.0.0.1:8000/api/v1/transcribe](http://127.0.0.1:8000/api/v1/transcribe)" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@audio_sample.wav"
```
* Example Response:

```JSON
{
  "text": "transcribed text"
}
```