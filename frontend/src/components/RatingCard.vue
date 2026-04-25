<template>
  <div class="rating-card">
    <div class="rating-header">
      <p class="rating-kicker">這站感受</p>
      <h2 class="venue-name">{{ venue.name }}</h2>
      <p class="rating-label">用星等和幾個關鍵字告訴我你的感覺。</p>
    </div>

    <div class="stars">
      <button
        v-for="n in 5"
        :key="n"
        class="star-btn"
        :class="{ filled: n <= selectedStars }"
        type="button"
        @click="selectedStars = n"
      >★</button>
    </div>
    <p class="star-caption">{{ starCaption }}</p>

    <div class="tags">
      <button
        v-for="tag in QUICK_TAGS"
        :key="tag"
        class="tag-btn"
        :class="{ selected: selectedTags.includes(tag) }"
        type="button"
        @click="toggleTag(tag)"
      >
        {{ tag }}
      </button>
    </div>
    <p class="tag-hint">標籤可選填，不選也可以直接送出。</p>

    <button class="submit-btn" type="button" :disabled="selectedStars === 0 || loading" @click="submitRating">
      {{ loading ? '提交中…' : '繼續探索' }}
    </button>
    <div v-if="errorText" class="error">{{ errorText }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { submitRating as apiSubmitRating } from '../services/api'
import type { RateResult } from '../types/trip'

const props = defineProps<{
  venue: { venue_id: string | number; name: string }
}>()

const emit = defineEmits<{
  rated: [payload: { result: RateResult; stars: number; tags: string[] }]
}>()

const QUICK_TAGS = ['食物很好吃', '人太多了', '值得再來', '服務很好', '環境很棒']

const selectedStars = ref(0)
const selectedTags = ref<string[]>([])
const loading = ref(false)
const errorText = ref('')

const starCaption = computed(() => {
  if (selectedStars.value === 0) return '先選一個星等'
  if (selectedStars.value === 1) return '這站不太對味'
  if (selectedStars.value === 2) return '有點普通'
  if (selectedStars.value === 3) return '還不錯'
  if (selectedStars.value === 4) return '很喜歡'
  return '這站超對味'
})

function toggleTag(tag: string) {
  const idx = selectedTags.value.indexOf(tag)
  if (idx >= 0) {
    selectedTags.value.splice(idx, 1)
  } else {
    selectedTags.value.push(tag)
  }
}

async function submitRating() {
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (!sessionId || selectedStars.value === 0) return

  loading.value = true
  errorText.value = ''
  try {
    const result = await apiSubmitRating(sessionId, selectedStars.value, selectedTags.value)
    emit('rated', {
      result,
      stars: selectedStars.value,
      tags: [...selectedTags.value],
    })
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    errorText.value = e?.response?.data?.detail ?? '提交失敗，請重試。'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.rating-card {
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1px solid #dbeafe;
  border-radius: 20px;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.rating-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  text-align: center;
}

.rating-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #3b82f6;
  font-weight: 700;
}

.venue-name {
  font-size: 22px;
  font-weight: 700;
  color: #1e293b;
  text-align: center;
}

.rating-label {
  font-size: 15px;
  color: #475569;
  line-height: 1.5;
}

.stars {
  display: flex;
  gap: 8px;
}

.star-btn {
  background: none;
  border: none;
  font-size: 36px;
  color: #e2e8f0;
  cursor: pointer;
  padding: 0;
  line-height: 1;
  transition: color 0.1s;
}

.star-btn.filled {
  color: #f59e0b;
}

.star-btn:hover {
  color: #fbbf24;
}

.star-caption {
  font-size: 14px;
  color: #475569;
  font-weight: 600;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.tag-btn {
  padding: 6px 14px;
  border: 1.5px solid #e2e8f0;
  border-radius: 20px;
  background: white;
  color: #64748b;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
}

.tag-btn.selected {
  border-color: #2563eb;
  background: #2563eb;
  color: white;
}

.tag-hint {
  font-size: 12px;
  color: #94a3b8;
}

.submit-btn {
  width: 100%;
  padding: 14px;
  background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
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
  filter: brightness(0.96);
}

.error {
  color: #ef4444;
  font-size: 13px;
  text-align: center;
}
</style>
