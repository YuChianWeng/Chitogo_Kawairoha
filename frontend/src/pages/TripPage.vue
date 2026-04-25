<template>
  <div class="trip-container">
    <div v-if="showGoHomeBanner" class="go-home-banner">
      <p>{{ goHomeMessage }}</p>
      <div class="banner-actions">
        <button class="banner-btn continue" @click="dismissBanner">繼續玩</button>
        <button class="banner-btn gohome" @click="triggerSummary">回家去</button>
      </div>
    </div>

    <div v-if="locationDenied" class="location-fallback">
      <p>需要位置資訊才能推薦附近景點。請選擇你所在的區域：</p>
      <select v-model="selectedDistrict" class="district-select" @change="applyDistrictFallback">
        <option value="">選擇地區</option>
        <option v-for="d in DISTRICT_CENTROIDS" :key="d.name" :value="d.name">{{ d.name }}</option>
      </select>
    </div>

    <div class="trip-content">
      <template v-if="tripPhase === 'TRANSPORT_PROMPT'">
        <div class="phase-header">
          <div>
            <h2>先確認這一輪的交通</h2>
            <p class="phase-subtitle">每次選景點前都可以調整交通與每段可接受時間。</p>
          </div>
          <p class="gene-badge">{{ userGene }}</p>
        </div>

        <div class="transport-card">
          <div class="transport-grid">
            <label
              v-for="mode in transportOptions"
              :key="mode.value"
              class="transport-option"
              :class="{ active: transportModes.includes(mode.value) }"
            >
              <input
                v-model="transportModes"
                type="checkbox"
                :value="mode.value"
              />
              <span>{{ mode.label }}</span>
            </label>
          </div>

          <div class="slider-group">
            <div class="slider-header">
              <span>每段最長時間</span>
              <strong>{{ maxMinutesPerLeg }} 分鐘</strong>
            </div>
            <input
              v-model.number="maxMinutesPerLeg"
              type="range"
              min="5"
              max="120"
              step="5"
              class="slider"
            />
          </div>

          <p class="transport-hint">這一輪會依你現在選的交通方式重新篩選候選景點。</p>
          <div v-if="candidatesError" class="inline-error">{{ candidatesError }}</div>

          <button class="primary-btn" :disabled="loadingCandidates" @click="submitTransport">
            {{ loadingCandidates ? '搜尋中…' : '開始找景點' }}
          </button>
        </div>
      </template>

      <template v-else-if="tripPhase === 'SELECTING'">
        <div class="phase-header">
          <div>
            <h2>附近推薦</h2>
            <p class="transport-summary">
              {{ transportSummary }}
            </p>
          </div>
          <div class="phase-actions">
            <p class="gene-badge">{{ userGene }}</p>
            <button class="secondary-btn" @click="reopenTransportPrompt">改交通</button>
          </div>
        </div>

        <div v-if="loadingCandidates" class="loading-state">
          <p>搜尋附近景點中…</p>
        </div>
        <div v-else-if="candidatesResult">
          <div v-if="candidatesError" class="inline-error">{{ candidatesError }}</div>
          <CandidateGrid
            :candidates="candidatesResult.candidates"
            :partial="candidatesResult.partial"
            :fallback-reason="candidatesResult.fallback_reason"
            @select="onVenueSelected"
            @demand="showDemandModal = true"
          />
        </div>
        <div v-else class="error-state">
          <p>{{ candidatesError || '還沒有找到候選景點。' }}</p>
          <button class="retry-btn" @click="retryCurrentRound">重試</button>
        </div>
      </template>

      <template v-else-if="tripPhase === 'NAVIGATING' && selectResult">
        <NavigationPanel
          :venue="selectResult.venue"
          :navigation="selectResult.navigation"
          :encouragement="selectResult.encouragement_message"
          @arrived="onArrived"
        />
      </template>

      <template v-else-if="tripPhase === 'RATING' && selectResult">
        <RatingCard :venue="selectResult.venue" @rated="onRated" />
      </template>
    </div>

    <button
      v-if="tripPhase !== 'ENDED'"
      class="go-home"
      @click="showGoHomeConfirm = true"
    >
      我想回家
    </button>

    <dialog ref="goHomeDialog" class="confirm-dialog">
      <p>確定要結束旅程嗎？</p>
      <div class="dialog-actions">
        <button class="dialog-btn cancel" @click="closeGoHomeDialog">取消</button>
        <button class="dialog-btn confirm" @click="triggerSummary" :disabled="summaryLoading">
          {{ summaryLoading ? '結束中…' : '確定' }}
        </button>
      </div>
    </dialog>

    <DemandModal
      v-if="showDemandModal"
      :lat="currentLat"
      :lng="currentLng"
      @close="showDemandModal = false"
      @select="onDemandSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import CandidateGrid from '../components/CandidateGrid.vue'
import DemandModal from '../components/DemandModal.vue'
import NavigationPanel from '../components/NavigationPanel.vue'
import RatingCard from '../components/RatingCard.vue'
import { checkGoHome, getCandidates, getSummary, selectVenue } from '../services/api'
import type { CandidateCard, CandidateTransportInput, CandidatesResult, RateResult, SelectResult, TransportMode } from '../types/trip'

const router = useRouter()

type TripPhase = 'TRANSPORT_PROMPT' | 'SELECTING' | 'NAVIGATING' | 'RATING' | 'ENDED'

const currentLat = ref(25.0478)
const currentLng = ref(121.5170)
const locationDenied = ref(false)
const selectedDistrict = ref('')

const DISTRICT_CENTROIDS = [
  { name: '大安區', lat: 25.0264, lng: 121.5432 },
  { name: '信義區', lat: 25.0336, lng: 121.5645 },
  { name: '中山區', lat: 25.0697, lng: 121.5326 },
  { name: '松山區', lat: 25.0578, lng: 121.5770 },
  { name: '中正區', lat: 25.0329, lng: 121.5187 },
  { name: '萬華區', lat: 25.0349, lng: 121.4997 },
  { name: '士林區', lat: 25.0936, lng: 121.5300 },
  { name: '北投區', lat: 25.1322, lng: 121.4982 },
  { name: '內湖區', lat: 25.0814, lng: 121.5872 },
  { name: '南港區', lat: 25.0551, lng: 121.6059 },
  { name: '文山區', lat: 24.9982, lng: 121.5679 },
  { name: '大同區', lat: 25.0633, lng: 121.5131 },
]

const transportOptions: Array<{ value: TransportMode; label: string }> = [
  { value: 'walk', label: '步行' },
  { value: 'transit', label: '大眾運輸' },
  { value: 'drive', label: '開車' },
]

const tripPhase = ref<TripPhase>('TRANSPORT_PROMPT')
const candidatesResult = ref<CandidatesResult | null>(null)
const selectResult = ref<SelectResult | null>(null)
const loadingCandidates = ref(false)
const candidatesError = ref<string | null>(null)
const summaryLoading = ref(false)
const showDemandModal = ref(false)
const showGoHomeConfirm = ref(false)
const goHomeDialog = ref<HTMLDialogElement | null>(null)

const transportModes = ref<TransportMode[]>(['transit'])
const maxMinutesPerLeg = ref(30)
const lastRequestedTransport = ref<CandidateTransportInput | null>(null)

const showGoHomeBanner = ref(false)
const goHomeMessage = ref('')
let suppressUntil = 0
let goHomeInterval: ReturnType<typeof setInterval> | null = null
let locationInterval: ReturnType<typeof setInterval> | null = null

const userGene = localStorage.getItem('chitogo_gene') || ''

const transportSummary = computed(() => {
  const currentTransport = lastRequestedTransport.value
  if (!currentTransport) return '尚未選擇交通'
  const labels = currentTransport.modes.map(mode => transportLabel(mode)).join(' / ')
  return `${labels} · 每段 ${currentTransport.max_minutes_per_leg} 分鐘內`
})

onMounted(() => {
  requestLocation()
  startGoHomePolling()
})

onUnmounted(() => {
  if (goHomeInterval) clearInterval(goHomeInterval)
  if (locationInterval) clearInterval(locationInterval)
})

watch(showGoHomeConfirm, value => {
  if (value && goHomeDialog.value) {
    goHomeDialog.value.showModal()
  } else if (!value && goHomeDialog.value) {
    goHomeDialog.value.close()
  }
})

function transportLabel(mode: TransportMode) {
  return transportOptions.find(option => option.value === mode)?.label || mode
}

function applyDistrictFallback() {
  const centroid = DISTRICT_CENTROIDS.find(d => d.name === selectedDistrict.value)
  if (!centroid) return

  currentLat.value = centroid.lat
  currentLng.value = centroid.lng

  if (tripPhase.value === 'SELECTING' && lastRequestedTransport.value) {
    void loadCandidates(lastRequestedTransport.value)
  }
}

function requestLocation() {
  if (!navigator.geolocation) {
    locationDenied.value = true
    return
  }

  navigator.geolocation.getCurrentPosition(
    pos => {
      currentLat.value = pos.coords.latitude
      currentLng.value = pos.coords.longitude
      locationInterval = setInterval(() => {
        navigator.geolocation.getCurrentPosition(
          latest => {
            currentLat.value = latest.coords.latitude
            currentLng.value = latest.coords.longitude
          },
          () => {}
        )
      }, 30000)
    },
    () => {
      locationDenied.value = true
    }
  )
}

function buildTransportInput(): CandidateTransportInput {
  return {
    modes: [...transportModes.value],
    max_minutes_per_leg: maxMinutesPerLeg.value,
  }
}

async function submitTransport() {
  if (!transportModes.value.length) {
    candidatesError.value = '請至少選擇一種交通方式'
    return
  }

  await loadCandidates(buildTransportInput())
}

async function loadCandidates(transport?: CandidateTransportInput) {
  const sessionId = localStorage.getItem('chitogo_session_id')
  const activeTransport = transport || lastRequestedTransport.value
  if (!sessionId || !activeTransport) return

  loadingCandidates.value = true
  candidatesError.value = null
  candidatesResult.value = null

  try {
    candidatesResult.value = await getCandidates(
      sessionId,
      currentLat.value,
      currentLng.value,
      activeTransport
    )
    lastRequestedTransport.value = {
      modes: [...activeTransport.modes],
      max_minutes_per_leg: activeTransport.max_minutes_per_leg,
    }
    tripPhase.value = 'SELECTING'
  } catch (err: unknown) {
    const error = err as { response?: { data?: { detail?: string } } }
    candidatesError.value = error?.response?.data?.detail ?? '無法載入推薦，請重試。'
    tripPhase.value = 'TRANSPORT_PROMPT'
  } finally {
    loadingCandidates.value = false
  }
}

async function retryCurrentRound() {
  if (lastRequestedTransport.value) {
    await loadCandidates(lastRequestedTransport.value)
    return
  }
  tripPhase.value = 'TRANSPORT_PROMPT'
}

function reopenTransportPrompt() {
  candidatesError.value = null
  tripPhase.value = 'TRANSPORT_PROMPT'
}

async function onVenueSelected(venueId: string | number) {
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (!sessionId) return

  try {
    candidatesError.value = null
    selectResult.value = await selectVenue(sessionId, venueId, currentLat.value, currentLng.value)
    tripPhase.value = 'NAVIGATING'
  } catch (err: unknown) {
    const error = err as { response?: { data?: { detail?: string } } }
    candidatesError.value = error?.response?.data?.detail ?? '選擇失敗，請重試。'
  }
}

function onArrived() {
  tripPhase.value = 'RATING'
}

async function onRated(_result: RateResult) {
  selectResult.value = null
  candidatesResult.value = null
  candidatesError.value = null
  tripPhase.value = 'TRANSPORT_PROMPT'
}

async function onDemandSelect(card: CandidateCard) {
  showDemandModal.value = false
  await onVenueSelected(card.venue_id)
}

function closeGoHomeDialog() {
  showGoHomeConfirm.value = false
}

async function triggerSummary() {
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (!sessionId) return

  summaryLoading.value = true
  try {
    await getSummary(sessionId)
    tripPhase.value = 'ENDED'
    router.push('/summary')
  } catch {
    summaryLoading.value = false
  }
}

function startGoHomePolling() {
  goHomeInterval = setInterval(async () => {
    if (tripPhase.value === 'ENDED') return
    if (Date.now() < suppressUntil) return

    const sessionId = localStorage.getItem('chitogo_session_id')
    if (!sessionId) return

    try {
      const status = await checkGoHome(sessionId, currentLat.value, currentLng.value)
      if (status.remind) {
        goHomeMessage.value = status.message || '該回家啦！'
        showGoHomeBanner.value = true
      }
    } catch {
      // Ignore polling errors during the trip loop.
    }
  }, 60000)
}

function dismissBanner() {
  showGoHomeBanner.value = false
  suppressUntil = Date.now() + 600_000
}
</script>

<style scoped>
.trip-container {
  min-height: 100vh;
  background: #f0f4ff;
  display: flex;
  flex-direction: column;
  position: relative;
}

.go-home-banner {
  background: #4d68bf;
  color: white;
  padding: 14px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  position: sticky;
  top: 0;
  z-index: 50;
}

.go-home-banner p {
  font-size: 14px;
  flex: 1;
}

.banner-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.banner-btn {
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  border: none;
}

.banner-btn.continue {
  background: rgba(255, 255, 255, 0.2);
  color: white;
}

.banner-btn.gohome {
  background: white;
  color: #4d68bf;
}

.location-fallback {
  background: #fef9c3;
  color: #92400e;
  padding: 12px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  flex-wrap: wrap;
}

.district-select {
  padding: 6px 10px;
  border: 1px solid #d97706;
  border-radius: 8px;
  font-family: inherit;
  font-size: 13px;
}

.trip-content {
  flex: 1;
  padding: 20px 20px 100px;
  max-width: 600px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

.phase-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.phase-header h2 {
  font-size: 22px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 4px;
}

.phase-subtitle {
  font-size: 14px;
  color: #64748b;
}

.phase-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.gene-badge {
  background: #4d68bf;
  color: white;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}

.transport-card {
  background: white;
  border-radius: 18px;
  padding: 24px;
  box-shadow: 0 12px 32px rgba(77, 104, 191, 0.12);
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.transport-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.transport-option {
  border: 1.5px solid #dbe4ff;
  border-radius: 14px;
  padding: 14px 12px;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  color: #334155;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.transport-option input {
  margin: 0;
}

.transport-option.active {
  border-color: #4d68bf;
  background: #eef2ff;
  color: #31468f;
}

.slider-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.slider-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #334155;
}

.slider {
  width: 100%;
}

.transport-hint,
.transport-summary {
  font-size: 14px;
  color: #64748b;
}

.primary-btn,
.secondary-btn,
.retry-btn {
  border: none;
  border-radius: 12px;
  font-family: inherit;
  cursor: pointer;
}

.primary-btn {
  width: 100%;
  padding: 14px 18px;
  background: #4d68bf;
  color: white;
  font-size: 15px;
  font-weight: 600;
}

.primary-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.secondary-btn {
  padding: 9px 14px;
  background: white;
  color: #4d68bf;
  border: 1.5px solid #c7d2fe;
  font-size: 13px;
  font-weight: 600;
}

.loading-state,
.error-state {
  text-align: center;
  padding: 40px 20px;
  color: #64748b;
}

.inline-error {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
}

.retry-btn {
  margin-top: 12px;
  padding: 10px 24px;
  background: #4d68bf;
  color: white;
  font-size: 14px;
}

.go-home {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  padding: 14px 32px;
  background: white;
  color: #ef4444;
  border: 2px solid #ef4444;
  border-radius: 30px;
  font-size: 15px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  z-index: 40;
  transition: all 0.2s;
}

.go-home:hover {
  background: #ef4444;
  color: white;
}

.confirm-dialog {
  border: none;
  border-radius: 16px;
  padding: 28px 24px;
  max-width: 320px;
  width: 90%;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.2);
  font-family: inherit;
}

.confirm-dialog::backdrop {
  background: rgba(0, 0, 0, 0.4);
}

.confirm-dialog p {
  font-size: 17px;
  color: #1e293b;
  text-align: center;
  margin-bottom: 20px;
}

.dialog-actions {
  display: flex;
  gap: 10px;
}

.dialog-btn {
  flex: 1;
  padding: 12px;
  border-radius: 10px;
  font-size: 15px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  border: none;
}

.dialog-btn.cancel {
  background: #f1f5f9;
  color: #475569;
}

.dialog-btn.confirm {
  background: #ef4444;
  color: white;
}

.dialog-btn.confirm:disabled {
  background: #fca5a5;
  cursor: not-allowed;
}

@media (max-width: 640px) {
  .phase-header {
    flex-direction: column;
  }

  .phase-actions {
    width: 100%;
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
  }

  .transport-grid {
    grid-template-columns: 1fr;
  }
}
</style>
