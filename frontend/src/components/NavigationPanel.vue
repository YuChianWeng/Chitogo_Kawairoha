<template>
  <div class="nav-panel">
    <div class="venue-info">
      <h2 class="venue-name">{{ venue.name }}</h2>
      <p class="venue-address">{{ venue.address || '台北市' }}</p>
      <p class="travel-time">預計 {{ navigation.estimated_travel_min }} 分鐘到達</p>
    </div>

    <p class="encouragement">{{ encouragement }}</p>

    <div class="map-buttons">
      <a :href="navigation.google_maps_url" target="_blank" class="map-btn google">
        開啟 Google Maps
      </a>
      <a :href="navigation.apple_maps_url" class="map-btn apple">
        開啟 Apple Maps
      </a>
    </div>

    <button class="arrived-btn" @click="$emit('arrived')">我到了！</button>
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
  background: white;
  border-radius: 16px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
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
  margin-bottom: 4px;
}

.travel-time {
  font-size: 14px;
  color: #4d68bf;
  font-weight: 500;
}

.encouragement {
  background: #f0f4ff;
  border-left: 3px solid #4d68bf;
  padding: 12px 16px;
  border-radius: 8px;
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
  background: #1d1d1f;
  color: white;
}

.arrived-btn {
  padding: 14px;
  background: #10b981;
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
  background: #059669;
}
</style>
