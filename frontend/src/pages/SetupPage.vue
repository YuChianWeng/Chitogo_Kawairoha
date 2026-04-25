<template>
  <div class="setup-container">
    <div class="setup-card">
      <h1 class="title">行程設定</h1>
      <p class="subtitle">讓我幫你規劃最適合的台北之旅</p>

      <!-- Accommodation -->
      <section class="section">
        <h3 class="section-title">住宿</h3>
        <div class="radio-group">
          <label class="radio-label">
            <input type="radio" v-model="booked" :value="true"> 已預訂飯店
          </label>
          <label class="radio-label">
            <input type="radio" v-model="booked" :value="false"> 尚未預訂
          </label>
        </div>

        <div v-if="booked" class="hotel-input-group">
          <input
            v-model="hotelName"
            class="text-input"
            placeholder="輸入飯店名稱"
            @input="validationResult = null"
          />
          <div v-if="validationResult" class="validation-badge" :class="validationResult.status">
            <template v-if="validationResult.status === 'validated' || validationResult.status === 'fuzzy_match'">
              <div class="validation-title">
                ✓ {{ validationResult.matched_name || hotelName }}（合法旅宿）
              </div>
              <div
                v-if="validationResult.district || validationResult.address"
                class="validation-meta"
              >
                {{ [validationResult.district, validationResult.address].filter(Boolean).join('｜') }}
              </div>
            </template>
            <template v-else-if="validationResult.status === 'not_found'">
              <div class="validation-title">⚠ 查無此合法旅宿</div>

              <div v-if="validationResult.alternatives.length" class="alternatives-block">
                <div class="alternatives-label">你是不是要找：</div>
                <div class="alternatives">
                  <button
                    v-for="alt in validationResult.alternatives"
                    :key="`alt-${alt.name}`"
                    class="alt-btn"
                    @click="chooseHotel(alt.name)"
                  >
                    {{ alt.name }}<span v-if="alt.district">（{{ alt.district }}）</span>
                  </button>
                </div>
              </div>

              <div v-if="validationResult.recommendations.length" class="alternatives-block">
                <div class="alternatives-label">可改訂以下合法旅宿：</div>
                <div class="alternatives">
                  <button
                    v-for="hotel in validationResult.recommendations"
                    :key="`recommend-${hotel.name}`"
                    class="alt-btn"
                    @click="chooseHotel(hotel.name)"
                  >
                    {{ hotel.name }}<span v-if="hotel.district">（{{ hotel.district }}）</span>
                  </button>
                </div>
              </div>
            </template>
          </div>
        </div>

        <div v-else class="not-booked-fields">
          <select v-model="district" class="select-input">
            <option value="">選擇偏好地區</option>
            <option v-for="d in DISTRICTS" :key="d" :value="d">{{ d }}</option>
          </select>
          <div class="radio-group horizontal">
            <label v-for="t in ['budget', 'mid', 'luxury']" :key="t" class="radio-label">
              <input type="radio" v-model="budgetTier" :value="t">
              {{ { budget: '平價', mid: '中價', luxury: '高價' }[t] }}
            </label>
          </div>
        </div>
      </section>

      <!-- Return time -->
      <section class="section">
        <h3 class="section-title">預計返回時間（選填）</h3>
        <input v-model="returnTime" type="time" class="text-input" />
        <input
          v-model="returnDestination"
          class="text-input mt-8"
          placeholder="返回地點（如：飯店、台北車站）"
        />
      </section>

      <div v-if="errorText" class="error">{{ errorText }}</div>

      <button class="submit-btn" :disabled="loading" @click="handleSubmit">
        {{ loading ? '設定中…' : '開始探索' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { submitSetup } from '../services/api'
import type { SetupResult } from '../types/trip'

const router = useRouter()

const DISTRICTS = ['大安區', '信義區', '中山區', '松山區', '中正區', '萬華區', '士林區', '北投區', '內湖區', '南港區', '文山區', '大同區']

const booked = ref(false)
const hotelName = ref('')
const district = ref('')
const budgetTier = ref<'budget' | 'mid' | 'luxury'>('mid')
const returnTime = ref('')
const returnDestination = ref('')
const loading = ref(false)
const errorText = ref('')

interface ValidationResult {
  status: string
  matched_name: string | null
  district: string | null
  address: string | null
  alternatives: Array<{ name: string; district: string | null; address: string | null; confidence: number }>
  recommendations: Array<{ name: string; district: string | null; address: string | null }>
}
const validationResult = ref<ValidationResult | null>(null)

function chooseHotel(name: string) {
  hotelName.value = name
  validationResult.value = null
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
    const result: SetupResult = await submitSetup(sessionId, {
      accommodation: booked.value
        ? { booked: true, hotel_name: hotelName.value || undefined }
        : { booked: false, district: district.value || undefined, budget_tier: budgetTier.value },
      return_time: returnTime.value || undefined,
      return_destination: returnDestination.value || undefined,
    })

    if (result.hotel_validation) {
      validationResult.value = {
        status: result.accommodation_status,
        matched_name: result.hotel_validation.matched_name,
        district: result.hotel_validation.district,
        address: result.hotel_validation.address,
        alternatives: result.hotel_validation.alternatives,
        recommendations: result.hotel_validation.recommendations,
      }
    } else {
      validationResult.value = null
    }

    if (result.setup_complete) {
      router.push('/trip')
    }
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
  max-width: 520px;
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
  margin-bottom: 28px;
}

.section {
  margin-bottom: 28px;
  padding-bottom: 24px;
  border-bottom: 1px solid #f1f5f9;
}

.section:last-of-type {
  border-bottom: none;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 12px;
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.radio-group.horizontal {
  flex-direction: row;
  gap: 20px;
}

.radio-label, .checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #475569;
  cursor: pointer;
}

.text-input, .select-input {
  width: 100%;
  padding: 10px 14px;
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  font-size: 14px;
  font-family: inherit;
  color: #334155;
  margin-top: 8px;
  box-sizing: border-box;
}

.text-input:focus, .select-input:focus {
  outline: none;
  border-color: #4d68bf;
}

.mt-8 {
  margin-top: 8px;
}

.hotel-input-group {
  margin-top: 8px;
}

.not-booked-fields {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.validation-badge {
  margin-top: 8px;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
}

.validation-title {
  font-weight: 600;
}

.validation-meta {
  margin-top: 4px;
  font-size: 12px;
  opacity: 0.85;
}

.validation-badge.validated,
.validation-badge.fuzzy_match {
  background: #dcfce7;
  color: #15803d;
}

.validation-badge.not_found {
  background: #fef9c3;
  color: #92400e;
}

.alternatives {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.alternatives-block + .alternatives-block {
  margin-top: 10px;
}

.alternatives-label {
  margin-top: 8px;
  font-size: 12px;
  font-weight: 600;
}

.alt-btn {
  padding: 4px 10px;
  border: 1px solid #d97706;
  border-radius: 6px;
  background: white;
  color: #92400e;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}

.checkbox-group {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.slider-group {
  margin-top: 8px;
}

.slider-group label {
  font-size: 13px;
  color: #475569;
  display: block;
  margin-bottom: 6px;
}

.slider {
  width: 100%;
  accent-color: #4d68bf;
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
