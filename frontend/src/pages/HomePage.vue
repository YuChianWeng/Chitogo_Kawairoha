<template>
  <div class="chat-shell">
    <header class="chat-header">
      <h1>ChitoGo</h1>
      <span class="subtitle">Taipei travel assistant</span>
    </header>

    <div class="messages" ref="messagesEl">
      <div v-if="messages.length === 0" class="empty-hint">
        Try: "Plan a day trip in 大安區 for food and cafes" or "Recommend museums near Zhongshan"
      </div>

      <div
        v-for="(msg, i) in messages"
        :key="i"
        :class="['message', msg.role]"
      >
        <div class="bubble">{{ msg.text }}</div>

        <div v-if="msg.itinerary" class="itinerary">
          <div class="itinerary-header">
            {{ msg.itinerary.summary }}
            <span v-if="msg.itinerary.total_duration_min" class="duration">
              {{ msg.itinerary.total_duration_min }} min total
            </span>
          </div>
          <ol class="stops">
            <li v-for="stop in msg.itinerary.stops" :key="stop.stop_index" class="stop">
              <span class="stop-name">{{ stop.venue_name }}</span>
              <span v-if="stop.arrival_time" class="stop-time">{{ stop.arrival_time }}</span>
              <span v-if="stop.category" class="stop-category">{{ stop.category }}</span>
              <span v-if="stop.visit_duration_min" class="stop-duration">{{ stop.visit_duration_min }} min</span>
            </li>
          </ol>
        </div>

        <div v-if="msg.candidates && msg.candidates.length" class="candidates">
          <div
            v-for="c in msg.candidates"
            :key="c.place_id"
            class="candidate-card"
          >
            <strong>{{ c.name }}</strong>
            <span v-if="c.district" class="tag">{{ c.district }}</span>
            <span v-if="c.category" class="tag">{{ c.category }}</span>
            <span v-if="c.rating" class="tag">★ {{ c.rating }}</span>
            <p v-if="c.why_recommended" class="why">{{ c.why_recommended }}</p>
          </div>
        </div>

        <div v-if="msg.needsClarification" class="clarification-hint">
          Please provide more details to continue.
        </div>
      </div>

      <div v-if="loading" class="message assistant">
        <div class="bubble thinking">Thinking…</div>
      </div>
    </div>

    <form class="input-row" @submit.prevent="send">
      <input
        v-model="input"
        :disabled="loading"
        placeholder="Ask about Taipei…"
        autocomplete="off"
      />
      <button type="submit" :disabled="loading || !input.trim()">Send</button>
    </form>

    <div v-if="errorText" class="error-bar">{{ errorText }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { sendMessage } from '../services/api'
import type { Itinerary, ChatCandidate } from '../types/itinerary'

interface Message {
  role: 'user' | 'assistant'
  text: string
  itinerary?: Itinerary | null
  candidates?: ChatCandidate[]
  needsClarification?: boolean
}

const messages = ref<Message[]>([])
const input = ref('')
const loading = ref(false)
const errorText = ref('')
const sessionId = ref<string | null>(null)
const messagesEl = ref<HTMLElement | null>(null)

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

async function scrollBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-shell {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  max-width: 720px;
  margin: 0 auto;
  font-family: system-ui, sans-serif;
}

.chat-header {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.chat-header h1 {
  margin: 0;
  font-size: 1.25rem;
}

.subtitle {
  font-size: 0.85rem;
  color: #64748b;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.empty-hint {
  color: #94a3b8;
  font-size: 0.9rem;
  text-align: center;
  margin-top: 2rem;
}

.message {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 85%;
}

.message.user {
  align-self: flex-end;
  align-items: flex-end;
}

.message.assistant {
  align-self: flex-start;
  align-items: flex-start;
}

.bubble {
  padding: 0.6rem 0.9rem;
  border-radius: 12px;
  font-size: 0.95rem;
  line-height: 1.5;
  white-space: pre-wrap;
}

.message.user .bubble {
  background: #2563eb;
  color: white;
  border-bottom-right-radius: 3px;
}

.message.assistant .bubble {
  background: #f1f5f9;
  color: #0f172a;
  border-bottom-left-radius: 3px;
}

.bubble.thinking {
  color: #94a3b8;
}

.itinerary {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  font-size: 0.88rem;
  width: 100%;
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

.stop-time,
.stop-category,
.stop-duration {
  font-size: 0.8rem;
  color: #64748b;
}

.candidates {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  width: 100%;
}

.candidate-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.6rem 0.8rem;
  font-size: 0.88rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
}

.tag {
  background: #e2e8f0;
  border-radius: 4px;
  padding: 0.1rem 0.4rem;
  font-size: 0.78rem;
  color: #475569;
}

.why {
  width: 100%;
  margin: 0.25rem 0 0;
  color: #64748b;
  font-size: 0.82rem;
}

.clarification-hint {
  font-size: 0.8rem;
  color: #f59e0b;
}

.input-row {
  display: flex;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border-top: 1px solid #e2e8f0;
}

.input-row input {
  flex: 1;
  padding: 0.55rem 0.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 0.95rem;
  outline: none;
}

.input-row input:focus {
  border-color: #2563eb;
}

.input-row button {
  padding: 0.55rem 1.1rem;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.95rem;
  cursor: pointer;
}

.input-row button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-bar {
  background: #fee2e2;
  color: #b91c1c;
  font-size: 0.85rem;
  padding: 0.5rem 1.5rem;
  border-top: 1px solid #fca5a5;
}
</style>
