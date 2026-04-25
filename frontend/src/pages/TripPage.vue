<template>
  <div class="trip-container">

    <!-- Go-home reminder banner (T033) -->
    <div v-if="showGoHomeBanner" class="go-home-banner">
      <p>{{ goHomeMessage }}</p>
      <div class="banner-actions">
        <button class="banner-btn continue" @click="dismissBanner">繼續玩</button>
        <button class="banner-btn gohome" @click="triggerSummary">回家去</button>
      </div>
    </div>

    <!-- Geolocation fallback (T034) -->
    <div v-if="locationDenied" class="location-fallback">
      <p>需要位置資訊才能推薦附近景點。請選擇你所在的區域：</p>
      <select v-model="selectedDistrict" class="district-select" @change="applyDistrictFallback">
        <option value="">選擇地區</option>
        <option v-for="d in DISTRICT_CENTROIDS" :key="d.name" :value="d.name">{{ d.name }}</option>
      </select>
    </div>

    <!-- Main content -->
    <div class="trip-content">

      <!-- SELECTING: Candidate grid -->
      <template v-if="tripPhase === 'SELECTING'">
        <div class="phase-header">
          <h2>附近推薦</h2>
          <p class="gene-badge">{{ userGene }}</p>
        </div>
        <div v-if="loadingCandidates" class="loading-state">
          <p>搜尋附近景點中…</p>
        </div>
        <CandidateGrid
          v-else-if="candidatesResult"
          :candidates="candidatesResult.candidates"
          :partial="candidatesResult.partial"
          :fallback-reason="candidatesResult.fallback_reason"
          @select="onVenueSelected"
          @demand="showDemandModal = true"
        />
        <div v-else-if="candidatesError" class="error-state">
          <p>{{ candidatesError }}</p>
          <button class="retry-btn" @click="loadCandidates">重試</button>
        </div>
      </template>

      <!-- NAVIGATING: Navigation panel -->
      <template v-else-if="tripPhase === 'NAVIGATING' && selectResult">
        <NavigationPanel
          :venue="selectResult.venue"
          :navigation="selectResult.navigation"
          :encouragement="selectResult.encouragement_message"
          @arrived="onArrived"
        />
      </template>

      <!-- RATING: Rating card -->
      <template v-else-if="tripPhase === 'RATING' && selectResult">
        <RatingCard
          :venue="selectResult.venue"
          @rated="onRated"
        />
      </template>

    </div>

    <!-- Fixed go-home button -->
    <button
      v-if="tripPhase !== 'ENDED'"
      class="go-home"
      @click="showGoHomeConfirm = true"
    >
      我想回家
    </button>

    <!-- Go-home confirmation dialog (T030) -->
    <dialog ref="goHomeDialog" class="confirm-dialog">
      <p>確定要結束旅程嗎？</p>
      <div class="dialog-actions">
        <button class="dialog-btn cancel" @click="closeGoHomeDialog">取消</button>
        <button class="dialog-btn confirm" @click="triggerSummary" :disabled="summaryLoading">
          {{ summaryLoading ? '結束中…' : '確定' }}
        </button>
      </div>
    </dialog>

    <!-- Demand modal (T023) -->
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
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import CandidateGrid from '../components/CandidateGrid.vue'
import NavigationPanel from '../components/NavigationPanel.vue'
import RatingCard from '../components/RatingCard.vue'
import DemandModal from '../components/DemandModal.vue'
import { getCandidates, selectVenue, checkGoHome, getSummary } from '../services/api'
import type { CandidatesResult, SelectResult, RateResult, CandidateCard } from '../types/trip'
import { useMapState } from '../composables/useMapState'

const router = useRouter()
const { setSpotCandidates, clearSpotCandidates } = useMapState()

type TripPhase = 'SELECTING' | 'NAVIGATING' | 'RATING' | 'ENDED'

// Location
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

function applyDistrictFallback() {
  const centroid = DISTRICT_CENTROIDS.find(d => d.name === selectedDistrict.value)
  if (centroid) {
    currentLat.value = centroid.lat
    currentLng.value = centroid.lng
    if (tripPhase.value === 'SELECTING') {
      loadCandidates()
    }
  }
}

// Trip state
const tripPhase = ref<TripPhase>('SELECTING')
const candidatesResult = ref<CandidatesResult | null>(null)
const selectResult = ref<SelectResult | null>(null)
const loadingCandidates = ref(false)
const candidatesError = ref<string | null>(null)
const summaryLoading = ref(false)
const showDemandModal = ref(false)
const showGoHomeConfirm = ref(false)
const goHomeDialog = ref<HTMLDialogElement | null>(null)

// Go-home banner
const showGoHomeBanner = ref(false)
const goHomeMessage = ref('')
let suppressUntil = 0
let goHomeInterval: ReturnType<typeof setInterval> | null = null
let locationInterval: ReturnType<typeof setInterval> | null = null

const userGene = localStorage.getItem('chitogo_gene') || ''

onMounted(async () => {
  requestLocation()
  startGoHomePolling()
})

onUnmounted(() => {
  if (goHomeInterval) clearInterval(goHomeInterval)
  if (locationInterval) clearInterval(locationInterval)
  clearSpotCandidates()
})

watch(showGoHomeConfirm, (val) => {
  if (val && goHomeDialog.value) {
    goHomeDialog.value.showModal()
  } else if (!val && goHomeDialog.value) {
    goHomeDialog.value.close()
  }
})

function requestLocation() {
  if (!navigator.geolocation) {
    locationDenied.value = true
    return
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      currentLat.value = pos.coords.latitude
      currentLng.value = pos.coords.longitude
      loadCandidates()
      locationInterval = setInterval(() => {
        navigator.geolocation.getCurrentPosition(
          (p) => {
            currentLat.value = p.coords.latitude
            currentLng.value = p.coords.longitude
          },
          () => {}
        )
      }, 30000)
    },
    () => {
      locationDenied.value = true
      loadCandidates()
    }
  )
}

async function loadCandidates() {
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (!sessionId) return

  loadingCandidates.value = true
  candidatesError.value = null
  try {
    candidatesResult.value = await getCandidates(sessionId, currentLat.value, currentLng.value)
    setSpotCandidates(candidatesResult.value.candidates)
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    candidatesError.value = e?.response?.data?.detail ?? '無法載入推薦，請重試。'
  } finally {
    loadingCandidates.value = false
  }
}

async function onVenueSelected(venueId: string | number) {
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (!sessionId) return

  try {
    selectResult.value = await selectVenue(sessionId, venueId, currentLat.value, currentLng.value)
    clearSpotCandidates()
    tripPhase.value = 'NAVIGATING'
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    candidatesError.value = e?.response?.data?.detail ?? '選擇失敗，請重試。'
  }
}

function onArrived() {
  tripPhase.value = 'RATING'
}

async function onRated(_result: RateResult) {
  selectResult.value = null
  tripPhase.value = 'SELECTING'
  await loadCandidates()
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

// Go-home polling (T033)
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
      // Silently ignore polling errors
    }
  }, 60000)
}

function dismissBanner() {
  showGoHomeBanner.value = false
  suppressUntil = Date.now() + 600_000
}

// Banner go-home button
async function goHomeFromBanner() {
  showGoHomeBanner.value = false
  await triggerSummary()
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
  align-items: center;
  margin-bottom: 16px;
}

.phase-header h2 {
  font-size: 22px;
  font-weight: 700;
  color: #1e293b;
}

.gene-badge {
  background: #4d68bf;
  color: white;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
}

.loading-state, .error-state {
  text-align: center;
  padding: 40px 20px;
  color: #64748b;
}

.retry-btn {
  margin-top: 12px;
  padding: 10px 24px;
  background: #4d68bf;
  color: white;
  border: none;
  border-radius: 10px;
  font-family: inherit;
  font-size: 14px;
  cursor: pointer;
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
</style>
