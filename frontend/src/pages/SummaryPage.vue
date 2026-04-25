<template>
  <div class="summary-container">
    <div v-if="loading" class="loading">
      <p>載入旅程總結中…</p>
    </div>

    <div v-else-if="summary" class="summary-content">
      <!-- Mascot farewell -->
      <div class="mascot-section">
        <img
          :src="`/images/mascot_${summary.mascot}.svg`"
          :alt="summary.travel_gene"
          class="mascot-img"
          @error="onMascotImgError"
        />
        <div class="gene-info">
          <p class="gene-label">旅遊基因</p>
          <p class="gene-name">{{ summary.travel_gene }}</p>
        </div>
      </div>

      <p class="farewell">{{ summary.mascot_farewell }}</p>

      <!-- Stats -->
      <div class="stats-row">
        <div class="stat-card">
          <span class="stat-value">{{ summary.total_stops }}</span>
          <span class="stat-label">個景點</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ formatTime(summary.total_elapsed_min) }}</span>
          <span class="stat-label">旅遊時間</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ (summary.total_distance_m / 1000).toFixed(1) }}</span>
          <span class="stat-label">公里</span>
        </div>
      </div>

      <!-- Timeline -->
      <h3 class="timeline-title">今日足跡</h3>
      <div class="timeline">
        <div v-for="stop in summary.stops" :key="stop.stop_number" class="stop-item">
          <div class="stop-num">{{ stop.stop_number }}</div>
          <div class="stop-info">
            <div class="stop-header">
              <h4 class="stop-name">{{ stop.venue_name }}</h4>
              <span class="stop-time">{{ formatArrivalTime(stop.arrived_at) }}</span>
            </div>
            <div class="stop-stars">
              <span v-for="n in 5" :key="n" :class="n <= stop.star_rating ? 'star filled' : 'star'">★</span>
            </div>
            <div class="stop-tags" v-if="stop.tags.length">
              <span v-for="tag in stop.tags" :key="tag" class="tag-chip">{{ tag }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Share button -->
      <button class="share-btn" @click="shareJourney">分享我的旅程</button>
    </div>

    <div v-else class="error-state">
      <p>無法載入旅程總結。</p>
      <button class="retry-btn" @click="loadSummary">重試</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSummary } from '../services/api'
import type { JourneySummary } from '../types/trip'

const loading = ref(true)
const summary = ref<JourneySummary | null>(null)

onMounted(loadSummary)

async function loadSummary() {
  const sessionId = localStorage.getItem('chitogo_session_id')
  if (!sessionId) return

  loading.value = true
  try {
    summary.value = await getSummary(sessionId)
  } catch {
    summary.value = null
  } finally {
    loading.value = false
  }
}

function formatTime(minutes: number): string {
  if (minutes < 60) return `${minutes} 分`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m > 0 ? `${h} 時 ${m} 分` : `${h} 小時`
}

function formatArrivalTime(isoStr: string): string {
  try {
    const d = new Date(isoStr)
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return ''
  }
}

function onMascotImgError(e: Event) {
  (e.target as HTMLImageElement).style.display = 'none'
}

async function shareJourney() {
  const s = summary.value
  if (!s) return
  const text = `我今天在台北用 ChitoGo 探索了 ${s.total_stops} 個景點！旅遊基因：${s.travel_gene}，走了 ${(s.total_distance_m / 1000).toFixed(1)} 公里 🗺️`
  if (navigator.share) {
    await navigator.share({ text })
  } else {
    await navigator.clipboard.writeText(text)
    alert('已複製到剪貼簿！')
  }
}
</script>

<style scoped>
.summary-container {
  min-height: 100vh;
  background: #f0f4ff;
  padding: 24px 20px 48px;
  max-width: 520px;
  margin: 0 auto;
  box-sizing: border-box;
}

.loading, .error-state {
  text-align: center;
  padding: 60px 20px;
  color: #64748b;
}

.retry-btn {
  margin-top: 12px;
  padding: 10px 24px;
  background: #4d68bf;
  color: white;
  border: none;
  border-radius: 10px;
  font-family: inherit;
  font-size: 14px;
  cursor: pointer;
}

.mascot-section {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  background: white;
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(77, 104, 191, 0.08);
}

.mascot-img {
  width: 80px;
  height: 80px;
  object-fit: contain;
}

.gene-label {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 2px;
}

.gene-name {
  font-size: 22px;
  font-weight: 700;
  color: #4d68bf;
}

.farewell {
  background: white;
  border-radius: 16px;
  padding: 20px;
  font-size: 15px;
  color: #334155;
  line-height: 1.7;
  margin-bottom: 16px;
  box-shadow: 0 2px 12px rgba(77, 104, 191, 0.08);
}

.stats-row {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.stat-card {
  flex: 1;
  background: white;
  border-radius: 14px;
  padding: 16px 12px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(77, 104, 191, 0.08);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: #4d68bf;
}

.stat-label {
  font-size: 12px;
  color: #94a3b8;
}

.timeline-title {
  font-size: 17px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 12px;
}

.timeline {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 24px;
}

.stop-item {
  display: flex;
  gap: 14px;
  background: white;
  border-radius: 14px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(77, 104, 191, 0.08);
}

.stop-num {
  width: 28px;
  height: 28px;
  background: #4d68bf;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

.stop-info {
  flex: 1;
}

.stop-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}

.stop-name {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
}

.stop-time {
  font-size: 12px;
  color: #94a3b8;
}

.stop-stars {
  margin-bottom: 6px;
}

.star {
  font-size: 14px;
  color: #e2e8f0;
}

.star.filled {
  color: #f59e0b;
}

.stop-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-chip {
  background: #f1f5f9;
  color: #475569;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
}

.share-btn {
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

.share-btn:hover {
  background: #3d55a0;
}

@media (max-width: 767px) {
  .summary-container {
    padding: 16px 12px 80px;
    min-height: unset;
  }

  .mascot-section {
    padding: 14px;
  }

  .mascot-img {
    width: 60px;
    height: 60px;
  }

  .gene-name {
    font-size: 18px;
  }

  .stat-value {
    font-size: 18px;
  }

  .stop-item {
    padding: 12px;
  }

  .share-btn {
    min-height: 48px;
  }

  .retry-btn {
    min-height: 44px;
  }
}
</style>
