<template>
  <div class="setup-container">
    <div class="setup-card">
      <h1 class="title">住宿安排</h1>
      <p class="subtitle">先確認今天的住宿狀態，再進入返回設定</p>

      <div class="mode-grid">
        <button
          v-for="option in modeOptions"
          :key="option.value"
          type="button"
          class="mode-card"
          :class="{ active: mode === option.value }"
          @click="changeMode(option.value)"
        >
          <div class="mode-title">{{ option.label }}</div>
          <div class="mode-desc">{{ option.description }}</div>
        </button>
      </div>

      <section v-if="mode === 'booked'" class="section">
        <h3 class="section-title">檢查已預訂飯店</h3>
        <input
          :value="hotelName"
          class="text-input"
          placeholder="輸入飯店名稱"
          @input="onBookedHotelInput"
        />

        <div v-if="validationResult && !validationResult.valid" class="warning-box">
          <div class="warning-title">查無此合法旅宿</div>

          <div v-if="validationResult.alternatives.length" class="result-block">
            <div class="result-label">你是不是要找：</div>
            <HotelRecommendationGrid
              :cards="validationResult.alternatives"
              :selected-name="hotelName"
              @select="chooseHotel"
            />
          </div>

          <div v-if="hotelRecommendations.length" class="result-block">
            <div class="result-label">可改訂以下合法旅宿：</div>
            <HotelRecommendationGrid
              :cards="hotelRecommendations"
              :selected-name="hotelName"
              @select="chooseHotel"
            />
          </div>
        </div>
      </section>

      <section v-else-if="mode === 'need_hotel'" class="section">
        <h3 class="section-title">推薦合法飯店</h3>
        <select
          v-model="district"
          class="select-input"
          @change="resetHotelRecommendations(true)"
        >
          <option value="">不限地區</option>
          <option v-for="item in DISTRICTS" :key="item" :value="item">{{ item }}</option>
        </select>

        <div class="radio-group horizontal">
          <label v-for="tier in budgetOptions" :key="tier.value" class="radio-label">
            <input
              v-model="budgetTier"
              type="radio"
              :value="tier.value"
              @change="resetHotelRecommendations(true)"
            >
            {{ tier.label }}
          </label>
        </div>

        <div v-if="hotelName" class="selection-banner">
          已選擇：{{ hotelName }}
        </div>

        <div v-if="recommendationMessage" class="info-box">
          {{ recommendationMessage }}
        </div>

        <div v-if="hotelRecommendations.length" class="result-block">
          <div class="result-label">推薦清單</div>
          <HotelRecommendationGrid
            :cards="hotelRecommendations"
            :selected-name="hotelName"
            @select="chooseHotel"
          />
        </div>
      </section>

      <section v-else class="section">
        <h3 class="section-title">今天不住宿</h3>
        <div class="info-box">
          這個選項會直接跳到下一步，只填返回時間與返回地點。
        </div>
      </section>

      <div v-if="errorText" class="error">{{ errorText }}</div>

      <button class="submit-btn" :disabled="loading" @click="handleSubmit">
        {{ loading ? '處理中…' : submitLabel }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import HotelRecommendationGrid from '../components/HotelRecommendationGrid.vue'
import { submitSetup } from '../services/api'
import type {
  AccommodationMode,
  HotelRecommendationCard,
  HotelValidation,
  RecommendationStatus,
  SetupResult,
} from '../types/trip'
import { clearAccommodationState, saveAccommodationState } from '../utils/accommodation'

const router = useRouter()

const DISTRICTS = ['大安區', '信義區', '中山區', '松山區', '中正區', '萬華區', '士林區', '北投區', '內湖區', '南港區', '文山區', '大同區']
const budgetOptions = [
  { value: 'budget', label: '平價' },
  { value: 'mid', label: '中價' },
  { value: 'luxury', label: '高價' },
] as const
const modeOptions = [
  { value: 'booked', label: '有訂飯店', description: '檢查是否為合法旅宿' },
  { value: 'need_hotel', label: '尚未預訂', description: '依地區與預算推薦飯店' },
  { value: 'no_stay', label: '不住宿', description: '直接進下一步填返回資訊' },
] as const

const mode = ref<AccommodationMode>('booked')
const hotelName = ref('')
const district = ref('')
const budgetTier = ref<'budget' | 'mid' | 'luxury'>('mid')
const validationResult = ref<HotelValidation | null>(null)
const hotelRecommendations = ref<HotelRecommendationCard[]>([])
const recommendationStatus = ref<RecommendationStatus | null>(null)
const loading = ref(false)
const errorText = ref('')

const submitLabel = computed(() => {
  if (mode.value === 'booked') return '檢查合法旅宿'
  if (mode.value === 'need_hotel') return hotelName.value ? '使用這間飯店' : '推薦飯店'
  return '不住宿，下一步'
})

const recommendationMessage = computed(() => {
  if (recommendationStatus.value === 'matched_preferences') return '以下清單符合你目前的地區與預算偏好。'
  if (recommendationStatus.value === 'relaxed_budget') return '符合地區的合法旅宿較少，已先放寬預算條件。'
  if (recommendationStatus.value === 'expanded_citywide') return '指定地區房源較少，已擴大到全台北幫你找。'
  if (recommendationStatus.value === 'expanded_citywide_and_budget') return '條件較嚴格，已擴大到全台北並放寬預算。'
  if (recommendationStatus.value === 'no_results') return '目前找不到符合條件的合法旅宿，請調整地區或預算再試一次。'
  return ''
})

function resetHotelRecommendations(clearSelectedHotel = false) {
  validationResult.value = null
  hotelRecommendations.value = []
  recommendationStatus.value = null
  if (clearSelectedHotel) {
    hotelName.value = ''
  }
}

function changeMode(nextMode: AccommodationMode) {
  mode.value = nextMode
  errorText.value = ''
  resetHotelRecommendations(true)
}

function updateBookedHotel(value: string) {
  hotelName.value = value
  resetHotelRecommendations(false)
}

function onBookedHotelInput(event: Event) {
  updateBookedHotel((event.target as HTMLInputElement).value)
}

function chooseHotel(name: string) {
  hotelName.value = name
  errorText.value = ''
}

async function handleSubmit() {
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (!sessionId) {
    router.push('/quiz')
    return
  }

  loading.value = true
  errorText.value = ''

  try {
    const payload =
      mode.value === 'booked'
        ? { accommodation: { mode: 'booked' as const, hotel_name: hotelName.value || undefined } }
        : mode.value === 'need_hotel'
          ? {
              accommodation: {
                mode: 'need_hotel' as const,
                hotel_name: hotelName.value || undefined,
                district: district.value || undefined,
                budget_tier: budgetTier.value,
              },
            }
          : { accommodation: { mode: 'no_stay' as const } }

    const result: SetupResult = await submitSetup(sessionId, payload)
    validationResult.value = result.hotel_validation
    hotelRecommendations.value = result.hotel_recommendations
    recommendationStatus.value = result.recommendation_status

    if (result.next_step === 'setup') {
      saveAccommodationState({
        mode: mode.value,
        hotelName: hotelName.value || null,
        displayName: result.hotel_validation?.matched_name || hotelName.value || null,
      })
      router.push('/setup')
      return
    }

    clearAccommodationState()
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    errorText.value = e?.response?.data?.detail ?? '設定失敗，請重試。'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.setup-container {
  min-height: 100vh;
  background: #f0f4ff;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 40px 20px;
}

.setup-card {
  background: white;
  border-radius: 20px;
  padding: 40px 32px;
  max-width: 560px;
  width: 100%;
  box-shadow: 0 8px 32px rgba(77, 104, 191, 0.12);
}

.title {
  font-size: 24px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 6px;
}

.subtitle {
  color: #64748b;
  font-size: 14px;
  margin-bottom: 24px;
}

.mode-grid {
  display: grid;
  gap: 10px;
  margin-bottom: 24px;
}

.mode-card {
  text-align: left;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1.5px solid #e2e8f0;
  background: white;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}

.mode-card:hover {
  border-color: #4d68bf;
  box-shadow: 0 4px 16px rgba(77, 104, 191, 0.12);
}

.mode-card.active {
  border-color: #4d68bf;
  background: #f8faff;
}

.mode-title {
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
}

.mode-desc {
  margin-top: 4px;
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
}

.section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 12px;
}

.text-input,
.select-input {
  width: 100%;
  padding: 10px 14px;
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  font-size: 14px;
  font-family: inherit;
  color: #334155;
  box-sizing: border-box;
}

.text-input:focus,
.select-input:focus {
  outline: none;
  border-color: #4d68bf;
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.radio-group.horizontal {
  flex-direction: row;
  gap: 20px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #475569;
  cursor: pointer;
}

.warning-box,
.info-box,
.selection-banner {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
}

.warning-box {
  background: #fffbeb;
  color: #92400e;
}

.warning-title {
  font-weight: 700;
}

.info-box,
.selection-banner {
  background: #eff6ff;
  color: #1d4ed8;
}

.selection-banner {
  font-weight: 600;
}

.result-block {
  margin-top: 14px;
}

.result-label {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 700;
}

.error {
  color: #ef4444;
  font-size: 14px;
  margin-bottom: 12px;
  text-align: center;
}

.submit-btn {
  width: 100%;
  padding: 14px;
  background: #4d68bf;
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 16px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.submit-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.submit-btn:not(:disabled):hover {
  background: #3d55a0;
}
</style>
