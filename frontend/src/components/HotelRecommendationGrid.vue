<template>
  <div v-if="cards.length" class="hotel-grid">
    <button
      v-for="card in cards"
      :key="card.license_no || card.place_id || card.name"
      type="button"
      class="hotel-card"
      :class="{ selected: selectedName === card.name }"
      @click="$emit('select', card.name)"
    >
      <div class="hotel-card-header">
        <div>
          <h4 class="hotel-name">{{ card.name }}</h4>
          <p class="hotel-district">{{ card.district || '台北市' }}</p>
        </div>
        <div class="hotel-pills">
          <span v-if="card.rating !== null" class="pill rating">★ {{ card.rating.toFixed(1) }}</span>
          <span v-if="budgetLabel(card.budget_level)" class="pill budget">{{ budgetLabel(card.budget_level) }}</span>
        </div>
      </div>

      <p class="hotel-address">{{ card.address || '地址待補' }}</p>
      <p v-if="card.confidence !== null" class="hotel-confidence">
        相似度 {{ Math.round(card.confidence * 100) }}%
      </p>
    </button>
  </div>
</template>

<script setup lang="ts">
import type { HotelRecommendationCard } from '../types/trip'

defineProps<{
  cards: HotelRecommendationCard[]
  selectedName?: string
}>()

defineEmits<{
  select: [name: string]
}>()

function budgetLabel(value: string | null) {
  if (value === 'PRICE_LEVEL_FREE' || value === 'INEXPENSIVE') return '平價'
  if (value === 'MODERATE') return '中價'
  if (value === 'EXPENSIVE' || value === 'VERY_EXPENSIVE') return '高價'
  return ''
}
</script>

<style scoped>
.hotel-grid {
  display: grid;
  gap: 12px;
}

.hotel-card {
  width: 100%;
  text-align: left;
  border: 1.5px solid #e2e8f0;
  border-radius: 14px;
  background: white;
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}

.hotel-card:hover {
  border-color: #4d68bf;
  box-shadow: 0 6px 20px rgba(77, 104, 191, 0.14);
  transform: translateY(-1px);
}

.hotel-card.selected {
  border-color: #4d68bf;
  background: #f8faff;
  box-shadow: 0 6px 20px rgba(77, 104, 191, 0.16);
}

.hotel-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.hotel-name {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
}

.hotel-district {
  margin: 4px 0 0;
  font-size: 12px;
  color: #64748b;
}

.hotel-pills {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.pill {
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.pill.rating {
  background: #fff7ed;
  color: #c2410c;
}

.pill.budget {
  background: #eff6ff;
  color: #1d4ed8;
}

.hotel-address {
  margin: 10px 0 0;
  font-size: 13px;
  color: #475569;
  line-height: 1.5;
}

.hotel-confidence {
  margin: 10px 0 0;
  font-size: 12px;
  color: #92400e;
}
</style>
