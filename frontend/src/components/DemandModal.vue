<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <button class="close-btn" type="button" @click="$emit('close')">✕</button>
      <p class="modal-kicker">換個條件再推薦</p>
      <h3 class="modal-title">直接用一句話告訴我你想找什麼</h3>

      <div v-if="!searched || results.length === 0">
        <textarea
          v-model="inputText"
          class="demand-input"
          placeholder="例如：我想找安靜一點、適合散步拍照的地方"
          rows="3"
        ></textarea>
        <p class="input-hint">留白也可以，我會先給你同一輪原本的推薦景點。</p>
        <button class="search-btn" type="button" :disabled="loading" @click="doSearch">
          {{ loading ? '整理中…' : '幫我重新推薦' }}
        </button>
        <div v-if="errorText" class="error">{{ errorText }}</div>
        <div v-if="searched && results.length === 0 && !loading && !errorText" class="no-results">
          我附近找不到特別接近的地點，換個描述試試看。
        </div>
      </div>

      <div v-else>
        <p class="result-intro">
          {{ showingOriginalCandidates ? '這是你這一輪原本的推薦景點。' : '我幫你整理了幾個比較接近你剛剛描述的地方。' }}
        </p>
        <p v-if="fallbackReason" class="fallback-note">{{ fallbackReason }}</p>
        <div class="results">
          <div
            v-for="card in results"
            :key="card.venue_id"
            class="result-card"
            @click="$emit('select', card)"
          >
            <div class="result-header">
              <span class="category-badge" :class="card.category">
                {{ card.category === 'restaurant' ? '美食' : '景點' }}
              </span>
              <span class="distance">{{ card.distance_min }} 分鐘</span>
            </div>
            <h4 class="result-name">{{ card.name }}</h4>
            <p class="result-why">{{ card.why_recommended }}</p>
          </div>
        </div>
        <button class="search-btn outline" type="button" @click="results = []; inputText = ''; searched = false">重新輸入條件</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { submitDemand } from '../services/api'
import type { CandidateCard } from '../types/trip'

const props = defineProps<{
  lat: number
  lng: number
  currentCandidates: CandidateCard[]
}>()

const emit = defineEmits<{
  close: []
  select: [card: CandidateCard]
}>()

const inputText = ref('')
const loading = ref(false)
const errorText = ref('')
const results = ref<CandidateCard[]>([])
const fallbackReason = ref<string | null>(null)
const searched = ref(false)
const reusedCurrentCandidates = ref(false)

const showingOriginalCandidates = computed(() => (
  reusedCurrentCandidates.value && inputText.value.trim().length === 0
))

async function doSearch() {
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (!sessionId) return

  if (!inputText.value.trim()) {
    fallbackReason.value = null
    errorText.value = ''
    results.value = [...props.currentCandidates]
    reusedCurrentCandidates.value = true
    searched.value = true
    return
  }

  loading.value = true
  errorText.value = ''
  searched.value = false
  reusedCurrentCandidates.value = false
  try {
    const result = await submitDemand(sessionId, inputText.value, props.lat, props.lng)
    results.value = result.alternatives
    fallbackReason.value = result.fallback_reason
    searched.value = true
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    errorText.value = e?.response?.data?.detail ?? '搜尋失敗，請重試。'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  justify-content: center;
  align-items: flex-end;
  z-index: 100;
  padding: 0;
}

.modal {
  background: white;
  border-radius: 20px 20px 0 0;
  padding: 28px 24px 40px;
  width: 100%;
  max-width: 520px;
  position: relative;
  max-height: 85vh;
  overflow-y: auto;
}

.close-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #94a3b8;
  line-height: 1;
}

.modal-title {
  font-size: 22px;
  line-height: 1.35;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 16px;
}

.modal-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 600;
  color: #2563eb;
  margin-bottom: 10px;
}

.demand-input {
  width: 100%;
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 15px;
  font-family: inherit;
  resize: none;
  box-sizing: border-box;
  margin-bottom: 12px;
}

.demand-input:focus {
  outline: none;
  border-color: #4d68bf;
}

.input-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
}

.search-btn {
  width: 100%;
  padding: 13px;
  background: #4d68bf;
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 15px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
}

.search-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.search-btn.outline {
  background: white;
  color: #4d68bf;
  border: 1.5px solid #4d68bf;
  margin-top: 12px;
}

.error {
  color: #ef4444;
  font-size: 13px;
  margin-top: 8px;
  text-align: center;
}

.result-intro {
  font-size: 14px;
  color: #475569;
  line-height: 1.6;
  margin-bottom: 12px;
}

.no-results {
  color: #64748b;
  font-size: 13px;
  margin-top: 8px;
  text-align: center;
  padding: 8px;
  background: #f8fafc;
  border-radius: 8px;
}

.fallback-note {
  font-size: 13px;
  color: #92400e;
  background: #fef9c3;
  padding: 8px 12px;
  border-radius: 8px;
  margin-bottom: 12px;
}

.results {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 4px;
}

.result-card {
  border: 1.5px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.result-card:hover {
  border-color: #4d68bf;
  background: #f0f4ff;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.category-badge {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  font-weight: 600;
}

.category-badge.restaurant {
  background: #fef3c7;
  color: #d97706;
}

.category-badge.attraction {
  background: #e0f2fe;
  color: #0369a1;
}

.distance {
  font-size: 12px;
  color: #64748b;
}

.result-name {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 4px;
}

.result-why {
  font-size: 13px;
  color: #475569;
}
</style>
