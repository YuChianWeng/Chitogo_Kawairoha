<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <button class="close-btn" type="button" @click="$emit('close')">✕</button>
      <p class="modal-kicker">{{ locale.demand.kicker }}</p>
      <h3 class="modal-title">{{ locale.demand.title }}</h3>

      <div v-if="!searched || results.length === 0">
        <textarea
          v-model="inputText"
          class="demand-input"
          :placeholder="locale.demand.placeholder"
          rows="3"
        ></textarea>
        <p class="input-hint">{{ locale.demand.inputHint }}</p>
        <button class="search-btn" type="button" :disabled="loading" @click="doSearch">
          {{ loading ? locale.demand.loading : locale.demand.submit }}
        </button>
        <div v-if="errorText" class="error">{{ errorText }}</div>
        <div v-if="searched && results.length === 0 && !loading && !errorText" class="no-results">
          {{ locale.demand.noResults }}
        </div>
      </div>

      <div v-else>
        <p class="result-intro">
          {{ showingOriginalCandidates ? locale.demand.showingOriginal : locale.demand.showingNew }}
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
                {{ locale.trip.categories[card.category as 'restaurant' | 'attraction'] ?? card.category }}
              </span>
              <span class="distance">{{ locale.common.minutes(card.distance_min) }}</span>
            </div>
            <h4 class="result-name">{{ lang === 'en' && card.name_en ? card.name_en : card.name }}</h4>
            <p class="result-why">{{ card.why_recommended }}</p>
          </div>
        </div>

        <div v-if="rainFiltered.length > 0" class="rain-section">
          <div class="rain-section-header">
            <span>🌧️</span>
            <span class="rain-section-title">{{ locale.demand.rainDeferredNote }}</span>
          </div>
          <div class="results">
            <div
              v-for="card in rainFiltered"
              :key="card.venue_id"
              class="result-card rain-card"
            >
              <div class="result-header">
                <span class="category-badge" :class="card.category">
                  {{ locale.trip.categories[card.category as 'restaurant' | 'attraction'] ?? card.category }}
                </span>
                <span class="rain-badge">{{ locale.trip.rain.badge }}</span>
              </div>
              <h4 class="result-name rain-name">{{ lang === 'en' && card.name_en ? card.name_en : card.name }}</h4>
              <p class="rain-note-text">{{ card.rain_note }}</p>
            </div>
          </div>
        </div>

        <button class="search-btn outline" type="button" @click="results = []; rainFiltered = []; inputText = ''; searched = false">{{ locale.trip.selecting.retry }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { submitDemand } from '../services/api'
import { useLocale } from '../composables/useLocale'
import type { CandidateCard } from '../types/trip'

const { lang, locale } = useLocale()

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
const rainFiltered = ref<CandidateCard[]>([])
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
    rainFiltered.value = result.rain_filtered ?? []
    fallbackReason.value = result.fallback_reason
    searched.value = true
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    errorText.value = e?.response?.data?.detail ?? locale.value.demand.error
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

.rain-section {
  margin-top: 16px;
  border-top: 1.5px dashed #bfdbfe;
  padding-top: 14px;
}

.rain-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 12px;
}

.rain-section-title {
  font-weight: 600;
  color: #3b82f6;
}

.rain-card {
  opacity: 0.6;
  cursor: default;
  background: linear-gradient(180deg, #f0f9ff 0%, #e0f2fe 100%);
  border-color: #bfdbfe;
  pointer-events: none;
}

.rain-badge {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 5px;
  background: #dbeafe;
  color: #1d4ed8;
  font-weight: 600;
}

.rain-name {
  color: #475569;
}

.rain-note-text {
  font-size: 11px;
  color: #2563eb;
  line-height: 1.4;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid #bfdbfe;
}
</style>
