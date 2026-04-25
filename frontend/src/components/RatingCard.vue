<template>
  <div class="rating-card">
    <h2 class="venue-name">{{ venue.name }}</h2>
    <div class="photo-placeholder"></div>

    <p class="rating-label">你覺得這裡怎麼樣？</p>
    <div class="stars">
      <button
        v-for="n in 5"
        :key="n"
        class="star-btn"
        :class="{ filled: n <= selectedStars }"
        @click="selectedStars = n"
      >★</button>
    </div>

    <div class="tags">
      <button
        v-for="tag in QUICK_TAGS"
        :key="tag"
        class="tag-btn"
        :class="{ selected: selectedTags.includes(tag) }"
        @click="toggleTag(tag)"
      >
        {{ tag }}
      </button>
    </div>

    <button class="submit-btn" :disabled="selectedStars === 0 || loading" @click="submitRating">
      {{ loading ? '提交中…' : '繼續探索' }}
    </button>
    <div v-if="errorText" class="error">{{ errorText }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { submitRating as apiSubmitRating } from '../services/api'
import type { RateResult } from '../types/trip'

const props = defineProps<{
  venue: { venue_id: string | number; name: string }
}>()

const emit = defineEmits<{
  rated: [result: RateResult]
}>()

const QUICK_TAGS = ['食物很好吃', '人太多了', '值得再來', '服務很好', '環境很棒']

const selectedStars = ref(0)
const selectedTags = ref<string[]>([])
const loading = ref(false)
const errorText = ref('')

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
    emit('rated', result)
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
  background: white;
  border-radius: 16px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.venue-name {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
  text-align: center;
}

.photo-placeholder {
  width: 100%;
  height: 160px;
  background: #f1f5f9;
  border-radius: 12px;
}

.rating-label {
  font-size: 15px;
  color: #475569;
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
  border-color: #4d68bf;
  background: #4d68bf;
  color: white;
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

.error {
  color: #ef4444;
  font-size: 13px;
  text-align: center;
}
</style>
