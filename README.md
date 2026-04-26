# 𨑨迌迌 Chito-Go

**賽題分類**：賽題 A · ⾏旅台北

**團隊**：第 19 隊「Kawairoha」

<p align="center">
  <img src="images/chat_recommendation.png" width="800" alt="chat_recommendation.png" />
</p>
<p align="center">
  <img src="images/chat_route.png" width="800" alt="chat_route.png" />
</p>
<p align="center">
  <img src="images/chat_rank_spot.png" width="800" alt="chat_rank_spot.png" />
</p>


一款專為臺北遊客打造的旅遊行程規劃工具，不管是外國旅客、。通過有趣的「城市靈魂探測器測驗」讓我們了解使用者的偏好——包含喜歡的旅遊風格、出沒時間、旅伴、和臺北市的熟悉程度——即可獲得個人化專屬的出遊行程，內含考量天氣狀況、路程、時間、出行方式、社群評價、近年的熱門程度與最佳化路線安排。

## 動機 (Motivation)

在現今的旅遊市場中，尋找景點與規劃路線的成本過高。觀察旅客現有的規劃Workflow，通常被迫拆分為三個孤立的階段：

痛點一：資訊發散，搜尋成本高
旅客需要手動在 IG、Threads 或 PTT 等社群尋找靈感，這些平台資訊更新快但缺乏結構化，難以直接轉化為行程。

痛點二：真實性確認繁瑣
為了避免「網美照騙」，旅客必須額外花時間前往 Google Places 或痞客邦等部落格查看真實評價與詳細資訊，造成嚴重的資訊焦慮。

痛點三：路線規劃耗時且缺乏彈性
即便找齊了景點，旅客最後仍需依賴如「去趣」等路線工具，手動拼湊動線並計算交通時間。若遇上突發天氣變化（如大雨），整個辛苦排好的行程往往直接報廢。

【我們的願景：自動化與個人化的旅遊助理】

我們致力於打破上述繁瑣的步驟，將這個耗時數小時的流程縮短至數秒鐘。透過整合多社群爬蟲技術、天氣感知演算法以及台語語音輸入功能，我們將「找靈感、看評價、排路線」三個步驟無縫合一，打造真正懂使用者的智慧旅遊規劃工具。

> **🌟 核心特色：台語語音支援 & 多方數據整合**
> **整合了 Breeze-ASR-26 模型提供台語語音轉文字（Speech-to-Text）功能**，致力於提升台語使用者的便利性，並推廣本土語言。
> 此外，我們期待可以透過有趣的小測驗讓使用者可以在進行使用者調查時也不覺得枯燥而是充滿滿滿的趣味性，以此為小小願景的我們還額外設計了「城市靈魂探測器」，測試使用者是哪種臺灣飲品。在數據方面我們整合了多個社群平台與訂房網站的數據，提供最豐富、最真實的景點與飯店資訊。

## ✨ 特色功能 (Features)

- **🗣️ 台語語音輸入 (Taiwanese Voice Input)**：原生整合 Breeze-ASR-26 模型，支援流暢的在地化台語語音互動。
- **🌐 全方位數據爬蟲 (Multi-Source Crawling)**：從 `Threads`、`IG`、`Pixnet`、`PTT`、`Booking.com`、`Agoda`、`台灣旅宿網` 以及 `Google Places` 抓取並分析，豐富景點與住宿資訊，也希望透過多元化社群資料搜集顧及各類型使用者的資料皆有被妥善蒐集。
- **🧭 專屬人格化行程 (Personality-Based Routing)**：基於獨創的「城市靈魂探測器」測驗，為不同類型的旅客量身打造專屬行程。
- **動態景點獲取 (Dynamic venue fetching)**：在請求時從 Google Places API 和我們的社群爬蟲資料庫中提取候選名單。
- **天氣感知評分 (Weather-aware scoring)**：雨天優先推薦室內或是具備遮雨功能的半戶外景點，晴天則按使用者類型推薦戶外室內活動。
- **智慧合併與去重 (Smart merge & dedup)**：將來自多個資料源的結果進行標準化、合併及去重複處理。

---

## 🧭 城市靈魂探測器：測出你的專屬旅行基因

為了提供最精準的行程推薦，使用者將在前端進行一場類似人格測驗的問卷，測出屬於你的旅客類型：

1. **台北對你來說，更像是一場什麼樣的邂逅？**
   - A. 初次見面的神祕網友，充滿新鮮感。
   - B. 見過幾次面，還在探索彼此的共同話題。
   - C. 熟到不能再熟的老友，閉著眼都能走到目的地。
2. **當你打開導航地圖，你的手指通常會滑向哪裡？**
   - A. 經典必去！沒在標誌性景點前打卡就不算來過。
   - B. 拒絕人潮！哪裡沒人往哪鑽，越神祕的小徑我越愛。
3. **如果給你一個靜止的午後，縮在城市角落的咖啡廳聞著豆香，你的電力值會？**
   - A. 直衝 100%！這種孤獨的浪漫是我最頂級的充電方式。
   - B. 降到 20%... 靜止太久我會開始焦慮，我需要點熱鬧的聲音。
4. **暫時放下手機，親手完成一件手工藝品（如陶藝、皮革），你覺得那是？**
   - A. 靈魂的冥想。沉浸在「慢工出細活」裡是極致的紓壓。
   - B. 意志力的考驗。我更傾向於直接購買成品來享受生活。
5. **路過一家風格奇特、充滿個人色彩的文創選物店，你的反應是？**
   - A. 像磁鐵一樣被吸進去！我就愛這些奇奇怪怪的小驚喜。
   - B. 保持社交距離。除非真的有需求，否則我很少駐足。
6. **當太陽下山、霓虹燈亮起，你體內的細胞通常會？**
   - A. 全面甦醒！夜晚才是我的主場，越夜越有活力。
   - B. 準備休眠。太陽下山後，我的靈魂也想跟著床鋪合體。
7. **比起在摩天大樓間穿梭，你更渴望讓雙腳踩在什麼樣的土地上？**
   - A. 濕潤的泥土或森林草地，大自然才是我的救贖。
   - B. 乾淨平整的大理石地板，吹著冷氣逛街才是正經事。
8. **今天的你，是要進行一場「限時 24 小時」的忙裡偷閒大作戰嗎？**
   - A. 沒錯！ 戰鬥力已滿，我準備好要在今天內征服這座城市的所有美好。
   - B. 沒這回事！ 我想要的是慢節奏，打算在這裡多賴幾天，慢慢感受。
9. **這次有帶著家裡的「小跟班」一起冒險嗎？**
   - A. 有，帶孩子一起同行！
   - B. 沒有，這次是我的 Me Time～。

### 🍹 測驗結果圖鑑 (6 種專屬旅客類型)

根據測驗結果，使用者會被分類為以下 6 種旅行基因，並搭配專屬的文字敘述與台灣特色飲品插圖：

<p align="center">
  <img src="images/6.png" width="800" alt="6種旅行基因測驗結果總覽" />
</p>

* 🍵 **文青型旅客 —— 【文山包種茶】**
    * *風格：* 步調緩慢、品味細膩，熱愛探索在地藝術、文化與美學空間。
* 🧒 **親子型旅客 —— 【古早味彈珠汽水】**
    * *風格：* 充滿活力與童心，注重行程的趣味性與安全性，尋找能讓孩子放電的好去處。
* 🧋 **不常來 / 初訪者 —— 【珍珠奶茶】**
    * *風格：* 追求台北最經典、最具標誌性的體驗。必去景點和必吃美食一個都不能少。
* 🥣 **夜貓子型旅客 —— 【深夜永和豆漿】**
    * *風格：* 太陽下山才真正甦醒。熱愛夜市、酒吧與越夜越美麗的城市霓虹。
* 🥤 **一日快閃旅客 —— 【甘蔗青茶】**
    * *風格：* 講求效率、清爽直截。要在最短的時間內，將精華景點濃縮進緊湊的行程中。
* 🍋 **野外探索旅客 —— 【野生愛玉冰】**
    * *風格：* 嚮往山林步道與新鮮空氣，相較於水泥叢林，更渴望大自然的療癒與純粹。

---

## Architecture

### System Overview

The system is composed of four independent FastAPI microservices and a Vue 3 SPA. The **Chat Agent** is the primary user-facing backend; it holds session state, calls an LLM with a tool registry, and fans out to the **Place Data Service** for venue lookups. The **Itinerary Planner** is an independent scoring/routing pipeline that can be called directly. The **Speech API** handles Taiwanese ASR as a standalone service.

```
Browser (Vue 3 SPA :5173)
    │
    ├── Conversational flow ──────────────────────────────────────────────►  Chat Agent (:8100)
    │                                                                               │
    │                                                                               ├── LLM Layer
    │                                                                               │     ├── Gemini 2.5 Flash  (primary)
    │                                                                               │     ├── Claude Sonnet 4.6 (fallback)
    │                                                                               │     └── OpenRouter GPT-4.1-mini (alt)
    │                                                                               │
    │                                                                               ├── Session Store (in-memory + TTL sweeper)
    │                                                                               │
    │                                                                               └── Tool Registry
    │                                                                                     ├── place_search ──────────────────► Place Data Service (:8000)
    │                                                                                     │                                           │
    │                                                                                     │                                    PostgreSQL (venues, social)
    │                                                                                     │
    │                                                                                     └── route_advisor ─────────────────► Google Maps API
    │
    ├── Itinerary planning ──────────────────────────────────────────────► Itinerary Planner (:8000*)
    │       POST /api/v1/itinerary                                                  │
    │                                                                               ├── Candidate Providers (parallel fetch)
    │                                                                               │     ├── Google Places API (New) ──┐
    │                                                                               │     ├── Crawler / Social API ─────┼─► normalize → merge/dedup → filter
    │                                                                               │     └── Local SQLite seed ─────────┘
    │                                                                               │
    │                                                                               ├── ScoringEngine
    │                                                                               │     └── interest(40%) + weather(30%) + trend(20%) + budget(10%)
    │                                                                               │
    │                                                                               └── RouteOptimizer
    │                                                                                     └── Greedy nearest-neighbor with time budget
    │
    └── Voice input ──────────────────────────────────────────────────────► Speech API (Hugging Face)
            (Taiwanese Mandarin audio)                                              └── Breeze-ASR-26
```

> \* Itinerary Planner and Place Data Service share the default port `:8000` — run only one at a time unless ports are overridden.

### Services

| Service | Directory | Port | Responsibility |
|---------|-----------|------|----------------|
| **Chat Agent** | `backend/Chat_Agent/` | 8100 | LLM orchestration, session management, tool dispatch |
| **Itinerary Planner** | `backend/app/` | 8000 | Score and route venues into a day plan (SQLite seed) |
| **Place Data Service** | `backend/Chitogo_DataBase/` | 8000 | PostgreSQL store for Taipei venues; search, nearby, recommend APIs |
| **Speech API** | `backend/taiwanese_speech/` | — | Taiwanese speech-to-text via Breeze-ASR-26 on Hugging Face |
| **Frontend** | `frontend/` | 5173 | Vue 3 + Vite SPA |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Vue 3, Vite 5, TypeScript 5, Axios, vue-router 4 |
| **Backend runtime** | Python 3.11, FastAPI 0.111, Pydantic v2, uvicorn, httpx |
| **LLM providers** | Gemini 2.5 Flash (primary), Claude Sonnet 4.6 (fallback), OpenRouter GPT-4.1-mini |
| **Databases** | SQLite via aiosqlite (Itinerary Planner), PostgreSQL via SQLAlchemy 2.x (Place Data Service) |
| **Speech / ASR** | Hugging Face — Breeze-ASR-26 (Taiwanese Mandarin) |
| **External APIs** | Google Places API (New), OpenWeatherMap, Google Maps Directions |
| **Data sources** | Google Places, Threads, IG, Pixnet, PTT, Booking.com, Agoda, 台灣旅宿網 |
| **Cache** | In-memory TTL dict (candidates: 5 min, weather: 30 min, sessions: configurable) |
| **Testing** | pytest, pytest-asyncio, httpx async test client |

---

## Prerequisites

### 1. Python 3.11

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
python3.11 --version
```

**Linux (Fedora/RHEL):**
```bash
sudo dnf install python3.11
```

> If `python3.11` is not available on your distro, add the deadsnakes PPA first:
> ```bash
> sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt update
> sudo apt install python3.11 python3.11-venv
> ```

**Windows:**
1. Download Python **3.11.x** from https://www.python.org/downloads/ (do not use 3.12+)
2. Run the installer — **check "Add Python to PATH"** before clicking Install
3. Open a new terminal and verify:
```cmd
python --version
```
> If `python` is not found, try `py -3.11 --version`

---

### 2. Node.js 20

**Linux:**
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc        # or ~/.zshrc
nvm install 20
nvm use 20
node --version          # should print v20.x.x
```

**Windows:**
1. Download the Node.js 20 LTS installer from https://nodejs.org/
2. Run the installer (accept defaults)
3. Verify in a new terminal:
```cmd
node --version
npm --version
```

---

### 3. PostgreSQL (required for the Place Data Service)

**Linux:**
```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**Windows:**
1. Download the PostgreSQL 15+ installer from https://www.postgresql.org/download/windows/
2. Run the installer with default settings — **remember the password** you set for the `postgres` superuser
3. PostgreSQL starts automatically as a Windows service

**Both — create the application user and database:**

```bash
# Linux: switch to the postgres system user first
sudo -u postgres psql

# Windows: open pgAdmin, or launch from Start > PostgreSQL > SQL Shell (psql)
# then connect as the postgres superuser
```

Inside the psql prompt, run:
```sql
CREATE USER chitogo_user WITH PASSWORD 'kawairoha';
CREATE DATABASE chitogo OWNER chitogo_user;
GRANT ALL PRIVILEGES ON DATABASE chitogo TO chitogo_user;
\q
```

---

### 4. API Keys

Obtain the following keys before starting the services:

| Key | Where to get it | Required for |
|-----|----------------|--------------|
| `GEMINI_API_KEY` | https://aistudio.google.com/app/apikey | Chat Agent (primary LLM) |
| `GOOGLE_PLACES_API_KEY` | https://console.cloud.google.com/apis/credentials — enable **Places API** | Itinerary Planner |
| `GOOGLE_MAPS_API_KEY` | Same GCP project — enable **Maps JavaScript API** + **Directions API** | Chat Agent routing + frontend |
| `OPENWEATHER_API_KEY` | https://openweathermap.org/api (free tier) | Itinerary Planner weather |
| `CWA_API_KEY` | https://opendata.cwa.gov.tw/devManual/insrtuction | Chat Agent weather |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/ | Chat Agent (optional fallback) |
| `OPENROUTER_API_KEY` | https://openrouter.ai/ | Chat Agent (optional fallback) |

---

## Setup

### Step 1 — Clone the repository

```bash
git clone https://github.com/YuChianWeng/Chitogo_Kawairoha.git
cd Chitogo_Kawairoha
```

---

### Step 2 — Copy environment files

**Linux:**
```bash
cp backend/.env.example            backend/.env
cp backend/Chat_Agent/.env.example backend/Chat_Agent/.env
cp backend/Chitogo_DataBase/.env.example backend/Chitogo_DataBase/.env
cp backend/taiwanese_speech/.env.example backend/taiwanese_speech/.env
cp frontend/.env.example           frontend/.env
```

**Windows (CMD):**
```cmd
copy backend\.env.example            backend\.env
copy backend\Chat_Agent\.env.example backend\Chat_Agent\.env
copy backend\Chitogo_DataBase\.env.example backend\Chitogo_DataBase\.env
copy backend\taiwanese_speech\.env.example backend\taiwanese_speech\.env
copy frontend\.env.example           frontend\.env
```

---

### Step 3 — Fill in the `.env` files

**`backend/.env`** (Itinerary Planner):
```env
OPENWEATHER_API_KEY=your_openweathermap_key
GOOGLE_PLACES_API_KEY=your_google_places_key
GEMINI_API_KEY=your_gemini_key
USE_LLM=false
DB_PATH=./taipei.db
WEATHER_CACHE_TTL_MINUTES=30
CANDIDATE_CACHE_TTL_MINUTES=5
# For demos without a real weather API: MOCK_WEATHER=rain
```

**`backend/Chat_Agent/.env`** (LLM Agent):
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.5-flash
ANTHROPIC_API_KEY=optional_anthropic_key
OPENROUTER_API_KEY=optional_openrouter_key
GOOGLE_MAPS_API_KEY=your_google_maps_key
DATA_SERVICE_BASE_URL=http://localhost:8000
CWA_API_KEY=your_cwa_key
```

**`backend/Chitogo_DataBase/.env`** (Place Data Service):
```env
DATABASE_URL=postgresql://chitogo_user:kawairoha@localhost:5432/chitogo
```

**`frontend/.env`**:
```env
VITE_GOOGLE_MAPS_API_KEY=your_google_maps_browser_key
```

---

### Step 4 — Create the Python virtual environment and install dependencies

**Linux:**
```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r Chat_Agent/requirements.txt
pip install -r Chitogo_DataBase/requirements.txt
cd ..
```

**Windows (PowerShell):**
```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
pip install -r Chat_Agent\requirements.txt
pip install -r Chitogo_DataBase\requirements.txt
cd ..
```

> If PowerShell blocks the activate script, run this once in an admin terminal:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

---

### Step 5 — Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Running

You need **4 separate terminals**, all opened from the repo root.

---

### Terminal 1 — Place Data Service (PostgreSQL, port 8000)

**Linux:**
```bash
cd backend/Chitogo_DataBase
source ../.venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Windows:**
```powershell
cd backend\Chitogo_DataBase
..\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verify: http://localhost:8000/api/v1/health/db — should return `{"status":"ok"}`

---

### Terminal 2 — Chat Agent (LLM orchestration, port 8100)

**Linux:**
```bash
cd backend/Chat_Agent
source ../.venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

**Windows:**
```powershell
cd backend\Chat_Agent
..\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

Verify: http://localhost:8100/docs — should show the Swagger UI.

---

### Terminal 3 — Itinerary Planner (SQLite, port 8001)

> The Itinerary Planner and the Place Data Service both default to port `8000`. Since Terminal 1 already uses `8000`, start this service on `8001`.

**Linux:**
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

**Windows:**
```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Verify: http://localhost:8001/docs

---

### Terminal 4 — Frontend (Vue 3, port 5173)

```bash
cd frontend
npm run dev
```

Open http://localhost:5173 in your browser.

---

### Quick-start (Itinerary Planner + Frontend only, no PostgreSQL needed)

If you only want the standalone trip-planning form without the Chat Agent or PostgreSQL, the Makefile starts both with one command:

**Linux:**
```bash
make dev
```

**Windows:** Install `make` first, then run `make dev`:
```powershell
# Option A — winget
winget install GnuWin32.Make

# Option B — Chocolatey
choco install make
```

---

### Verify everything is running

| URL | Expected response |
|-----|-------------------|
| http://localhost:5173 | Vue frontend — main app UI |
| http://localhost:8000/api/v1/health/db | `{"status":"ok"}` (Place Data Service) |
| http://localhost:8001/api/v1/health | `{"status":"ok"}` (Itinerary Planner) |
| http://localhost:8100/docs | Chat Agent Swagger UI |

---

### Common issues

**`python3.11: command not found` (Linux)** — Install via the deadsnakes PPA (see Prerequisites above).

**`ModuleNotFoundError` when starting a service** — The virtualenv is not activated in that terminal. Re-run the `source .venv/bin/activate` (Linux) or `.venv\Scripts\Activate.ps1` (Windows) command.

**PostgreSQL connection refused** — Check the service is running:
- Linux: `sudo systemctl status postgresql`
- Windows: open Services (`services.msc`) and look for `postgresql-x64-15` (or your installed version)

**Port already in use** — Another process is occupying that port. Either stop it or change the `--port` value when starting uvicorn.

**Windows `Activate.ps1` is blocked** — Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once in an admin PowerShell window.

Open http://localhost:5173 in your browser.

Interactive API docs:
- Itinerary Planner: http://localhost:8000/docs
- Chat Agent: http://localhost:8100/docs

---

## Environment Variables

### Itinerary Planner (`backend/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_PLACES_API_KEY` | (empty) | Google Places API key for live venue fetching |
| `CRAWLER_API_URL` | (empty) | Crawler/social source endpoint URL |
| `CANDIDATE_CACHE_TTL_MINUTES` | `5` | Cache duration for external candidate results |
| `OPENWEATHER_API_KEY` | (empty) | OpenWeatherMap API key |
| `MOCK_WEATHER` | (empty) | Override weather for demos: `rain`, `clear`, `cloudy` |
| `USE_LLM` | `false` | Enable LLM-based reason generation |
| `DB_PATH` | `./taipei.db` | SQLite database path (seed/fallback data) |
| `WEATHER_CACHE_TTL_MINUTES` | `30` | Weather cache duration in minutes |

### Chat Agent (`backend/Chat_Agent/.env`)

| Variable | Description |
|----------|-------------|
| `LLM_PROVIDER` | `gemini`, `anthropic`, or `openrouter` |
| `GEMINI_API_KEY` | Gemini API key |
| `ANTHROPIC_API_KEY` | Anthropic API key (Claude Sonnet 4.6 fallback) |
| `OPENROUTER_API_KEY` | OpenRouter API key (GPT-4.1-mini alternative) |
| `DATA_SERVICE_BASE_URL` | URL of the Place Data Service (default: `http://localhost:8000`) |

---

## API Reference

### Chat Agent

#### `POST /api/v1/chat`

Send a message within a session. The agent maintains conversation history and calls tools (place search, route planning) as needed.

**Request body:**

```json
{
  "session_id": "b8f20dcd-1894-475e-8895-891b73fc473b",
  "message": "推薦我大安區適合下雨天的景點",
  "lat": 25.033,
  "lng": 121.543
}
```

**Response:**

```json
{
  "session_id": "b8f20dcd-...",
  "reply": "根據天氣狀況，以下是幾個適合雨天的室內景點：...",
  "tool_calls": ["place_search"],
  "candidates": [ ... ]
}
```

#### `GET /api/v1/trip/should_go_home`

Checks whether the user should head home based on current location and remaining itinerary time.

```
GET /api/v1/trip/should_go_home?session_id=<id>&lat=25.077&lng=121.573
```

### Itinerary Planner

#### `POST /api/v1/itinerary`

Generate a personalized itinerary.

**Request body:**

```json
{
  "district": "Da'an",
  "start_time": "10:00",
  "end_time": "18:00",
  "interests": ["culture", "food", "cafe"],
  "budget": "medium",
  "companion": "couple",
  "indoor_pref": "both"
}
```

**Response:**

```json
{
  "status": "ok",
  "district": "Da'an",
  "date": "2026-03-30",
  "weather_condition": "clear",
  "stops": [
    {
      "order": 1,
      "venue_id": "v001",
      "name": "National Palace Museum",
      "district": "Shilin",
      "category": "museum",
      "suggested_start": "10:00",
      "suggested_end": "12:00",
      "duration_minutes": 120,
      "travel_minutes_from_prev": 0,
      "reason": "A popular indoor museum perfect for exploring Taiwanese history...",
      "tags": ["culture", "history", "art"],
      "cost_level": "low",
      "indoor": true
    }
  ],
  "total_stops": 3,
  "total_duration_minutes": 360
}
```

**Valid field values:**
- `district`: `Zhongzheng`, `Da'an`, `Zhongshan`, `Xinyi`, `Wanhua`, `Songshan`, `Neihu`, `Shilin`, `Beitou`, `Wenshan`, `Nangang`, `Datong`
- `budget`: `low`, `medium`, `high`
- `companion`: `solo`, `couple`, `family`, `friends`
- `indoor_pref`: `indoor`, `outdoor`, `both`
- `interests`: `food`, `culture`, `shopping`, `nature`, `nightlife`, `art`, `history`, `cafe`, `sports`, `temple`

#### `GET /api/v1/health`

Liveness check.

#### `GET /api/v1/venues`

List seeded venues (debug endpoint).

---

## Scoring

Venues are ranked by a weighted score:

| Factor | Weight | Description |
|--------|--------|-------------|
| Interest match | 40% | How well the venue's tags match selected interests |
| Weather suitability | 30% | Indoor/outdoor preference adjusted for current weather |
| Trend score | 20% | Venue popularity signal (0.0–1.0) |
| Budget compatibility | 10% | Venue cost level vs. user budget |

---

## Data Flow

1. **Fetch** — Google Places + Crawler queried in parallel (cached results used when available)
2. **Normalize** — External results mapped to internal `Venue` schema, districts assigned from coordinates
3. **Merge & Dedup** — Combined by name similarity and 50 m proximity; trend scores merged (max)
4. **Filter** — District proximity, indoor preference, cost level (relaxed progressively if < 3 results)
5. **Fallback** — If external sources return < 3 venues, local seed data fills the gap
6. **Score** — Weighted scoring: interest + weather + trend + budget
7. **Route** — Greedy nearest-neighbor ordering within time budget
8. **Respond** — Assembled itinerary with arrival times, durations, and reasons

---

## Tests

```bash
# Itinerary Planner
cd backend && source .venv/bin/activate
pytest tests/ -v --cov=app --cov-report=term-missing

# Chat Agent
cd backend/Chat_Agent
pytest tests/ -v

# Place Data Service
cd backend/Chitogo_DataBase
pytest tests/ -v
```

---

## Project Structure

```
backend/
├── app/                          # Itinerary Planner service (SQLite)
│   ├── main.py                   # App factory, CORS, DB init
│   ├── config.py                 # Settings (pydantic-settings)
│   ├── api/v1/
│   │   ├── itinerary.py          # POST /itinerary handler
│   │   └── router.py
│   ├── providers/
│   │   ├── base.py               # CandidateProvider protocol
│   │   ├── google_places.py      # Google Places API (New) provider
│   │   ├── crawler.py            # Crawler/social source provider
│   │   ├── cache.py              # In-memory TTL cache
│   │   └── aggregator.py         # Merge, dedup, fallback orchestrator
│   ├── models/
│   │   ├── db.py                 # SQLite access, Venue entity, seeding
│   │   └── schemas.py            # Pydantic request/response models
│   ├── services/
│   │   ├── scoring.py            # Venue scoring engine
│   │   ├── routing.py            # Route optimizer
│   │   └── itinerary_builder.py  # Pipeline orchestrator
│   └── data/
│       └── venues.json           # 35 curated Taipei venues (fallback)
│
├── Chat_Agent/                   # LLM Agent orchestration service
│   └── app/
│       ├── main.py               # App factory (create_app)
│       ├── chat/                 # Message handler, trace store, schemas
│       ├── session/              # Session store + TTL sweeper
│       └── tools/                # Tool registry, place/route adapters
│
├── Chitogo_DataBase/             # Place Data Service (PostgreSQL)
│   └── app/
│       ├── main.py
│       ├── db.py                 # SQLAlchemy engine + base
│       ├── models/               # ORM models
│       ├── routers/              # health, places, retrieval
│       └── services/             # ingestion, category
│
├── taiwanese_speech/             # Speech-to-text (Hugging Face Breeze-ASR-26)
└── scripts/                      # social_crawler.py, test_asrapi.py

frontend/
└── src/
    ├── App.vue
    ├── main.ts
    ├── pages/
    │   ├── HomePage.vue
    │   └── TripPage.vue
    ├── services/api.ts           # Axios API client
    └── types/
        ├── itinerary.ts
        └── chat.ts

specs/                            # Feature specs and implementation plans
```
