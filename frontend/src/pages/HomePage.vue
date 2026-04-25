<template>
  <div class="app-container">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="logo-container">
        <img src="/images/111_200.svg" alt="Logo" class="logo-icon">
        <h1 class="logo-text">𨑨迌迌<br>Chito-Go</h1>
      </div>
      <nav class="nav-menu">
        <button
          v-for="tab in NAV_TABS"
          :key="tab.key"
          type="button"
          :class="['nav-item', activeTab === tab.key ? 'active' : '']"
          @click="activeTab = tab.key"
        >
          <img v-if="tab.icon" :src="tab.icon" :alt="tab.label">
          <span v-else class="nav-icon-placeholder"></span>
          <span>{{ tab.label }}</span>
        </button>
      </nav>
    </aside>

    <!-- Agent tab: chat + map -->
    <div v-if="activeTab === 'agent'" class="main-content" ref="mainContentEl">
      <!-- Chat Area -->
      <main class="chat-area" :style="{ width: chatWidth + 'px' }">
        <header class="chat-header">
          <h2>𨑨迌迌 Chito-Go</h2>
          <div class="info-bar">
            <div class="info-item">
              <img src="/images/111_361.svg" alt="Weather">
              <span>多雲•降雨機率 30%</span>
            </div>
            <div class="info-item">
              <img src="/images/111_363.svg" alt="Time">
              <span>{{ currentTime }}</span>
            </div>
            <div class="info-item">
              <img src="/images/111_362.svg" alt="Location">
              <span>台北市•信義區</span>
            </div>
          </div>
        </header>

        <div class="chat-content" ref="messagesEl">
          <div v-if="messages.length === 0" class="empty-hint">
            試試看：「幫我規劃大安區一日美食行程」或「信義區附近有什麼隱藏景點？」
          </div>

          <div
            v-for="(msg, i) in messages"
            :key="i"
            :class="['message', msg.role === 'user' ? 'user-message' : 'agent-message']"
          >
            <img v-if="msg.role === 'assistant'" src="/images/111_301.svg" alt="Agent" class="avatar">

            <div class="bubble-wrapper">
              <div v-if="msg.role === 'user'" class="user-bubble">
                {{ msg.text }}
                <div class="message-time">
                  {{ currentTime }}
                  <img src="/images/111_410.svg" alt="Read">
                </div>
              </div>

              <div v-else class="agent-bubble">
                {{ msg.text }}

                <div v-if="msg.needsClarification" class="transport-options">
                  <button
                    v-for="t in transportOptions"
                    :key="t"
                    :class="['transport-btn', selectedTransport === t ? 'active' : '']"
                    @click="selectedTransport = t"
                  >{{ t }}</button>
                </div>

                <div v-if="msg.itinerary" class="itinerary-block">
                  <div class="itinerary-header">
                    {{ msg.itinerary.summary }}
                    <span v-if="msg.itinerary.total_duration_min" class="duration">
                      {{ msg.itinerary.total_duration_min }} 分鐘
                    </span>
                  </div>
                  <ol class="stops">
                    <li v-for="stop in msg.itinerary.stops" :key="stop.stop_index" class="stop">
                      <span class="stop-name">{{ stop.venue_name }}</span>
                      <span v-if="stop.arrival_time" class="stop-meta">{{ stop.arrival_time }}</span>
                      <span v-if="stop.category" class="stop-meta">{{ stop.category }}</span>
                      <span v-if="stop.visit_duration_min" class="stop-meta">{{ stop.visit_duration_min }} 分</span>
                    </li>
                  </ol>
                </div>

                <div v-if="msg.candidates && msg.candidates.length" class="bar-grid">
                  <div v-for="c in msg.candidates" :key="c.place_id" class="bar-card">
                    <img :src="placeImage(c)" class="bar-img" :alt="c.name">
                    <div class="bar-info">
                      <div class="bar-title-row">
                        <h3>{{ c.name }}</h3>
                        <div v-if="c.rating" class="rating">★ {{ c.rating }}</div>
                      </div>
                      <div class="bar-desc">
                        <img src="/images/111_241.svg" alt="Pin">
                        <span>{{ c.district ?? '' }}</span>
                      </div>
                      <div class="bar-tags">
                        <span v-if="c.category" class="tag">{{ c.category }}</span>
                        <span v-if="c.why_recommended" class="tag">{{ c.why_recommended.slice(0, 10) }}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="msg.candidates && msg.candidates.length" class="refresh-btn" @click="refreshCandidates(i)">換一批</div>
              </div>
            </div>
          </div>

          <div v-if="loading" class="message agent-message">
            <img src="/images/111_301.svg" alt="Agent" class="avatar">
            <div class="bubble-wrapper">
              <div class="agent-bubble thinking">思考中…</div>
            </div>
          </div>
        </div>

        <div v-if="errorText" class="error-bar">{{ errorText }}</div>

        <footer class="chat-footer">
          <form class="input-container" @submit.prevent="send">
            <input
              v-model="input"
              :disabled="loading"
              placeholder="想探索台北哪個角落？"
              autocomplete="off"
            >
            <button type="submit" class="send-btn" :disabled="loading || !input.trim()">送出</button>
            <button
              type="button"
              class="mic-btn"
              :class="{ recording: isRecording }"
              @click="toggleRecording"
              :disabled="loading"
            >
            <img src="/images/111_309.svg" alt="Mic" class="mic-icon">
            </button>
          </form>
        </footer>
      </main>

      <!-- Resizable Divider -->
      <div
        class="divider"
        role="separator"
        aria-orientation="vertical"
        :aria-valuenow="chatWidth"
        :aria-valuemin="CHAT_MIN"
        :aria-valuemax="CHAT_MAX"
        tabindex="0"
        @pointerdown.prevent="onDividerPointerDown"
        @keydown="onDividerKeyDown"
      >
        <div class="divider-line"></div>
        <div class="divider-handle">
          <div style="position: relative; width: 32px; height: 32px;">
            <img src="/images/116_56.svg" alt="" style="position:absolute;top:0;left:0;width:100%;height:100%;">
            <img src="/images/116_47.svg" alt="" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:24px;height:24px;">
          </div>
        </div>
      </div>

      <!-- Map -->
      <MapPanel :itinerary="latestItinerary" :candidates="latestCandidates" :loading="loading" />
    </div>

    <!-- Placeholder tabs -->
    <div v-else class="main-content placeholder-content">
      <div class="placeholder-view">
        <h2>{{ NAV_TABS.find(t => t.key === activeTab)?.label }}</h2>
        <p>即將推出</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onBeforeUnmount } from 'vue'
import { sendMessage } from '../services/api'
import type { Itinerary, ChatCandidate } from '../types/itinerary'
import MapPanel from '../components/MapPanel.vue'
import RecordRTC from 'recordrtc'

type TabKey = 'home' | 'attractions' | 'agent' | 'profile' | 'settings'

const NAV_TABS: { key: TabKey; label: string; icon?: string }[] = [
  { key: 'home',        label: '首頁',   icon: '/images/I111_161_1_103_47_149.svg' },
  { key: 'attractions', label: '景點',   icon: '/images/I111_160_1_103_47_158.svg' },
  { key: 'agent',       label: 'Agent',  icon: '/images/I111_160_1_103_47_159.svg' },
  { key: 'profile',     label: '個人資料', icon: '/images/I111_163_1_103_47_152.svg' },
  { key: 'settings',    label: '設定', icon: '/images/I111_163_1_103_47_153.svg' },
]

const CHAT_MIN = 360
const CHAT_MAX = 760
const CHAT_DEFAULT = 520

interface Message {
  role: 'user' | 'assistant'
  text: string
  itinerary?: Itinerary | null
  candidates?: ChatCandidate[]
  needsClarification?: boolean
}

// ── Tab state ──
const activeTab = ref<TabKey>('agent')

// ── Resizable panel state ──
const mainContentEl = ref<HTMLElement | null>(null)
const chatWidth = ref<number>(
  parseInt(localStorage.getItem('chitogo.chatWidth') ?? String(CHAT_DEFAULT)) || CHAT_DEFAULT
)

function clampWidth(w: number): number {
  return Math.min(CHAT_MAX, Math.max(CHAT_MIN, w))
}

function onDividerPointerDown(e: PointerEvent) {
  const container = mainContentEl.value
  if (!container) return

  document.body.classList.add('is-resizing')
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)

  function onMove(ev: PointerEvent) {
    const rect = container.getBoundingClientRect()
    chatWidth.value = clampWidth(ev.clientX - rect.left)
  }

  function onUp() {
    document.body.classList.remove('is-resizing')
    localStorage.setItem('chitogo.chatWidth', String(chatWidth.value))
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }

  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

function onDividerKeyDown(e: KeyboardEvent) {
  const step = 16
  if (e.key === 'ArrowLeft')  { chatWidth.value = clampWidth(chatWidth.value - step); e.preventDefault() }
  if (e.key === 'ArrowRight') { chatWidth.value = clampWidth(chatWidth.value + step); e.preventDefault() }
  if (e.key === 'Home')       { chatWidth.value = CHAT_MIN; e.preventDefault() }
  if (e.key === 'End')        { chatWidth.value = CHAT_MAX; e.preventDefault() }
  if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {
    localStorage.setItem('chitogo.chatWidth', String(chatWidth.value))
  }
}

onBeforeUnmount(() => {
  document.body.classList.remove('is-resizing')
})

// ── Chat state ──
const messages = ref<Message[]>([])
const input = ref('')
const loading = ref(false)
const errorText = ref('')
const sessionId = ref<string | null>(null)
const messagesEl = ref<HTMLElement | null>(null)
const selectedTransport = ref('步行')
const transportOptions = ['機車', '步行', '汽車', '捷運']

const placeholderImages = [
  '/images/562f22286b528749d8c9c64b5dccd5fea7d29c59.png',
  '/images/0d5013bb290214ebf4e634d47476a96e10284f8e.png',
  '/images/8d38edaeb174e78c2f764c80dee5c9d515f5bc93.png',
  '/images/78d32b5423897d4010582bf5bc832bb5aa8feb55.png',
]

function placeImage(c: ChatCandidate): string {
  const idx = Math.abs(c.place_id?.toString().charCodeAt(0) ?? 0) % placeholderImages.length
  return placeholderImages[idx]
}

const currentTime = computed(() => {
  const now = new Date()
  const days = ['日', '一', '二', '三', '四', '五', '六']
  const day = days[now.getDay()]
  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  return `星期${day} ${hh}:${mm}`
})

const latestCandidates = computed<ChatCandidate[]>(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const m = messages.value[i]
    if (m.candidates && m.candidates.length) return m.candidates
  }
  return []
})

const latestItinerary = computed<Itinerary | null>(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const m = messages.value[i]
    if (m.itinerary) return m.itinerary
  }
  return null
})

const isRecording = ref(false)
let mediaRecorder: RecordRTC | null = null

async function toggleRecording() {
  if (isRecording.value) {
    mediaRecorder?.stopRecording(async () => {
      const audioBlob = mediaRecorder!.getBlob()
      await uploadVoice(audioBlob)
      mediaRecorder?.camera?.getTracks().forEach(track => track.stop())
      isRecording.value = false
    })
    return
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaRecorder = new RecordRTC(stream, {
      type: 'audio',
      mimeType: 'audio/wav',
      recorderType: RecordRTC.StereoAudioRecorder,
      desiredSampRate: 16000,
      numberOfAudioChannels: 1
    })
    mediaRecorder.camera = stream
    mediaRecorder.startRecording()
    isRecording.value = true
  } catch (err) {
    console.error("Mic error:", err)
    errorText.value = "Cannot access microphone."
  }
}

async function uploadVoice(blob: Blob) {
  loading.value = true
  errorText.value = ''
  const formData = new FormData()
  formData.append('file', blob, 'recording.wav')

  try {
    const response = await fetch('http://127.0.0.1:8000/api/v1/transcribe', {
      method: 'POST',
      body: formData
    })

    if (!response.ok) {
      const errData = await response.json()
      throw new Error(errData.detail || 'Audio upload fail.')
    }
    
    const data = await response.json()
    if (data.text) {
      input.value = data.text.trim()
    }
  } catch (err: any) {
    console.error(err)
    errorText.value = err.message || "Voice recognition fail."
  } finally {
    loading.value = false
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', text })
  input.value = ''
  errorText.value = ''
  loading.value = true
  await scrollBottom()

  try {
    const response = await sendMessage({
      message: text,
      session_id: sessionId.value ?? undefined,
    })
    sessionId.value = response.session_id
    messages.value.push({
      role: 'assistant',
      text: response.message,
      itinerary: response.itinerary ?? null,
      candidates: response.itinerary ? [] : response.candidates,
      needsClarification: response.needs_clarification,
    })
  } catch (err: unknown) {
    const axiosError = err as { response?: { data?: { error?: string; detail?: string } } }
    const detail = axiosError?.response?.data?.detail ?? axiosError?.response?.data?.error
    errorText.value = detail ?? 'Something went wrong. Is the Chat Agent running on :8100?'
  } finally {
    loading.value = false
    await scrollBottom()
  }
}

function refreshCandidates(_idx: number) {
  // placeholder for re-query
}

async function scrollBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}
</script>

<style scoped>
/* ── Outer shell ── */
.app-container {
  display: flex;
  width: 1440px;
  min-height: 100vh;
  padding: 20px 80px;
  gap: 0;
  margin: 0 auto;
}

/* ── Sidebar ── */
.sidebar {
  width: 193px;
  background: white;
  border-radius: 15px;
  flex-shrink: 0;
  padding: 40px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.logo-container {
  text-align: center;
  margin-bottom: 60px;
}

.logo-icon {
  width: 40px;
  height: 40px;
  margin-bottom: 10px;
}

.logo-text {
  font-size: 16px;
  font-weight: bold;
  color: #000;
  line-height: 1.4;
}

.nav-menu {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.nav-item {
  display: flex;
  align-items: center;
  padding: 12px 20px;
  border: none;
  background: transparent;
  color: #6c7072;
  border-radius: 15px;
  font-size: 16px;
  font-family: inherit;
  gap: 15px;
  cursor: pointer;
  text-align: left;
  width: 100%;
}

.nav-item img {
  width: 24px;
  height: 24px;
}

.nav-icon-placeholder {
  width: 24px;
  height: 24px;
  display: inline-block;
  flex-shrink: 0;
}

.nav-item.active {
  background-color: #4d68bf;
  color: #fff;
  box-shadow: 0 4px 4px rgba(0,0,0,0.1);
}

.nav-item.active img {
  filter: brightness(0) invert(1);
}

/* ── Main content ── */
.main-content {
  display: flex;
  margin-left: 24px;
  height: calc(100vh - 40px);
  flex: 1;
  border-radius: 15px;
  overflow: hidden;
  box-shadow: 0 0 20px rgba(0,0,0,0.05);
  min-width: 0;
}

/* ── Chat area ── */
.chat-area {
  background: white;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}

.chat-header {
  text-align: center;
  padding-top: 20px;
  flex-shrink: 0;
}

.chat-header h2 {
  font-size: 18px;
  margin-bottom: 15px;
  color: #000;
}

.info-bar {
  background-color: #4d68bf;
  color: white;
  display: flex;
  justify-content: space-around;
  align-items: center;
  height: 33px;
  font-size: 12px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 5px;
}

.info-item img {
  width: 16px;
  height: 16px;
}

/* ── Messages ── */
.chat-content {
  flex: 1;
  padding: 20px 30px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.empty-hint {
  color: #94a3b8;
  font-size: 0.9rem;
  text-align: center;
  margin-top: 2rem;
}

.message {
  display: flex;
  gap: 12px;
}

.user-message {
  justify-content: flex-end;
}

.agent-message {
  justify-content: flex-start;
  align-items: flex-start;
}

.avatar {
  width: 31px;
  height: 31px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 4px;
}

.bubble-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 404px;
}

.user-bubble {
  background-color: #4d68bf;
  color: white;
  padding: 15px;
  border-radius: 15px;
  font-size: 14px;
  line-height: 1.5;
  max-width: 308px;
}

.message-time {
  text-align: right;
  font-size: 10px;
  color: rgba(255,255,255,0.7);
  margin-top: 5px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 4px;
}

.message-time img {
  width: 12px;
  height: 12px;
}

.agent-bubble {
  color: #252525;
  font-size: 14px;
  line-height: 1.6;
}

.agent-bubble.thinking {
  color: #94a3b8;
}

/* ── Transport buttons ── */
.transport-options {
  display: flex;
  gap: 10px;
  margin-top: 15px;
  flex-wrap: wrap;
}

.transport-btn {
  padding: 5px 15px;
  border: 1px solid #5c76ca;
  background: transparent;
  color: #5c76ca;
  border-radius: 10px;
  cursor: pointer;
  font-size: 14px;
  font-family: inherit;
}

.transport-btn.active {
  background-color: #5c76ca;
  color: white;
}

/* ── Itinerary ── */
.itinerary-block {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  font-size: 0.88rem;
  margin-top: 12px;
}

.itinerary-header {
  font-weight: 600;
  margin-bottom: 0.5rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.duration {
  font-weight: normal;
  color: #64748b;
  font-size: 0.82rem;
}

.stops {
  margin: 0;
  padding-left: 1.2rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.stop {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
  flex-wrap: wrap;
}

.stop-name {
  font-weight: 500;
}

.stop-meta {
  font-size: 0.8rem;
  color: #64748b;
}

/* ── Bar cards ── */
.bar-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
  margin-top: 20px;
}

.bar-card {
  border: 1px solid #b4e1a5;
  border-radius: 15px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.bar-img {
  width: 100%;
  height: 119px;
  object-fit: cover;
  border-radius: 13px 13px 0 0;
}

.bar-info {
  padding: 12px;
}

.bar-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 5px;
}

.bar-title-row h3 {
  font-size: 14px;
  color: #121212;
}

.rating {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: #6f7789;
}

.bar-desc {
  font-size: 12px;
  color: #6f7789;
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 8px;
}

.bar-desc img {
  width: 12px;
  height: 12px;
}

.bar-tags {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.tag {
  font-size: 10px;
  color: #6f7789;
  border: 0.5px solid #6f7789;
  border-radius: 15px;
  padding: 2px 8px;
}

.refresh-btn {
  text-align: center;
  color: #5c76ca;
  font-size: 14px;
  margin-top: 15px;
  cursor: pointer;
  user-select: none;
}

.refresh-btn:hover {
  text-decoration: underline;
}

/* ── Input footer ── */
.chat-footer {
  background-color: #4d68bf;
  height: 88px;
  display: flex;
  justify-content: center;
  align-items: center;
  flex-shrink: 0;
}

.input-container {
  width: 447px;
  height: 53px;
  background: white;
  border-radius: 15px;
  display: flex;
  align-items: center;
  padding: 0 15px;
  gap: 8px;
}

.input-container input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  color: #333;
  font-family: inherit;
}

.input-container input::placeholder {
  color: #adadad;
}

.send-btn {
  background: #4d68bf;
  color: white;
  border: none;
  border-radius: 10px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  flex-shrink: 0;
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.mic-btn {
  background: transparent;
  border: none;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.2s ease;
}
.mic-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.mic-icon {
  width: 30px;
  height: 30px;
  display: block;
}

.mic-btn.recording {
  background-color: #fee2e2;
  box-shadow: 0 0 0 4px #fee2e2;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0% { transform: scale(1); }
  50% { transform: scale(1.1); }
  100% { transform: scale(1); }
}

/* ── Error ── */
.error-bar {
  background: #fee2e2;
  color: #b91c1c;
  font-size: 0.85rem;
  padding: 0.5rem 1.5rem;
  border-top: 1px solid #fca5a5;
  flex-shrink: 0;
}

/* ── Divider ── */
.divider {
  width: 24px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  flex-shrink: 0;
  cursor: col-resize;
  position: relative;
  z-index: 10;
  background: transparent;
  border: none;
  padding: 0;
  outline-offset: -2px;
}

.divider:focus-visible {
  outline: 2px solid #4d68bf;
}

.divider-line {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 3px;
  height: 100%;
  background-color: #4d68bf;
  pointer-events: none;
}

.divider-handle {
  width: 32px;
  height: 32px;
  display: flex;
  justify-content: center;
  align-items: center;
  position: relative;
  z-index: 1;
}

/* ── Placeholder tabs ── */
.placeholder-content {
  justify-content: center;
  align-items: center;
  background: white;
}

.placeholder-view {
  text-align: center;
  color: #94a3b8;
}

.placeholder-view h2 {
  font-size: 24px;
  color: #4d68bf;
  margin-bottom: 12px;
}

.placeholder-view p {
  font-size: 16px;
}
</style>

<style>
/* Global: prevent text selection while dragging the divider */
body.is-resizing {
  user-select: none;
  cursor: col-resize;
}
</style>
