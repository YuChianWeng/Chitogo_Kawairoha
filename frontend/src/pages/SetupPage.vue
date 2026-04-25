<template>
  <div class="setup-container">
    <div class="setup-card">
      <h1 class="title">返回設定</h1>
      <p class="subtitle">最後補上今天的返回安排，就能開始探索</p>

      <div v-if="accommodationSummary" class="summary-box">
        <div class="summary-label">住宿狀態</div>
        <div class="summary-value">{{ accommodationSummary }}</div>
      </div>

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
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { submitSetup } from '../services/api'
import type { SetupResult } from '../types/trip'
import { readAccommodationState } from '../utils/accommodation'

const router = useRouter()

const returnTime = ref('')
const returnDestination = ref('')
const loading = ref(false)
const errorText = ref('')

const storedAccommodation = readAccommodationState()
const accommodationSummary = computed(() => {
  if (!storedAccommodation) return ''
  if (storedAccommodation.mode === 'no_stay') return '本次不住宿'
  return storedAccommodation.displayName || storedAccommodation.hotelName || '已選擇住宿'
})

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
      return_time: returnTime.value || undefined,
      return_destination: returnDestination.value || undefined,
    })

    if (result.next_step === 'trip') {
      if (returnTime.value) {
        localStorage.setItem(`chitogo_return_time_${sessionId}`, returnTime.value)
      }
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
  margin-bottom: 24px;
}

.summary-box {
  margin-bottom: 24px;
  padding: 14px 16px;
  border-radius: 14px;
  background: #f8faff;
  border: 1px solid #dbeafe;
}

.summary-label {
  font-size: 12px;
  color: #64748b;
}

.summary-value {
  margin-top: 4px;
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
}

.section {
  margin-bottom: 28px;
  padding-bottom: 24px;
  border-bottom: 1px solid #f1f5f9;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 12px;
}

.text-input {
  width: 100%;
  padding: 10px 14px;
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  font-size: 14px;
  font-family: inherit;
  color: #334155;
  box-sizing: border-box;
}

.text-input:focus {
  outline: none;
  border-color: #4d68bf;
}

.mt-8 {
  margin-top: 8px;
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

@media (max-width: 767px) {
  .setup-container {
    padding: 16px 12px 80px;
    align-items: stretch;
  }

  .setup-card {
    padding: 24px 16px;
    border-radius: 16px;
  }

  .text-input {
    font-size: 16px; /* prevents iOS auto-zoom */
    min-height: 44px;
  }

  .submit-btn {
    min-height: 48px;
  }
}
</style>
