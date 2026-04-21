# Chitogo Chat Agent — 後端工程進度報告

**日期：** 2026-04-21
**分支：** `003-agent-orchestration-backend`
**報告對象：** 內部團隊、指導老師、技術審查者

---

## 執行摘要

Chitogo Chat Agent 是一個台北旅遊 AI 助理的後端 orchestration 服務，以 Python 3.11 + FastAPI 構建，連接外部 Data Service（場地資料）和 Google Maps（路線估算），並透過統一的 `LLMClient` 支援 Gemini、Anthropic 與 OpenRouter。實作上已完成從使用者輸入到結構化行程生成、行程修改、trace 可觀測性的完整端到端流程；近期已把原本脆弱的 regex / keyword intent、preference、replan parsing 邏輯，改成以 LLM 為主、deterministic guardrail 為輔。全套測試目前為 **110 個全通過**，架構已具備 demo 與前端整合能力。

---

## 1. 專案概述

### 這個專案目前是什麼

這是一個對話式 AI 旅遊規劃後端服務，使用者透過聊天訊息輸入需求（例如：「我想從大安區出發，下午排一個美食行程」），服務會完成意圖分類、偏好萃取、場地查詢、行程組裝等步驟，最終回傳結構化的 `Itinerary` 物件與自然語言回覆。服務本身不直接存取場地資料庫，而是透過 HTTP 呼叫外部 Data Service 來取得推薦結果。

### 已完成到哪一層

根據 git 提交紀錄，已完成 Phase 1 至 Phase 7：

- Phase 1：專案框架建立
- Phase 2：基礎 FastAPI 結構、健康檢查
- Phase 3：意圖分類、偏好萃取模組
- Phase 4：工具適配器（PlaceToolAdapter、RouteToolAdapter）
- Phase 5：AgentLoop 與 ResponseComposer
- Phase 6：ItineraryBuilder（行程組裝）、Replanner（行程修改）
- Phase 7：TraceRecorder、TraceStore、Trace API，以及整合強化

### 現在可用到什麼程度

服務目前是 **integration-ready** 的狀態：後端 API 介面完整、邏輯清晰、測試全綠，但尚未接上真實的前端，且 session 狀態全存在記憶體中，沒有持久化層。在有外部 Data Service 與 Google Maps API key 的環境下，啟動即可運作。

---

## 2. 系統架構現況

### 整體分層結構

服務以 **application factory** 模式啟動（`app/main.py`），在 lifespan 階段啟動 TTL session sweeper，並在 ASGI 關閉時優雅停止。整體架構分為以下六個獨立職責域：

**API 層（`app/api/v1/`）** 負責 HTTP 路由定義，包含 health、chat message、trace 三組路由。路由層只負責入口驗證與 dependency injection，不含業務邏輯。

**Orchestration 層（`app/orchestration/`）** 是本服務的智能核心。`IntentClassifier` 已改成 **LLM-first**，要求模型直接回傳結構化 JSON（intent、confidence、needs_clarification、missing_fields、extracted_slots），解析失敗時才安全退回 `CHAT_GENERAL`。`PreferenceExtractor` 也改成 **LLM-first**，並在進入 `Preferences` model 前做一層 normalization，把像 `["朋友"]`、`"中等"`、`"咖啡廳"`、`null` list 欄位等常見 provider 輸出變形收斂成 canonical 值。`LanguageDetection` 透過 CJK 字元比例判斷是否為繁體中文，決定回覆語言。

**Chat 層（`app/chat/`）** 包含整個對話流程：`MessageHandler` 是單一請求的 application service，對 `AgentLoop`、`ItineraryBuilder`、`Replanner`、`ResponseComposer` 作統一呼叫與錯誤處理。`AgentLoop` 已從純 deterministic tool selection 升級為 **LLM tool planning + deterministic validation/fallback**。`TraceRecorder` 在每個步驟埋點計時，最終寫入 `TraceStore`。

**Tool 層（`app/tools/`）** 定義 `ToolRegistry` 統一管理工具清單，`PlaceToolAdapter` 封裝對外部 Data Service 的 HTTP 呼叫，`RouteToolAdapter` 先嘗試 Google Maps Directions API，失敗時以 haversine 球面公式進行估算。

**Session 層（`app/session/`）** 以 `InMemorySessionStore` 管理所有對話狀態，`SessionManager` 提供型別安全的 mutation API，`sweeper.py` 每 60 秒清除超過 TTL（預設 30 分鐘）的閒置 session。

**LLM 層（`app/llm/client.py`）** 提供 `LLMClient`，封裝 Gemini（預設）、Anthropic 與 OpenRouter 三條路徑的非同步文字和 JSON 生成。OpenRouter 路徑使用既有 `httpx`，不引入新的 SDK，並已補上較寬鬆的 read timeout 以支援較慢的模型回應。

---

## 3. 已完成功能整理

### Phase 2–3：基礎架構與智能核心

健康檢查端點（`GET /api/v1/health`）會主動 probe 外部 Data Service，回傳 `ok` 或 `degraded`。`Settings`（`app/core/config.py`）以 `pydantic-settings` 管理所有環境變數，包含 LLM provider 切換、CORS 設定、路線提供商選擇等，並有 model-level cross-validation（例如選擇 Gemini 時強制要求 `GEMINI_API_KEY`）。

意圖分類目前支援四種意圖：`GENERATE_ITINERARY`、`REPLAN`、`EXPLAIN`、`CHAT_GENERAL`。目前不再依賴 `RuleBasedClassifier`；模型必須直接回傳 slot-aware JSON，後端再做型別修正與缺欄位檢查。這讓像「換成」、「改到」、「要去」這種過去 regex 容易漏掉的語句能正常分類。

### Phase 4：工具適配器

`PlaceToolAdapter` 提供 `search_places`、`recommend_places`、`nearby_places`、`batch_get_places`、`get_categories`、`get_stats`。實作包含 500 錯誤的一次自動重試、timeout 處理、以及 malformed payload 的結構化 error result 回傳。`RouteToolAdapter` 在 Google Maps 可用時回傳精確路線時間，否則以 haversine 估算，並在 `RouteResult.status` 明確標記為 `fallback`。

### Phase 5：AgentLoop 與回覆組合

`AgentLoop` 現在會先嘗試用 LLM 規劃 `place_search` / `place_recommend` / `place_nearby` 的工具選擇與參數，再以 deterministic validation 過濾不合法工具、錯誤 district 或錯誤 category。對於已知 `interest_tags`（例如 `cafes`），後端仍會強制使用對應的 Data Service 語彙映射（例如 `food` + `cafe`），避免 LLM 自由文字 `keyword` 把查詢帶偏。若 planned `place_search` 查空，還會自動 fallback 到 `place_recommend`。`ResponseComposer` 負責將原始資料組成自然語言回覆，支援中文（zh-TW）和英文兩種語言路徑。

### Phase 6：行程生成與修改

`ItineraryBuilder`（`app/chat/itinerary_builder.py`）依照使用者的時間段長度決定站點數（時段 ≤ 3h → 2 站，≤ 5h → 3 站，其他 → 4 站），並呼叫 `route_estimate` 工具為每段腿估算時間、分配到站時間，最後產出符合 `Itinerary` schema 的完整結構。

`Replanner`（`app/chat/replanner.py`）支援三種操作：`replace`（取代指定站點）、`insert`（在指定位置插入新站點）、`remove`（移除指定站點）。解析時先走 regex fast path；若站點序號或操作意圖不清楚，再 fallback 到 LLM parsing。執行上會盡量重用未改變腿的舊路線資料，不需要全部重新估算。操作前也會優先從 `session.cached_candidates` 中找未使用的備選場地，減少對外部工具的呼叫次數。

### Phase 7：可觀測性與強化

`TraceRecorder` 提供 context manager 介面（`with recorder.step("name") as step`），每個步驟自動記錄耗時、狀態（success / fallback / error / skipped）、摘要、detail dict 和 warning。`TraceStore` 是有界限（最多 200 條，可設定）的 in-memory store，以 asyncio.Lock 保護並發寫入，最舊的條目自動驅逐。Trace API（`GET /api/v1/chat/traces` 與 `GET /api/v1/chat/traces/{trace_id}`）讓開發者可以在 debug 階段即時審查每次請求的執行步驟。

`MessageHandler` 對每個步驟都做了 try/except fallback 處理：classifier 失敗時退回 `CHAT_GENERAL`，preference extraction 失敗時退回純規則萃取，merge 失敗時保留舊偏好。整個請求失敗也確保 trace 一定被寫入 store，不會因為例外而遺失。

---

## 4. API / 後端能力現況

### 主要 Endpoint 清單

**`POST /api/v1/chat/message`** — 主要的對話端點，接受 `session_id`（選填，自動建立 UUID）、`message`（最多 4000 字元）、`user_context`（選填，lat/lng）。回傳包含 intent、preferences 更新、candidates 清單、itinerary（如有）、routing_status、tool_results_summary。這是前端整合的核心接口。

**`GET /api/v1/health`** — 回傳服務狀態與 Data Service 連通性，供 load balancer 或監控系統使用。

**`GET /api/v1/chat/traces`** — 列出最近 N 筆 trace 摘要，支援 `session_id` 過濾和 `limit` 分頁（預設 20，最多 200）。主要供開發人員和 debug 使用。

**`GET /api/v1/chat/traces/{trace_id}`** — 取得單筆 trace 的完整步驟列表與耗時，404 回傳結構化 `ErrorEnvelope`。

### 主流程能做什麼

對話端點支援以下四條流程路徑，由 `MessageHandler` 根據分類結果分派：

一、**需要澄清（clarification）**：偏好不足（缺少出發點或時間段）時，以語言感知的方式請使用者補充，不呼叫任何工具。

二、**場地探索（discovery）**：使用者說「推薦」或「附近」等詞時，呼叫 AgentLoop 查詢場地，回傳 candidates 清單並快取於 session。

三、**行程生成（generate itinerary）**：整合 AgentLoop 查詢 + ItineraryBuilder 組裝，回傳含 stops、legs、arrival_time 的完整 `Itinerary`。

四、**行程修改（replan）**：解析修改請求（replace / insert / remove），優先從 session cached_candidates 選取備選場地，必要時再呼叫 AgentLoop，然後以 Replanner 執行局部重建，盡量保留未修改的舊腿資料。

### 已登錄工具清單

| 工具名稱 | 說明 | 可用 intent |
|---|---|---|
| `place_search` | 以條件搜尋台北場地 | GENERATE_ITINERARY, REPLAN, CHAT_GENERAL |
| `place_recommend` | 依評分取得推薦場地 | GENERATE_ITINERARY |
| `place_nearby` | 查詢座標附近場地 | GENERATE_ITINERARY, REPLAN |
| `place_batch` | 以 id 批量取得場地詳情 | GENERATE_ITINERARY, REPLAN |
| `place_categories` | 列出支援的內部分類 | GENERATE_ITINERARY |
| `place_stats` | 取得場地統計數據 | GENERATE_ITINERARY |
| `route_estimate` | 估算兩座標間的移動時間 | GENERATE_ITINERARY, REPLAN |

---

## 5. 測試與穩定性狀態

### 測試覆蓋範圍

測試目前共 **110 個**，全部通過（`pytest 8.2.2 / asyncio mode=auto`）。覆蓋層次如下：

- **單元測試**：`SessionModel`、`Itinerary` schema 驗證（Pydantic model_validator）、`extract_stop_index` 中英文序數解析、`haversine_distance_m` 計算、語言偵測邏輯
- **適配器測試**：`PlaceToolAdapter` 以 `respx` 模擬 HTTP 回應，涵蓋 timeout、500、malformed JSON、empty 等異常路徑；`RouteToolAdapter` 同樣以 mock transport 測試 Google Maps 成功路徑與 haversine fallback
- **邏輯測試**：`IntentClassifier` 的 LLM JSON parsing、slot coercion、missing-field post-processing；`PreferenceExtractor` 的 LLM normalization、district/origin 補強；`AgentLoop` 的 LLM tool planning、deterministic mapping 覆寫、`place_search -> place_recommend` fallback；`ItineraryBuilder` 站點選取與 partial_fallback 標記
- **整合流程測試**：`MessageHandler` 完整流程，包含行程生成、行程修改（replace / remove）、clarification 路徑、tool 失敗降級、並發同 session 請求一致性
- **API 層測試**：以 `TestClient` 測試 chat 和 trace 端點的 HTTP 行為、錯誤格式

### 執行方式（目前需手動設定 PYTHONPATH）

```bash
PYTHONPATH=/path/to/Chat_Agent .venv/bin/pytest tests/ -v
```

---

## 6. 目前已知限制 / 待補強項目

**Session 無持久化。** `InMemorySessionStore` 在程式重啟後清空，多 process 部署下 session 無法共享。目前設計完全假設單 process。

**AgentLoop 仍然不是完整的多輪 agent。** 雖然現在已經有單輪 LLM tool planning，但它仍不是 open-ended、多步驟、自主反思式 agent loop；工具規劃仍受 deterministic validation 和既定 fallback chain 約束。

**ResponseComposer 使用樣板字串，不使用 LLM 生成。** 回覆品質是固定格式的，無法因應複雜對話或回覆使用者非預期的問題。`prompt_builder.py` 中已有偏好摘要等 helper，但最終回答文字仍是 deterministic composer。

**`session_locks` 沒有自動清理機制。** `MessageHandler._session_locks` 字典會隨著 session 數量增長，程式碼中已有 TODO 標記，在 demo 規模下不是 blocker。

**Trace store 是 in-memory 且有上限。** 最多 200 筆，重啟後清空，不適合作長期 debug 資料存取。

**沒有 CI pipeline。** 目前沒有 GitHub Actions 或等效設定，測試執行完全依賴手動。

**測試需手動設定 PYTHONPATH。** `pytest.ini` 未配置 `pythonpath`，裸跑 `pytest` 會全部 import error。此為文件與 CI 設定的缺口，不影響程式碼正確性。

**Google Maps API key 仍是必要欄位。** `Settings` 中 `google_maps_api_key` 是 required field，即使設定 `route_provider=fallback` 也會在啟動時驗證失敗，對測試環境設定略有摩擦。

**README / CurrentState 這類文件容易落後。** 近期架構改動主要集中在 LLM-first classification / preferences、OpenRouter 支援、AgentLoop tool planning 與 replanner LLM fallback，因此文件需要持續跟著 code 更新。

---

## 7. 目前整體完成度判斷

**判斷：Integration-ready，且已可支撐 demo 級實際對話。**

從工程角度看，這個後端的架構設計清晰，模組邊界明確，各層職責分明，有完整的 error handling 和 trace 可觀測性。Pydantic v2 的 model_validator 讓資料約束明確，Itinerary 的 stop/leg 連續性驗證是工程上少見的謹慎。測試覆蓋率廣且真實覆蓋了降級路徑（tool error、empty result、classifier fallback）。

目前的限制在於「功能邊界合理但深度有限」：雖然 intent / preference / replanning / tool planning 已經 LLM 化，但最後的 itinerary 組裝、候選挑選、回覆文案、fallback chain 仍以 deterministic 邏輯為主。這使得系統行為仍然可預期、方便 debug，也適合 demo 和前端整合；但在偏好細節、語意 nuance、候選排序品質上仍有進一步提升空間。

---

## 8. 下一步最合理的方向

根據目前 repo 的實際狀態，以下是最合理的下一步：

**前端整合。** 後端 API 介面已穩定，`ChatMessageResponse` 包含前端需要的所有欄位（itinerary、candidates、routing_status、preferences），現在是接上前端介面的時機。需要確認 CORS 設定和 session_id 管理策略。

**修正測試執行環境。** 在 `pytest.ini` 加入 `pythonpath = .` 或建立 `conftest.py` 設定 sys.path，讓測試可以不需要手動設 `PYTHONPATH` 直接執行。這同時是建立 CI 的前提。

**提升 itinerary 候選品質。** 目前雖然 `cafes -> food + cafe` 的 mapping 已修正，但 itinerary builder 的 stop selection 仍偏 deterministic；如果要讓「咖啡廳」需求更穩定對到真正 café 類型，下一步可以在 candidate ranking 或 itinerary selection 上再加入更明確的 type bias。

**基本 CI 設定。** 以 GitHub Actions 跑 `pytest`，讓每次 PR 都有測試保護，這是從 demo-ready 走向更穩定合作的基本條件。

**文件補充。** README 目前只有 startup 指令，缺少 API 說明、完整的 env 變數說明、測試執行方式，可以基於這份報告進一步補充。
