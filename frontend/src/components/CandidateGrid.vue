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
        <!-- Top row: category badge + distance -->
        <div class="card-header">
          <span class="category-badge" :class="card.category">
            {{ card.category === 'restaurant' ? '美食' : card.category === 'go_home' ? '回程' : '景點' }}
          </span>
          <div class="card-header-right">
            <span v-if="isTrending(card)" class="trend-badge">🔥 熱門</span>
            <span class="distance">{{ card.distance_min }} 分鐘</span>
          </div>
        </div>

        <!-- Venue name -->
        <h3 class="venue-name">{{ card.name }}</h3>
        <p class="address">{{ card.address || '台北市' }}</p>

        <!-- Rating + social stats row -->
        <div class="stats-row">
          <span v-if="card.rating" class="stat rating">
            ★ {{ card.rating.toFixed(1) }}
          </span>
          <span v-if="card.mention_count && card.mention_count > 0" class="stat mentions">
            💬 {{ formatMentions(card.mention_count) }}
          </span>
          <span v-if="card.sentiment_score != null" class="stat sentiment" :class="sentimentClass(card.sentiment_score)">
            {{ sentimentLabel(card.sentiment_score) }}
          </span>
        </div>

        <!-- Vibe tags -->
        <div v-if="card.vibe_tags && card.vibe_tags.length > 0" class="vibe-tags">
          <span v-for="tag in card.vibe_tags.slice(0, 4)" :key="tag" class="vibe-tag">
            #{{ tag }}
          </span>
        </div>

        <!-- Why recommended -->
        <p class="why">{{ card.why_recommended }}</p>
      </button>
    </div>

    <button class="none-btn" type="button" @click="$emit('demand')">
      這些都還好，換一種條件幫我找
    </button>

    <details v-if="rainFiltered && rainFiltered.length > 0" class="rain-section">
      <summary class="rain-section-summary">
        <span class="rain-icon" aria-hidden="true">🌧️</span>
        <span class="rain-section-title">雨天備選</span>
        <span class="rain-section-hint">（因預報降雨，戶外點改列於此）</span>
      </summary>
      <div class="rain-grid">
        <div
          v-for="card in rainFiltered"
          :key="card.venue_id"
          class="rain-card"
        >
          <div class="card-header">
            <span class="category-badge" :class="card.category">
              {{ card.category === 'restaurant' ? '美食' : '景點' }}
            </span>
            <span v-if="card.rain_note" class="rain-badge">{{ card.rain_note }}</span>
            <span v-else class="rain-badge">🌧 戶外</span>
          </div>
          <h3 class="venue-name rain-venue-name">{{ card.name }}</h3>
          <p class="address">{{ card.address || '台北市' }}</p>
          <div class="stats-row">
            <span v-if="card.rating" class="stat rating rain-rating">★ {{ card.rating.toFixed(1) }}</span>
            <span v-if="card.mention_count && card.mention_count > 0" class="stat mentions">
              💬 {{ formatMentions(card.mention_count) }}
            </span>
          </div>
          <div v-if="card.vibe_tags && card.vibe_tags.length > 0" class="vibe-tags">
            <span v-for="tag in card.vibe_tags.slice(0, 3)" :key="tag" class="vibe-tag">
              #{{ tag }}
            </span>
          </div>
        </div>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import type { CandidateCard } from '../types/trip'

defineProps<{
  candidates: CandidateCard[]
  rainFiltered?: CandidateCard[]
}>()

defineEmits<{
  select: [venueId: string | number]
  demand: []
}>()

function formatMentions(count: number): string {
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k 則討論`
  return `${count} 則討論`
}

function isTrending(card: CandidateCard): boolean {
  return (card.trend_score != null && card.trend_score > 0.6) ||
    (card.mention_count != null && card.mention_count >= 50)
}

function sentimentClass(score: number): string {
  if (score >= 0.7) return 'sentiment-positive'
  if (score >= 0.4) return 'sentiment-neutral'
  return 'sentiment-negative'
}

function sentimentLabel(score: number): string {
  if (score >= 0.7) return '好評'
  if (score >= 0.4) return '普通'
  return '評價不一'
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

.card-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
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

.trend-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 5px;
  background: #fff7ed;
  color: #c2410c;
  font-weight: 600;
  white-space: nowrap;
}

.distance {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
  white-space: nowrap;
}

.venue-name {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 2px;
}

.address {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 8px;
}

/* Stats row */
.stats-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.stat {
  font-size: 12px;
  font-weight: 500;
}

.rating {
  color: #f59e0b;
}

.mentions {
  color: #6366f1;
}

.sentiment {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.sentiment-positive {
  background: #dcfce7;
  color: #15803d;
}

.sentiment-neutral {
  background: #f1f5f9;
  color: #64748b;
}

.sentiment-negative {
  background: #fee2e2;
  color: #b91c1c;
}

/* Vibe tags */
.vibe-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.vibe-tag {
  font-size: 11px;
  color: #6366f1;
  background: #eef2ff;
  padding: 2px 7px;
  border-radius: 4px;
  font-weight: 500;
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

/* Rain section */
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
