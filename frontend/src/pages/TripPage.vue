<template>
  <div class="trip-container">
    <div v-if="showGoHomeBanner" class="go-home-banner">
      <p>{{ goHomeMessage }}</p>
      <div class="banner-actions">
        <button class="banner-btn continue" type="button" @click="dismissBanner">{{ locale.trip.goHome.continue }}</button>
        <button class="banner-btn gohome" type="button" @click="triggerSummary">{{ locale.trip.goHome.goHome }}</button>
      </div>
    </div>

    <div class="trip-content">
      <section class="conversation">
        <div class="message-row assistant hero-row">
          <div class="assistant-avatar assistant-avatar--hero">GO</div>
          <div class="message-stack">
            <div class="message-bubble assistant hero-bubble">
              <div class="hero-topline">
                <span class="message-label">{{ locale.trip.heroBubble.label }}</span>
                <span class="gene-badge">{{ (locale.quiz.genes[userGene] || locale.trip.heroBubble.geneDefault) }}</span>
                <span class="time-badge" :class="{ 'time-badge--sim': isSimulating }">
                  {{ isSimulating ? '⏱ ' : '' }}{{ currentTime }}
                </span>
              </div>
              <h1>{{ locale.trip.heroBubble.title }}</h1>
              <p>{{ locale.trip.heroBubble.body }}</p>
            </div>
          </div>
        </div>

        <div v-if="locationDenied" class="message-row assistant">
          <div class="assistant-avatar">Go</div>
          <div class="message-stack">
            <div class="message-bubble assistant warning-bubble">
              <p>{{ locale.trip.locationDenied.message }}</p>
            </div>
            <div class="message-surface location-surface">
              <label class="field-label" for="district-select">{{ locale.trip.locationDenied.label }}</label>
              <select id="district-select" v-model="selectedDistrict" class="district-select" @change="applyDistrictFallback">
                <option value="">{{ locale.trip.locationDenied.placeholder }}</option>
                <option v-for="d in DISTRICT_CENTROIDS" :key="d.name" :value="d.name">{{ d.name }}</option>
              </select>
            </div>
          </div>
        </div>

        <div v-if="lastRoundFeedback && !chatFlowActive" class="message-row assistant">
          <div class="assistant-avatar">Go</div>
          <div class="message-stack">
            <div class="message-bubble assistant success-bubble">
              <p>{{ lastRoundFeedbackMessage }}</p>
            </div>
          </div>
        </div>

        <div v-if="showTransportReply && !chatFlowActive" class="message-row user">
          <div class="message-bubble user">
            {{ locale.trip.transportSummary.userReply(transportSummary) }}
          </div>
        </div>

        <template v-if="tripPhase === 'TRANSPORT_PROMPT' && !chatFlowActive">
          <div class="message-row assistant">
            <div class="assistant-avatar">Go</div>
            <div class="message-stack">
              <div class="message-bubble assistant">
                <p class="message-kicker">{{ locale.trip.transportPrompt.kicker }}</p>
                <p>{{ locale.trip.transportPrompt.body }}</p>
              </div>
              <div v-if="candidatesError" class="message-bubble assistant error-bubble">
                <p>{{ candidatesError }}</p>
              </div>
              <div class="message-surface composer-surface" :class="{ 'composer-surface--loading': loadingCandidates }">
                <div class="transport-grid">
                  <label
                    v-for="mode in transportOptions"
                    :key="mode.value"
                    class="transport-option"
                    :class="{ active: transportMode === mode.value }"
                  >
                    <input
                      v-model="transportMode"
                      type="radio"
                      name="transport-mode"
                      :value="mode.value"
                    />
                    <span>{{ mode.label }}</span>
                  </label>
                </div>

                <div class="slider-group">
                  <div class="slider-header">
                    <span>{{ locale.trip.transportPrompt.sliderLabel }}</span>
                    <strong>{{ maxMinutesPerLeg }} {{ locale.trip.transportPrompt.sliderUnit }}</strong>
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

                <p class="transport-hint">{{ locale.trip.transportPrompt.hint }}</p>

                <Transition name="loading-swap" mode="out-in">
                  <div v-if="loadingCandidates" class="loading-panel" key="loading">
                    <div class="loading-orb-wrap">
                      <div class="loading-orb-ring"></div>
                      <div class="loading-orb">GO</div>
                    </div>
                    <Transition name="step-fade" mode="out-in">
                      <p class="loading-step" :key="loadingStepIndex">
                        {{ LOADING_STEPS[loadingStepIndex] }}
                      </p>
                    </Transition>
                    <div class="loading-dots">
                      <span class="dot"></span>
                      <span class="dot"></span>
                      <span class="dot"></span>
                    </div>
                  </div>
                  <button v-else class="primary-btn" type="button" key="btn" @click="submitTransport">
                    {{ locale.trip.transportPrompt.submit }}
                  </button>
                </Transition>
              </div>
            </div>
          </div>
        </template>

        <template v-else-if="tripPhase === 'SELECTING' && !chatFlowActive">
          <div class="message-row assistant">
            <div class="assistant-avatar">Go</div>
            <div class="message-stack">
              <div class="message-bubble assistant">
                <p class="message-kicker">{{ locale.trip.selecting.kicker }}</p>
                <p>{{ recommendationLead }}</p>
              </div>
              <div v-if="candidatesResult?.fallback_reason" class="message-bubble assistant subtle-bubble">
                <p>{{ candidatesResult.fallback_reason }}</p>
              </div>
              <div v-if="candidatesError" class="message-bubble assistant error-bubble">
                <p>{{ candidatesError }}</p>
              </div>
              <div v-if="loadingCandidates" class="message-surface status-surface">
                <p>{{ locale.trip.selecting.loading }}</p>
              </div>
              <div v-else-if="candidatesResult" class="message-surface candidate-surface">
                <div class="surface-header">
                  <p>{{ locale.trip.selecting.countLabel(candidatesResult.candidates.length) }}</p>
                  <button class="secondary-btn" type="button" @click="reopenTransportPrompt">{{ locale.trip.selecting.changeTransport }}</button>
                </div>

                <CandidateGrid
                  :candidates="candidatesResult.candidates"
                  :rain-filtered="candidatesResult.rain_filtered ?? []"
                  @select="onVenueSelected"
                />
              </div>
              <div v-else class="message-surface status-surface status-surface--error">
                <p>{{ candidatesError || locale.trip.selecting.noResults }}</p>
                <button class="retry-btn" type="button" @click="retryCurrentRound">{{ locale.trip.selecting.retry }}</button>
              </div>
            </div>
          </div>
        </template>

        <template v-else-if="tripPhase === 'NAVIGATING' && selectResult && !chatFlowActive">
          <div class="message-row user">
            <div class="message-bubble user">
              {{ locale.trip.navigating.userBubble(currentVenueName) }}
            </div>
          </div>

          <div class="message-row assistant">
            <div class="assistant-avatar">Go</div>
            <div class="message-stack">
              <div class="message-bubble assistant">
                <p>{{ locale.trip.navigating.assistantBubble }}</p>
              </div>
              <div class="message-surface nav-surface">
                <NavigationPanel
                  :venue="selectResult.venue"
                  :navigation="selectResult.navigation"
                  :encouragement="selectResult.encouragement_message"
                  @arrived="onArrived"
                />
              </div>
            </div>
          </div>
        </template>

        <template v-else-if="tripPhase === 'RATING' && selectResult && !chatFlowActive">
          <div class="message-row user">
            <div class="message-bubble user">
              {{ locale.trip.rating.userBubble(currentVenueName) }}
            </div>
          </div>

          <div class="message-row assistant">
            <div class="assistant-avatar">Go</div>
            <div class="message-stack">
              <div class="message-bubble assistant">
                <p>{{ locale.trip.rating.assistantBubble(currentVenueName) }}</p>
              </div>
              <div class="message-surface rating-surface">
                <RatingCard :venue="selectResult.venue" @rated="onRated" />
              </div>
            </div>
          </div>
        </template>

        <template v-for="msg in messages" :key="msg.id">
          <div v-if="msg.role === 'user'" class="message-row user">
            <div class="message-bubble user">{{ msg.text }}</div>
          </div>
          <div v-else class="message-row assistant">
            <div class="assistant-avatar">Go</div>
            <div class="message-stack">
              <div v-if="msg.pending || msg.text" class="message-bubble assistant">
                <template v-if="msg.pending">
                  <div class="loading-dots">
                    <span class="dot"></span>
                    <span class="dot"></span>
                    <span class="dot"></span>
                  </div>
                </template>
                <p v-else>{{ msg.text }}</p>
              </div>
              <div v-if="chatSelectError && !msg.pending" class="chat-select-error">{{ chatSelectError }}</div>
              <div v-if="msg.widget?.kind === 'navigation'" class="message-surface nav-surface">
                <NavigationPanel
                  :venue="msg.widget.data.venue"
                  :navigation="msg.widget.data.navigation"
                  :encouragement="msg.widget.data.encouragement_message"
                  @arrived="onArrivedFromMessage"
                />
              </div>
              <div v-if="msg.widget?.kind === 'rating'" class="message-surface rating-surface">
                <RatingCard
                  :venue="msg.widget.data.venue"
                  @rated="(p: RatingPayload) => onRatedFromMessage(p, msg.id)"
                />
              </div>
              <div
                v-if="msg.widget?.kind === 'transport_prompt' && !msg.widget.submitted"
                class="message-surface composer-surface"
                :class="{ 'composer-surface--loading': loadingCandidates }"
              >
                <div class="transport-grid">
                  <label
                    v-for="mode in transportOptions"
                    :key="mode.value"
                    class="transport-option"
                    :class="{ active: transportMode === mode.value }"
                  >
                    <input v-model="transportMode" type="radio" name="transport-mode" :value="mode.value" />
                    <span>{{ mode.label }}</span>
                  </label>
                </div>
                <div class="slider-group">
                  <div class="slider-header">
                    <span>每段最長時間</span>
                    <strong>{{ maxMinutesPerLeg }} 分鐘</strong>
                  </div>
                  <input v-model.number="maxMinutesPerLeg" type="range" min="5" max="120" step="5" class="slider" />
                </div>
                <Transition name="loading-swap" mode="out-in">
                  <div v-if="loadingCandidates" class="loading-panel" key="loading">
                    <div class="loading-orb-wrap">
                      <div class="loading-orb-ring"></div>
                      <div class="loading-orb">GO</div>
                    </div>
                    <Transition name="step-fade" mode="out-in">
                      <p class="loading-step" :key="loadingStepIndex">{{ LOADING_STEPS[loadingStepIndex] }}</p>
                    </Transition>
                    <div class="loading-dots">
                      <span class="dot"></span>
                      <span class="dot"></span>
                      <span class="dot"></span>
                    </div>
                  </div>
                  <button v-else class="primary-btn" type="button" key="btn" @click="submitTransportFromMessage(msg.id)">
                    開始聽推薦
                  </button>
                </Transition>
              </div>
              <div v-if="msg.widget?.kind === 'selecting' && !msg.widget.submitted" class="message-surface candidate-surface">
                <div class="surface-header">
                  <p>我先幫你挑了 {{ msg.widget.data.candidates.length }} 個選項，你可以直接點卡片決定這一站。</p>
                  <button class="secondary-btn" type="button" @click="reopenTransportPrompt">改交通</button>
                </div>
                <CandidateGrid
                  :candidates="msg.widget.data.candidates"
                  :rain-filtered="msg.widget.data.rain_filtered ?? []"
                  @select="onVenueSelected"
                />
              </div>
            </div>
          </div>
        </template>

        <div v-if="tripPhase !== 'ENDED'" class="global-actions">
          <button class="go-home-inline" type="button" @click="showGoHomeConfirm = true">
            {{ locale.trip.goHome.goHome }}
          </button>
        </div>
      </section>
    </div>

    <dialog ref="goHomeDialog" class="confirm-dialog">
      <p>{{ locale.trip.dialog.endTripConfirm }}</p>
      <div class="dialog-actions">
        <button class="dialog-btn cancel" type="button" @click="closeGoHomeDialog">{{ locale.trip.dialog.cancel }}</button>
        <button class="dialog-btn confirm" type="button" @click="triggerSummary" :disabled="summaryLoading">
          {{ summaryLoading ? locale.trip.dialog.ending : locale.trip.dialog.confirm }}
        </button>
      </div>
    </dialog>

    <ChatComposer
      v-if="tripPhase !== 'ENDED'"
      :sending="sendingMessage"
      @submit="handleComposerSubmit"
    />

    <DemoTimeTweaker />
    <DemoLocationTweaker />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import CandidateGrid from '../components/CandidateGrid.vue'
import ChatComposer from '../components/ChatComposer.vue'
import DemoLocationTweaker from '../components/DemoLocationTweaker.vue'
import DemoTimeTweaker from '../components/DemoTimeTweaker.vue'
import NavigationPanel from '../components/NavigationPanel.vue'
import RatingCard from '../components/RatingCard.vue'
import { useSimLocation } from '../composables/useSimLocation'
import { useSimTime } from '../composables/useSimTime'
import { checkGoHome, getCandidates, getSummary, selectVenue, sendMessage, snoozeGoHome, submitDemand } from '../services/api'
import type { ChatMessage, ChatWidget } from '../types/chat'
import type { ChatCandidate } from '../types/itinerary'
import { useLocale } from '../composables/useLocale'
import type {
  CandidateTransportInput,
  CandidatesResult,
  RateResult,
  SelectResult,
  TransportMode,
} from '../types/trip'
import { useMapState } from '../composables/useMapState'

const router = useRouter()
const { lang, locale } = useLocale()

const LOADING_STEPS = computed(() => locale.value.trip.loadingSteps)
const {
  setSpotCandidates,
  clearSpotCandidates,
  setCurrentLocation,
  setActiveNavigation,
  clearNavigation,
  resetMapState,
} = useMapState()

type TripPhase = 'TRANSPORT_PROMPT' | 'SELECTING' | 'NAVIGATING' | 'RATING' | 'ENDED'

interface LastRoundFeedback {
  venueName: string
  stars: number
  tags: string[]
}

interface RatingPayload {
  result: RateResult
  stars: number
  tags: string[]
}

const currentLat = ref(25.0478)
const currentLng = ref(121.5170)
const locationDenied = ref(false)
const selectedDistrict = ref('')
const locationSource = ref<'approximate' | 'gps' | 'fallback'>('approximate')

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

const transportOptions = computed<Array<{ value: TransportMode; label: string }>>(() => [
  { value: 'walk', label: locale.value.trip.transport.walk },
  { value: 'transit', label: locale.value.trip.transport.transit },
  { value: 'drive', label: locale.value.trip.transport.drive },
])

const tripPhase = ref<TripPhase>('TRANSPORT_PROMPT')
const candidatesResult = ref<CandidatesResult | null>(null)
const selectResult = ref<SelectResult | null>(null)
const loadingCandidates = ref(false)
const loadingStepIndex = ref(0)
let loadingStepInterval: ReturnType<typeof setInterval> | null = null
const candidatesError = ref<string | null>(null)
const summaryLoading = ref(false)
const showGoHomeConfirm = ref(false)
const messages = ref<ChatMessage[]>([])
const sendingMessage = ref(false)
const goHomeDialog = ref<HTMLDialogElement | null>(null)
const chatSelectingId = ref<string | number | null>(null)
const chatSelectError = ref<string | null>(null)
const chatFlowActive = ref(false)

const transportMode = ref<TransportMode>('transit')
const maxMinutesPerLeg = ref(30)
const lastRequestedTransport = ref<CandidateTransportInput | null>(null)
const selectedVenueName = ref('')
const lastRoundFeedback = ref<LastRoundFeedback | null>(null)

const { isSimulating, simTimeHHMM, effectiveDate, formatTime } = useSimTime()
const currentTime = computed(() => formatTime(effectiveDate.value))

const { isSimLocating, simLat, simLng, simLabel } = useSimLocation()
const effectiveLat = computed(() => isSimLocating.value && simLat.value !== null ? simLat.value : currentLat.value)
const effectiveLng = computed(() => isSimLocating.value && simLng.value !== null ? simLng.value : currentLng.value)
let timeInterval: ReturnType<typeof setInterval> | null = null

const showGoHomeBanner = ref(false)
const goHomeMessage = ref('')
let suppressUntil = 0
let goHomeInterval: ReturnType<typeof setInterval> | null = null
let locationInterval: ReturnType<typeof setInterval> | null = null

const userGene = localStorage.getItem('chitogo_gene') || ''

const transportSummary = computed(() => {
  const currentTransport = lastRequestedTransport.value
  if (!currentTransport) return locale.value.trip.transportSummary.notSelected
  return locale.value.trip.transportSummary.summary(transportLabel(currentTransport.mode), currentTransport.max_minutes_per_leg)
})

const showTransportReply = computed(() => (
  ['SELECTING', 'NAVIGATING', 'RATING'].includes(tripPhase.value) && Boolean(lastRequestedTransport.value)
))

const currentVenueName = computed(() => {
  const v = selectResult.value?.venue
  if (v) return (lang.value === 'en' && v.name_en) ? v.name_en : v.name
  return selectedVenueName.value || locale.value.common.defaultAddress
})

const recommendationLead = computed(() => {
  const rl = locale.value.trip.recommendLead
  if (loadingCandidates.value) {
    return rl.loading(transportSummary.value)
  }

  if (!candidatesResult.value) {
    return rl.noResult(transportSummary.value)
  }

  const cr = candidatesResult.value
  let lead = ''
  if (cr.go_home_reminder) {
    lead = cr.go_home_reminder + '。'
  }
  if ((cr.rain_filtered?.length ?? 0) > 0) {
    lead += rl.rain
  }
  if (cr.homing_active) {
    lead += rl.homing
  }

  if (cr.restaurant_count > 0 && cr.attraction_count > 0) {
    lead += rl.both
  } else if (cr.restaurant_count > 0) {
    lead += rl.restaurantsOnly
  } else {
    lead += rl.attractionsOnly
  }

  return lead
})

const lastRoundFeedbackMessage = computed(() => {
  if (!lastRoundFeedback.value) return ''
  const t = locale.value.trip
  const tagSummary = lastRoundFeedback.value.tags.length
    ? t.feedbackTags(lastRoundFeedback.value.tags.join('、'))
    : ''
  return t.feedbackMessage(lastRoundFeedback.value.venueName, lastRoundFeedback.value.stars, tagSummary)
})

onMounted(() => {
  requestLocation()
  startGoHomePolling()
  // Tick every minute so effectiveDate refreshes when not simulating
  timeInterval = setInterval(() => { /* triggers reactivity via effectiveDate */ }, 60000)
})

onUnmounted(() => {
  if (goHomeInterval) clearInterval(goHomeInterval)
  if (locationInterval) clearInterval(locationInterval)
  if (timeInterval) clearInterval(timeInterval)
  if (loadingStepInterval) clearInterval(loadingStepInterval)
  clearSpotCandidates()
  resetMapState()
})

watch(showGoHomeConfirm, value => {
  if (value && goHomeDialog.value) {
    goHomeDialog.value.showModal()
  } else if (!value && goHomeDialog.value) {
    goHomeDialog.value.close()
  }
})

watch(loadingCandidates, loading => {
  if (loading) {
    loadingStepIndex.value = 0
    loadingStepInterval = setInterval(() => {
      loadingStepIndex.value = (loadingStepIndex.value + 1) % LOADING_STEPS.length
    }, 1800)
  } else {
    if (loadingStepInterval) {
      clearInterval(loadingStepInterval)
      loadingStepInterval = null
    }
  }
})

watch(
  [currentLat, currentLng, locationSource, selectedDistrict, isSimLocating, effectiveLat, effectiveLng],
  () => {
    syncMapLocation()
  },
  { immediate: true },
)

function transportLabel(mode: TransportMode) {
  return transportOptions.value.find(option => option.value === mode)?.label || mode
}

function applyDistrictFallback() {
  const centroid = DISTRICT_CENTROIDS.find(d => d.name === selectedDistrict.value)
  if (!centroid) return

  currentLat.value = centroid.lat
  currentLng.value = centroid.lng
  locationSource.value = 'fallback'

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
      locationDenied.value = false
      locationSource.value = 'gps'
      currentLat.value = pos.coords.latitude
      currentLng.value = pos.coords.longitude
      locationInterval = setInterval(() => {
        navigator.geolocation.getCurrentPosition(
          latest => {
            locationSource.value = 'gps'
            currentLat.value = latest.coords.latitude
            currentLng.value = latest.coords.longitude
          },
          () => {}
        )
      }, 30000)
    },
    () => {
      locationDenied.value = true
      if (locationSource.value !== 'fallback') {
        locationSource.value = 'approximate'
      }
    }
  )
}

function syncMapLocation() {
  const label = isSimLocating.value && simLabel.value
    ? `📍 模擬位置：${simLabel.value}`
    : locationSource.value === 'gps'
      ? 'GPS 目前位置'
      : locationSource.value === 'fallback'
        ? `${selectedDistrict.value || '手動起點'}（手動設定）`
        : locationDenied.value
          ? '起點（預設）'
          : '定位中'

  setCurrentLocation({
    lat: effectiveLat.value,
    lng: effectiveLng.value,
    label,
    source: locationSource.value,
  })
}

function buildTransportInput(): CandidateTransportInput {
  return {
    mode: transportMode.value,
    max_minutes_per_leg: maxMinutesPerLeg.value,
  }
}

async function submitTransport() {
  await loadCandidates(buildTransportInput())
}

async function loadCandidates(transport?: CandidateTransportInput) {
  const sessionId = localStorage.getItem('chitogo_session_id')
  const activeTransport = transport || lastRequestedTransport.value
  if (!sessionId || !activeTransport) {
    candidatesError.value = '缺少行程資料，請重新開始。'
    tripPhase.value = 'TRANSPORT_PROMPT'
    return
  }

  loadingCandidates.value = true
  candidatesError.value = null
  candidatesResult.value = null
  selectedVenueName.value = ''
  lastRequestedTransport.value = activeTransport
  lastRoundFeedback.value = null
  clearNavigation()
  clearSpotCandidates()

  try {
    candidatesResult.value = await getCandidates(
      sessionId,
      effectiveLat.value,
      effectiveLng.value,
      activeTransport,
      simTimeHHMM.value ?? undefined,
    )
    setSpotCandidates(candidatesResult.value.candidates)
    tripPhase.value = 'SELECTING'
  } catch (err: unknown) {
    const error = err as { response?: { data?: { detail?: string } } }
    candidatesError.value = error?.response?.data?.detail ?? '無法載入推薦，請重試。'
    clearSpotCandidates()
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

  const matchedCard = candidatesResult.value?.candidates.find(
    card => String(card.venue_id) === String(venueId)
  )
  selectedVenueName.value = matchedCard?.name || selectedVenueName.value

  try {
    candidatesError.value = null
    selectResult.value = await selectVenue(sessionId, venueId, effectiveLat.value, effectiveLng.value)
    selectedVenueName.value = selectResult.value.venue.name
    clearSpotCandidates()
    setActiveNavigation({
      venue: selectResult.value.venue,
      transportMode: selectResult.value.navigation.transport_mode,
      googleMapsUrl: selectResult.value.navigation.google_maps_url,
      appleMapsUrl: selectResult.value.navigation.apple_maps_url,
      estimatedTravelMin: selectResult.value.navigation.estimated_travel_min,
    })

    if (chatFlowActive.value) {
      const snapshot = selectResult.value
      messages.value = [...messages.value, {
        id: crypto.randomUUID(),
        role: 'user',
        text: `那就去 ${snapshot.venue.name}。`,
      }]
      messages.value = [...messages.value, {
        id: crypto.randomUUID(),
        role: 'assistant',
        text: '好，我把路線整理好了。到了之後按一下「我到了，繼續」，我再接著問你感受。',
        widget: { kind: 'navigation', data: snapshot } satisfies ChatWidget,
      }]
    }

    tripPhase.value = 'NAVIGATING'
  } catch (err: unknown) {
    const error = err as { response?: { data?: { detail?: string } } }
    candidatesError.value = error?.response?.data?.detail ?? '選擇失敗，請重試。'
    selectedVenueName.value = ''
  }
}

async function onChatVenueSelected(candidate: ChatCandidate) {
  if (chatSelectingId.value !== null) return
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (!sessionId) return

  chatSelectError.value = null
  chatSelectingId.value = candidate.place_id
  selectedVenueName.value = candidate.name

  try {
    selectResult.value = await selectVenue(sessionId, candidate.place_id, effectiveLat.value, effectiveLng.value)
    selectedVenueName.value = selectResult.value.venue.name
    clearSpotCandidates()
    setActiveNavigation({
      venue: selectResult.value.venue,
      transportMode: selectResult.value.navigation.transport_mode,
      googleMapsUrl: selectResult.value.navigation.google_maps_url,
      appleMapsUrl: selectResult.value.navigation.apple_maps_url,
      estimatedTravelMin: selectResult.value.navigation.estimated_travel_min,
    })

    const snapshot = selectResult.value
    messages.value = [...messages.value, {
      id: crypto.randomUUID(),
      role: 'user',
      text: `那就去 ${snapshot.venue.name}。`,
    }]
    messages.value = [...messages.value, {
      id: crypto.randomUUID(),
      role: 'assistant',
      text: '好，我把路線整理好了。到了之後按一下「我到了，繼續」，我再接著問你感受。',
      widget: { kind: 'navigation', data: snapshot } satisfies ChatWidget,
    }]

    chatFlowActive.value = true
    tripPhase.value = 'NAVIGATING'
  } catch (err: unknown) {
    const error = err as { response?: { data?: { detail?: string } } }
    const detail = error?.response?.data?.detail ?? ''
    if (detail.startsWith('state_error:')) {
      chatSelectError.value = '目前行程正在進行中，請先完成當前景點再切換。'
    } else {
      chatSelectError.value = '無法前往該景點，請稍後再試。'
    }
    selectedVenueName.value = ''
  } finally {
    chatSelectingId.value = null
  }
}

function onArrived() {
  if (selectResult.value?.venue.venue_id === 'GO_HOME') {
    void triggerSummary()
    return
  }
  clearNavigation()
  tripPhase.value = 'RATING'
}

function onRated(payload: RatingPayload) {
  lastRoundFeedback.value = {
    venueName: currentVenueName.value,
    stars: payload.stars,
    tags: payload.tags,
  }

  selectResult.value = null
  selectedVenueName.value = ''
  candidatesResult.value = null
  candidatesError.value = null
  clearNavigation()
  tripPhase.value = 'TRANSPORT_PROMPT'
}

function onArrivedFromMessage() {
  if (selectResult.value?.venue.venue_id === 'GO_HOME') {
    void triggerSummary()
    return
  }

  const venueName = selectResult.value?.venue.name || selectedVenueName.value || '這一站'
  const snapshot = selectResult.value!

  clearNavigation()

  messages.value = [...messages.value, {
    id: crypto.randomUUID(),
    role: 'user',
    text: `我到 ${venueName} 了。`,
  }]
  messages.value = [...messages.value, {
    id: crypto.randomUUID(),
    role: 'assistant',
    text: `這一站走完了，你覺得 ${venueName} 怎麼樣？給我一個評價，我下一輪會更懂你的口味。`,
    widget: { kind: 'rating', data: snapshot } satisfies ChatWidget,
  }]

  tripPhase.value = 'RATING'
}

function onRatedFromMessage(payload: RatingPayload, msgId: string) {
  const venueName = selectResult.value?.venue.name || selectedVenueName.value || '這一站'
  const tagSummary = payload.tags.length ? `，也提到 ${payload.tags.join('、')}` : ''
  const feedbackText = `收到，你剛剛給 ${venueName} ${payload.stars} 星${tagSummary}。下一輪我會照這個感受繼續推薦。`

  messages.value = messages.value.map(m =>
    m.id === msgId ? { ...m, widget: undefined } : m
  )

  messages.value = [...messages.value, {
    id: crypto.randomUUID(),
    role: 'assistant',
    text: feedbackText,
  }]

  messages.value = [...messages.value, {
    id: crypto.randomUUID(),
    role: 'assistant',
    text: '這一輪想繼續怎麼移動？選好就按「開始聽推薦」。',
    widget: { kind: 'transport_prompt' } satisfies ChatWidget,
  }]

  selectResult.value = null
  selectedVenueName.value = ''
  candidatesResult.value = null
  candidatesError.value = null
  clearNavigation()
  tripPhase.value = 'TRANSPORT_PROMPT'
}

async function submitTransportFromMessage(msgId: string) {
  messages.value = [...messages.value, {
    id: crypto.randomUUID(),
    role: 'user',
    text: `這一輪我想用 ${transportSummary.value} 找景點。`,
  }]

  const pendingId = crypto.randomUUID()
  messages.value = [...messages.value, {
    id: pendingId,
    role: 'assistant',
    text: '',
    pending: true,
  }]

  await loadCandidates(buildTransportInput())

  // Hide the transport form only after loading finishes so the orb animation plays
  messages.value = messages.value.map(m =>
    m.id === msgId
      ? { ...m, widget: { kind: 'transport_prompt' as const, submitted: true } }
      : m
  )

  if (candidatesResult.value) {
    messages.value = messages.value.map(m =>
      m.id === pendingId
        ? { ...m, text: recommendationLead.value, pending: false, widget: { kind: 'selecting' as const, data: candidatesResult.value! } }
        : m
    )
  } else {
    messages.value = messages.value.map(m =>
      m.id === pendingId
        ? { ...m, text: candidatesError.value || '無法載入推薦，請重試。', pending: false }
        : m
    )
  }
}

async function handleComposerSubmit(text: string) {
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (!sessionId) return

  const userMsgId = crypto.randomUUID()
  const pendingId = crypto.randomUUID()

  messages.value = [...messages.value, { id: userMsgId, role: 'user', text }]
  messages.value = [...messages.value, { id: pendingId, role: 'assistant', text: '', pending: true }]
  sendingMessage.value = true

  try {
    const res = await sendMessage({
      session_id: sessionId,
      message: text,
      user_context: { lat: effectiveLat.value, lng: effectiveLng.value },
    })

    if (res.candidates?.length) {
      // Backend signalled recommendation intent — collapse old grids and fetch text-aware results
      messages.value = messages.value.map(m =>
        m.widget?.kind === 'selecting' ? { ...m, widget: { ...m.widget, submitted: true } } : m
      )
      candidatesResult.value = null
      chatFlowActive.value = true

      let widget: ChatWidget | undefined
      try {
        const demand = await submitDemand(sessionId, text, effectiveLat.value, effectiveLng.value)
        const result = {
          session_id: demand.session_id,
          candidates: demand.alternatives,
          rain_filtered: demand.rain_filtered ?? [],
          partial: false,
          fallback_reason: demand.fallback_reason,
          restaurant_count: demand.alternatives.filter(c => c.category === 'restaurant').length,
          attraction_count: demand.alternatives.filter(c => c.category === 'attraction').length,
        }
        setSpotCandidates(result.candidates)
        widget = { kind: 'selecting', data: result }
      } catch {
        // Fall through: show text reply without candidate grid
      }
      messages.value = messages.value.map(m =>
        m.id === pendingId
          ? { ...m, text: res.message, pending: false, ...(widget ? { widget } : {}) }
          : m
      )
    } else {
      messages.value = messages.value.map(m =>
        m.id === pendingId
          ? { ...m, text: res.message, pending: false }
          : m
      )
    }
  } catch {
    messages.value = messages.value.map(m =>
      m.id === pendingId
        ? { ...m, text: '抱歉，無法處理你的訊息，請再試一次。', pending: false }
        : m
    )
  } finally {
    sendingMessage.value = false
  }
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

async function runGoHomeCheck() {
  if (tripPhase.value === 'ENDED') return
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (!sessionId) return
  try {
    const status = await checkGoHome(sessionId, effectiveLat.value, effectiveLng.value, simTimeHHMM.value ?? undefined)
    if (status.remind) {
      goHomeMessage.value = status.message || '該回家啦！'
      showGoHomeBanner.value = true
    }
  } catch {
    // Ignore polling errors during the trip loop.
  }
}

function startGoHomePolling() {
  goHomeInterval = setInterval(async () => {
    if (Date.now() < suppressUntil) return
    await runGoHomeCheck()
  }, 60000)
}

watch(simTimeHHMM, async () => {
  suppressUntil = 0
  if (tripPhase.value === 'SELECTING' && lastRequestedTransport.value) {
    await loadCandidates(lastRequestedTransport.value)
  }
  await runGoHomeCheck()
})

async function dismissBanner() {
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (sessionId) {
    try {
      await snoozeGoHome(sessionId)
    } catch {
      // Ignore snooze errors
    }
  }
  showGoHomeBanner.value = false
  suppressUntil = Date.now() + 600_000
}
</script>

<style scoped>
.trip-container {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(191, 219, 254, 0.65), transparent 28%),
    radial-gradient(circle at top right, rgba(224, 231, 255, 0.85), transparent 32%),
    linear-gradient(180deg, #eff6ff 0%, #f8fbff 48%, #f8fafc 100%);
  display: flex;
  flex-direction: column;
  position: relative;
}

.go-home-banner {
  background: linear-gradient(135deg, #1d4ed8 0%, #4338ca 100%);
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
  border-radius: 999px;
  font-size: 13px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  border: none;
}

.banner-btn.continue {
  background: rgba(255, 255, 255, 0.18);
  color: white;
}

.banner-btn.gohome {
  background: white;
  color: #1d4ed8;
}

.trip-content {
  flex: 1;
  padding: 28px 20px 140px;
  max-width: 760px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

.conversation {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-stack {
  flex: 1;
  max-width: 640px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.assistant-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #bfdbfe 0%, #c7d2fe 100%);
  color: #1e3a8a;
  font-size: 14px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 10px 20px rgba(37, 99, 235, 0.14);
  flex-shrink: 0;
}

.assistant-avatar--hero {
  width: 48px;
  height: 48px;
  background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
  color: white;
}

.message-bubble {
  border-radius: 22px;
  padding: 16px 18px;
  line-height: 1.65;
  font-size: 15px;
}

.message-bubble.assistant {
  background: rgba(255, 255, 255, 0.92);
  color: #1e293b;
  border: 1px solid rgba(191, 219, 254, 0.75);
  box-shadow: 0 12px 30px rgba(148, 163, 184, 0.14);
}

.message-bubble.user {
  max-width: min(78%, 460px);
  background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
  color: white;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.22);
}

.hero-row .message-stack {
  max-width: 680px;
}

.hero-bubble {
  padding: 20px 22px;
}

.hero-topline {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.message-label,
.message-kicker {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #2563eb;
}

.message-kicker {
  margin-bottom: 6px;
}

.hero-bubble h1 {
  font-size: 28px;
  line-height: 1.2;
  color: #0f172a;
  margin-bottom: 10px;
}

.hero-bubble p,
.message-bubble p {
  margin: 0;
}

.gene-badge {
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
}

.time-badge {
  background: rgba(15, 23, 42, 0.08);
  color: #475569;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
}

.time-badge--sim {
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fcd34d;
}

.warning-bubble {
  border-color: #fde68a;
  background: #fffbeb;
}

.success-bubble {
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.subtle-bubble {
  background: #eff6ff;
  border-color: #bfdbfe;
}

.error-bubble {
  border-color: #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}

.message-surface {
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(191, 219, 254, 0.7);
  border-radius: 24px;
  padding: 18px;
  box-shadow: 0 14px 34px rgba(148, 163, 184, 0.12);
}

.composer-surface,
.candidate-surface,
.nav-surface,
.rating-surface,
.location-surface {
  backdrop-filter: blur(12px);
}

.composer-surface--loading .transport-grid,
.composer-surface--loading .slider-group,
.composer-surface--loading .transport-hint {
  opacity: 0.35;
  pointer-events: none;
  user-select: none;
}

.location-surface {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.field-label {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.district-select {
  padding: 12px 14px;
  border: 1.5px solid #cbd5e1;
  border-radius: 14px;
  font-family: inherit;
  font-size: 14px;
  color: #1e293b;
  background: white;
}

.transport-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.transport-option {
  border: 1.5px solid #dbeafe;
  border-radius: 16px;
  padding: 14px 12px;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  color: #334155;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  background: white;
}

.transport-option input {
  margin: 0;
}

.transport-option.active {
  border-color: #3b82f6;
  background: #eff6ff;
  color: #1d4ed8;
  box-shadow: 0 8px 20px rgba(59, 130, 246, 0.12);
}

.slider-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 18px;
}

.slider-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #334155;
  font-size: 14px;
}

.slider {
  width: 100%;
}

.transport-hint {
  margin: 18px 0 0;
  font-size: 14px;
  color: #64748b;
}

.surface-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.surface-header p {
  margin: 0;
  font-size: 14px;
  color: #475569;
  line-height: 1.6;
}

.status-surface {
  text-align: center;
  color: #475569;
}

.status-surface p {
  margin: 0;
  font-size: 15px;
}

.status-surface--error {
  border-color: #fecaca;
  background: #fef2f2;
}

.primary-btn,
.secondary-btn,
.retry-btn {
  border: none;
  border-radius: 999px;
  font-family: inherit;
  cursor: pointer;
  transition: transform 0.18s, box-shadow 0.18s, filter 0.18s;
}

.primary-btn {
  width: 100%;
  margin-top: 18px;
  padding: 14px 18px;
  background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
  color: white;
  font-size: 15px;
  font-weight: 700;
  box-shadow: 0 14px 24px rgba(37, 99, 235, 0.22);
}

.primary-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
  box-shadow: none;
}

.secondary-btn {
  padding: 10px 16px;
  background: white;
  color: #1d4ed8;
  border: 1.5px solid #bfdbfe;
  font-size: 13px;
  font-weight: 700;
}

.retry-btn {
  margin-top: 12px;
  padding: 10px 18px;
  background: #1d4ed8;
  color: white;
  font-size: 14px;
  font-weight: 700;
}

.primary-btn:not(:disabled):hover,
.secondary-btn:hover,
.retry-btn:hover {
  transform: translateY(-1px);
}

.global-actions {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

.go-home-inline {
  padding: 12px 32px;
  background: rgba(255, 255, 255, 0.94);
  color: #dc2626;
  border: 2px solid #fecaca;
  border-radius: 999px;
  font-size: 15px;
  font-family: inherit;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  transition: all 0.2s;
  backdrop-filter: blur(8px);
}

.go-home-inline:hover {
  border-color: #ef4444;
  background: #fff5f5;
  transform: translateY(-1px);
}

.confirm-dialog {
  border: none;
  border-radius: 20px;
  padding: 28px 24px;
  max-width: 320px;
  width: 90%;
  box-shadow: 0 20px 48px rgba(15, 23, 42, 0.24);
  font-family: inherit;
}

.confirm-dialog::backdrop {
  background: rgba(15, 23, 42, 0.4);
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
  border-radius: 12px;
  font-size: 15px;
  font-family: inherit;
  font-weight: 700;
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

.loading-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 24px 0 8px;
}

.loading-orb-wrap {
  position: relative;
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.loading-orb {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
  color: white;
  font-size: 16px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.3);
  position: relative;
  z-index: 1;
}

.loading-orb-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: transparent;
  border: 3px solid rgba(37, 99, 235, 0.35);
  animation: pulse-ring 1.6s ease-out infinite;
}

.loading-step {
  font-size: 15px;
  font-weight: 600;
  color: #1d4ed8;
  text-align: center;
  margin: 0;
  min-height: 1.5em;
}

.loading-dots {
  display: flex;
  gap: 7px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #93c5fd;
  animation: bounce-dot 1.2s ease-in-out infinite;
}

.dot:nth-child(2) {
  animation-delay: 0.2s;
}

.dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes pulse-ring {
  0% { transform: scale(1); opacity: 0.7; }
  70% { transform: scale(1.55); opacity: 0; }
  100% { transform: scale(1.55); opacity: 0; }
}

@keyframes bounce-dot {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-8px); }
}

.loading-swap-enter-active,
.loading-swap-leave-active {
  transition: opacity 0.22s, transform 0.22s;
}

.loading-swap-enter-from,
.loading-swap-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

.step-fade-enter-active,
.step-fade-leave-active {
  transition: opacity 0.3s, transform 0.3s;
}

.step-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.step-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@media (max-width: 640px) {
  .trip-content {
    padding: 20px 14px 140px;
  }

  .message-row {
    gap: 10px;
  }

  .assistant-avatar {
    width: 36px;
    height: 36px;
    font-size: 13px;
  }

  .assistant-avatar--hero {
    width: 42px;
    height: 42px;
  }

  .hero-bubble h1 {
    font-size: 24px;
  }

  .message-bubble.user {
    max-width: calc(100% - 32px);
  }

  .transport-grid {
    grid-template-columns: 1fr;
  }

  .surface-header {
    flex-direction: column;
    align-items: stretch;
  }

  .global-actions {
    margin-top: 16px;
  }

  .go-home-inline {
    width: 100%;
    padding: 14px 20px;
  }
}

.chat-select-error {
  font-size: 0.78rem;
  color: #ef4444;
  padding: 6px 4px 2px;
  line-height: 1.4;
}

/* ═══════════════════════════════════════════
   MOBILE  ≤ 767 px
═══════════════════════════════════════════ */
@media (max-width: 767px) {
  .trip-container {
    min-height: unset;
  }

  /* Main content area: less horizontal padding, more bottom padding for bottom nav */
  .trip-content {
    padding: 16px 12px 100px;
  }

  /* Go-home banner: stack vertically on very narrow screens */
  .go-home-banner {
    flex-wrap: wrap;
    gap: 8px;
    padding: 12px 14px;
  }

  .go-home-banner p {
    width: 100%;
    flex: unset;
    font-size: 13px;
  }

  .banner-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .banner-btn {
    padding: 8px 16px;
    min-height: 36px;
    font-size: 13px;
  }

  /* Transport grid: 2 columns on mobile */
  .transport-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .transport-option {
    padding: 12px 8px;
    font-size: 13px;
    min-height: 48px;
  }

  /* Messages */
  .message-row {
    gap: 8px;
  }

  .message-stack {
    max-width: 100%;
  }

  .message-bubble {
    font-size: 14px;
    padding: 12px 14px;
  }

  .hero-bubble {
    padding: 14px 16px;
  }

  .message-bubble.user {
    max-width: min(88%, 460px);
  }

  .assistant-avatar {
    width: 32px;
    height: 32px;
    font-size: 11px;
    flex-shrink: 0;
  }

  .assistant-avatar--hero {
    width: 36px;
    height: 36px;
  }

  /* Hero heading */
  .trip-content h1 {
    font-size: 20px;
  }

  /* Buttons */
  .primary-btn {
    padding: 14px 18px;
    font-size: 15px;
    min-height: 48px;
  }

  .secondary-btn {
    padding: 10px 14px;
    min-height: 44px;
    font-size: 13px;
  }

  .retry-btn {
    padding: 10px 16px;
    min-height: 44px;
  }

  /* District select */
  .district-select {
    font-size: 16px;
    min-height: 44px;
  }

  /* Rating surface */
  .rating-surface {
    padding: 14px;
  }

  /* Confirm dialog: tighter padding */
  .confirm-dialog {
    padding: 20px 16px;
  }
}
</style>
