<template>
  <div class="container">
    <h1>Taipei Itinerary Planner</h1>

    <form @submit.prevent="submit" class="form">
      <div class="field">
        <label>District</label>
        <select v-model="form.district">
          <option v-for="d in DISTRICTS" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>

      <div class="field">
        <label>Start Time</label>
        <input type="time" v-model="form.start_time" />
      </div>

      <div class="field">
        <label>End Time</label>
        <input type="time" v-model="form.end_time" />
      </div>

      <div class="field">
        <label>Interests (select multiple)</label>
        <div class="checkbox-group">
          <label v-for="interest in INTERESTS" :key="interest">
            <input
              type="checkbox"
              :value="interest"
              v-model="form.interests"
            />
            {{ interest }}
          </label>
        </div>
      </div>

      <div class="field">
        <label>Budget</label>
        <select v-model="form.budget">
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
      </div>

      <div class="field">
        <label>Companion</label>
        <select v-model="form.companion">
          <option value="solo">Solo</option>
          <option value="couple">Couple</option>
          <option value="family">Family</option>
          <option value="friends">Friends</option>
        </select>
      </div>

      <div class="field">
        <label>Indoor Preference</label>
        <select v-model="form.indoor_pref">
          <option value="both">Both</option>
          <option value="indoor">Indoor only</option>
          <option value="outdoor">Outdoor only</option>
        </select>
      </div>

      <button type="submit" :disabled="loading">
        {{ loading ? 'Planning…' : 'Generate Itinerary' }}
      </button>
    </form>

    <div v-if="error" class="error">
      <strong>Error {{ error.code }}:</strong> {{ error.message }}
    </div>

    <div v-if="result" class="result">
      <h2>Generated Itinerary</h2>
      <pre>{{ JSON.stringify(result, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { generateItinerary } from '../services/api'
import type { ItineraryResponse, ApiError } from '../types/itinerary'

const DISTRICTS = [
  "Zhongzheng", "Da'an", "Zhongshan", "Xinyi", "Wanhua",
  "Songshan", "Neihu", "Shilin", "Beitou", "Wenshan",
  "Nangang", "Datong",
]

const INTERESTS = [
  'food', 'culture', 'shopping', 'nature', 'nightlife',
  'art', 'history', 'cafe', 'sports', 'temple',
]

const form = reactive({
  district: "Da'an",
  start_time: '09:00',
  end_time: '17:00',
  interests: ['food', 'culture'] as string[],
  budget: 'medium' as 'low' | 'medium' | 'high',
  companion: 'solo' as 'solo' | 'couple' | 'family' | 'friends',
  indoor_pref: 'both' as 'indoor' | 'outdoor' | 'both',
})

const loading = ref(false)
const result = ref<ItineraryResponse | null>(null)
const error = ref<ApiError | null>(null)

async function submit() {
  loading.value = true
  result.value = null
  error.value = null
  try {
    result.value = await generateItinerary({ ...form })
  } catch (err: unknown) {
    if (
      err &&
      typeof err === 'object' &&
      'response' in err &&
      err.response &&
      typeof err.response === 'object' &&
      'data' in err.response
    ) {
      error.value = (err.response as { data: ApiError }).data
    } else {
      error.value = { status: 'error', code: 'network_error', message: String(err) }
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.container {
  max-width: 800px;
  margin: 0 auto;
  padding: 2rem;
  font-family: system-ui, sans-serif;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 2rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.field label {
  font-weight: 600;
  font-size: 0.9rem;
}

.field select,
.field input[type='time'] {
  padding: 0.4rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 1rem;
}

.checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.checkbox-group label {
  font-weight: normal;
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

button {
  padding: 0.6rem 1.2rem;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 1rem;
  cursor: pointer;
  align-self: flex-start;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error {
  background: #fee2e2;
  border: 1px solid #f87171;
  border-radius: 4px;
  padding: 1rem;
  margin-bottom: 1rem;
  color: #b91c1c;
}

.result pre {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 1rem;
  overflow-x: auto;
  font-size: 0.85rem;
  line-height: 1.5;
}
</style>
