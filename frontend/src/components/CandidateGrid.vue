<template>
  <div class="candidate-grid">
    <div class="grid">
      <button
        v-for="card in candidates"
        :key="card.venue_id"
        class="candidate-card"
        type="button"
        @click="$emit('select', card.venue_id)"
      >
        <div class="card-header">
          <span class="category-badge" :class="card.category">
            {{ locale.trip.categories[card.category as keyof typeof locale.trip.categories] ?? card.category }}
          </span>
          <span class="distance">{{ locale.common.minutes(card.distance_min) }}</span>
        </div>
        <h3 class="venue-name">{{ cardName(card) }}</h3>
        <p class="address">{{ card.address || locale.common.defaultAddress }}</p>
        <div v-if="card.rating" class="rating">★ {{ card.rating.toFixed(1) }}</div>
        <p class="why">{{ card.why_recommended }}</p>
      </button>
    </div>

    <button class="none-btn" type="button" @click="$emit('demand')">
      {{ locale.trip.demand.none }}
    </button>

    <details v-if="rainFiltered && rainFiltered.length > 0" class="rain-section">
      <summary class="rain-section-summary">
        <span class="rain-icon" aria-hidden="true">🌧️</span>
        <span class="rain-section-title">{{ locale.trip.rain.section }}</span>
        <span class="rain-section-hint">{{ locale.trip.rain.hint }}</span>
      </summary>
      <div class="rain-grid">
        <div
          v-for="card in rainFiltered"
          :key="card.venue_id"
          class="rain-card"
        >
          <div class="card-header">
            <span class="category-badge" :class="card.category">
              {{ locale.trip.categories[card.category as keyof typeof locale.trip.categories] ?? card.category }}
            </span>
            <span v-if="card.rain_note" class="rain-badge">{{ card.rain_note }}</span>
            <span v-else class="rain-badge">{{ locale.trip.rain.badge }}</span>
          </div>
          <h3 class="venue-name rain-venue-name">{{ cardName(card) }}</h3>
          <p class="address">{{ card.address || locale.common.defaultAddress }}</p>
          <div v-if="card.rating" class="rating rain-rating">★ {{ card.rating.toFixed(1) }}</div>
        </div>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import type { CandidateCard } from '../types/trip'
import { useLocale } from '../composables/useLocale'

defineProps<{
  candidates: CandidateCard[]
  rainFiltered?: CandidateCard[]
}>()

defineEmits<{
  select: [venueId: string | number]
  demand: []
}>()

const { lang, locale } = useLocale()

function cardName(card: { name: string; name_en?: string | null }) {
  return (lang.value === 'en' && card.name_en) ? card.name_en : card.name
}
</script>

<style scoped>
.candidate-grid {
  width: 100%;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}

@media (max-width: 767px) {
  .grid {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .candidate-card {
    padding: 12px;
  }

  .venue-name {
    font-size: 15px;
  }

  .none-btn {
    min-height: 48px;
    font-size: 14px;
  }
}

.candidate-card {
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1.5px solid #e2e8f0;
  border-radius: 14px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
  width: 100%;
}

.candidate-card:hover {
  border-color: #3b82f6;
  box-shadow: 0 10px 24px rgba(59, 130, 246, 0.16);
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

.category-badge.go_home {
  background: #fee2e2;
  color: #dc2626;
}

.distance {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
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
  margin-bottom: 8px;
}

.rating {
  font-size: 12px;
  color: #f59e0b;
  margin-bottom: 8px;
}

.why {
  font-size: 13px;
  color: #475569;
  line-height: 1.4;
}

.none-btn {
  width: 100%;
  padding: 12px;
  background: #f8fafc;
  border: 1.5px dashed #94a3b8;
  border-radius: 12px;
  color: #64748b;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
}

.none-btn:hover {
  border-color: #3b82f6;
  color: #1d4ed8;
  background: #eff6ff;
}

/* ── Rain-filtered section ── */

.rain-section {
  margin-top: 20px;
  border-top: 1.5px dashed #bfdbfe;
  padding-top: 8px;
}

.rain-section-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 8px 4px 12px;
  cursor: pointer;
  list-style: none;
  font-weight: 600;
  color: #1d4ed8;
}

.rain-section-summary::-webkit-details-marker {
  display: none;
}

.rain-icon {
  font-size: 16px;
  line-height: 1;
}

.rain-section-title {
  font-size: 12px;
  font-weight: 600;
  color: #3b82f6;
  letter-spacing: 0.01em;
}

.rain-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

@media (max-width: 480px) {
  .rain-grid {
    grid-template-columns: 1fr;
  }
}

.rain-card {
  background: linear-gradient(180deg, #f0f9ff 0%, #e0f2fe 100%);
  border: 1.5px solid #bfdbfe;
  border-radius: 14px;
  padding: 12px 14px;
  text-align: left;
  opacity: 0.62;
  cursor: default;
  position: relative;
}

.rain-venue-name {
  color: #475569;
}

.rain-badge {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 5px;
  background: #dbeafe;
  color: #1d4ed8;
  font-weight: 600;
  max-width: 12rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rain-rating {
  color: #93c5fd;
}

</style>
