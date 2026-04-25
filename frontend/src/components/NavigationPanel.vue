<template>
  <div class="nav-panel">
    <div class="panel-header">
      <div>
        <p class="panel-kicker">前往中</p>
        <div class="mode-pill">{{ transportLabel }}</div>
      </div>
      <div class="eta-block">
        <p class="travel-time">預計 {{ travelTimeText }} 到達</p>
        <p v-if="distanceText" class="travel-distance">{{ distanceText }}</p>
      </div>
    </div>

    <div class="venue-info">
      <h2 class="venue-name">{{ venue.name }}</h2>
      <p class="venue-address">{{ venue.address || '台北市' }}</p>
    </div>

    <p class="encouragement">{{ encouragement }}</p>

    <div v-if="navigationStatus === 'loading'" class="status-card">
      右側地圖正在計算最佳路線與步驟…
    </div>

    <div v-else-if="navigationStatus === 'error'" class="status-card status-card--error">
      {{ navigationError || '目前無法取得導航路線，請改用外部地圖。' }}
    </div>

    <div v-else-if="navigationSteps.length" class="steps-card">
      <p class="steps-title">導航步驟</p>
      <ol class="steps-list">
        <li v-for="(step, index) in navigationSteps" :key="`${index}-${step.instruction}`" class="step-item">
          <span class="step-index">{{ index + 1 }}</span>
          <div class="step-content">
            <p class="step-instruction">{{ step.instruction }}</p>
            <p class="step-meta">
              <span v-if="step.lineName">{{ step.lineName }}</span>
              <span v-if="step.durationText">{{ step.durationText }}</span>
              <span v-if="step.distanceText">{{ step.distanceText }}</span>
            </p>
          </div>
        </li>
      </ol>
    </div>

    <div class="map-buttons">
      <a :href="navigation.google_maps_url" target="_blank" rel="noreferrer" class="map-btn google">
        外跳 Google Maps
      </a>
      <a :href="navigation.apple_maps_url" target="_blank" rel="noreferrer" class="map-btn apple">
        外跳 Apple Maps
      </a>
    </div>

    <button class="arrived-btn" type="button" @click="$emit('arrived')">我到了，繼續</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useMapState } from '../composables/useMapState'
import type { SelectResult, TransportMode } from '../types/trip'

const props = defineProps<{
  venue: SelectResult['venue']
  navigation: SelectResult['navigation']
  encouragement: string
}>()

defineEmits<{
  arrived: []
}>()

const {
  navigationStatus,
  routeSummary,
  navigationSteps,
  navigationError,
} = useMapState()

const transportLabel = computed(() => transportModeLabel(props.navigation.transport_mode))

const travelTimeText = computed(() => (
  routeSummary.value?.durationText ?? `${props.navigation.estimated_travel_min} 分鐘`
))

const distanceText = computed(() => routeSummary.value?.distanceText ?? null)

function transportModeLabel(mode: TransportMode) {
  if (mode === 'walk') return '步行'
  if (mode === 'drive') return '開車'
  return '大眾運輸'
}
</script>

<style scoped>
.nav-panel {
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1px solid #dbeafe;
  border-radius: 20px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.panel-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #2563eb;
  font-weight: 700;
  margin-bottom: 8px;
}

.mode-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
}

.eta-block {
  text-align: right;
}

.venue-name {
  font-size: 22px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 4px;
}

.venue-address {
  font-size: 14px;
  color: #64748b;
}

.travel-time {
  font-size: 13px;
  color: #1d4ed8;
  font-weight: 700;
}

.travel-distance {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.encouragement {
  background: #eff6ff;
  border-left: 3px solid #3b82f6;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  color: #334155;
  line-height: 1.6;
}

.status-card,
.steps-card {
  border-radius: 16px;
  padding: 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #334155;
  font-size: 14px;
}

.status-card--error {
  background: #fff1f2;
  border-color: #fecdd3;
  color: #be123c;
}

.steps-title {
  font-size: 13px;
  font-weight: 700;
  color: #1e40af;
  margin-bottom: 12px;
}

.steps-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.step-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.step-index {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #2563eb;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-content {
  min-width: 0;
}

.step-instruction {
  color: #1e293b;
  line-height: 1.5;
}

.step-meta {
  margin-top: 4px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  color: #64748b;
  font-size: 12px;
}

.map-buttons {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.map-btn {
  display: block;
  padding: 13px;
  text-align: center;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  text-decoration: none;
  transition: opacity 0.2s;
}

.map-btn:hover {
  opacity: 0.85;
}

.map-btn.google {
  background: #4285f4;
  color: white;
}

.map-btn.apple {
  background: #0f172a;
  color: white;
}

.arrived-btn {
  padding: 14px;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 16px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.arrived-btn:hover {
  filter: brightness(0.96);
}
</style>
