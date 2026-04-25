<template>
  <div class="candidate-grid">
    <div v-if="fallbackReason && partial" class="fallback-notice">
      ⚠ {{ fallbackReason }}
    </div>

    <div class="grid">
      <div
        v-for="card in candidates"
        :key="card.venue_id"
        class="candidate-card"
        @click="$emit('select', card.venue_id)"
      >
        <div class="card-header">
          <span class="category-badge" :class="card.category">
            {{ card.category === 'restaurant' ? '美食' : '景點' }}
          </span>
          <span class="distance">{{ card.distance_min }} 分鐘</span>
        </div>
        <h3 class="venue-name">{{ card.name }}</h3>
        <p class="address">{{ card.address || '台北市' }}</p>
        <div class="rating" v-if="card.rating">★ {{ card.rating.toFixed(1) }}</div>
        <p class="why">{{ card.why_recommended }}</p>
      </div>
    </div>

    <button class="none-btn" @click="$emit('demand')">
      沒有想去的？告訴我你想找什麼
    </button>
  </div>
</template>

<script setup lang="ts">
import type { CandidateCard } from '../types/trip'

defineProps<{
  candidates: CandidateCard[]
  partial?: boolean
  fallbackReason?: string | null
}>()

defineEmits<{
  select: [venueId: string | number]
  demand: []
}>()
</script>

<style scoped>
.candidate-grid {
  width: 100%;
}

.fallback-notice {
  background: #fef9c3;
  color: #92400e;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 13px;
  margin-bottom: 14px;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}

@media (max-width: 480px) {
  .grid {
    grid-template-columns: 1fr;
  }
}

.candidate-card {
  background: white;
  border: 1.5px solid #e2e8f0;
  border-radius: 14px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.candidate-card:hover {
  border-color: #4d68bf;
  box-shadow: 0 4px 16px rgba(77, 104, 191, 0.15);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.category-badge {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  font-weight: 600;
}

.category-badge.restaurant {
  background: #fef3c7;
  color: #d97706;
}

.category-badge.attraction {
  background: #e0f2fe;
  color: #0369a1;
}

.distance {
  font-size: 12px;
  color: #64748b;
}

.venue-name {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 4px;
}

.address {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 4px;
}

.rating {
  font-size: 12px;
  color: #f59e0b;
  margin-bottom: 4px;
}

.why {
  font-size: 13px;
  color: #475569;
  line-height: 1.4;
}

.none-btn {
  width: 100%;
  padding: 12px;
  background: transparent;
  border: 1.5px dashed #94a3b8;
  border-radius: 12px;
  color: #64748b;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
}

.none-btn:hover {
  border-color: #4d68bf;
  color: #4d68bf;
  background: #f0f4ff;
}
</style>
