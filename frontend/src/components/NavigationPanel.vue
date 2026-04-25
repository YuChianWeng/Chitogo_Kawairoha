<template>
  <div class="nav-panel">
    <div class="panel-header">
      <p class="panel-kicker">前往中</p>
      <p class="travel-time">預計 {{ navigation.estimated_travel_min }} 分鐘到達</p>
    </div>

    <div class="venue-info">
      <h2 class="venue-name">{{ venue.name }}</h2>
      <p class="venue-address">{{ venue.address || '台北市' }}</p>
    </div>

    <p class="encouragement">{{ encouragement }}</p>

    <div class="map-buttons">
      <a :href="navigation.google_maps_url" target="_blank" rel="noreferrer" class="map-btn google">
        開啟 Google Maps
      </a>
      <a :href="navigation.apple_maps_url" target="_blank" rel="noreferrer" class="map-btn apple">
        開啟 Apple Maps
      </a>
    </div>

    <button class="arrived-btn" type="button" @click="$emit('arrived')">我到了，繼續</button>
  </div>
</template>

<script setup lang="ts">
import type { SelectResult } from '../types/trip'

defineProps<{
  venue: SelectResult['venue']
  navigation: SelectResult['navigation']
  encouragement: string
}>()

defineEmits<{
  arrived: []
}>()
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
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.panel-kicker {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #2563eb;
  font-weight: 700;
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

.encouragement {
  background: #eff6ff;
  border-left: 3px solid #3b82f6;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  color: #334155;
  line-height: 1.6;
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
