<template>
  <div class="map-panel">
    <div ref="mapEl" class="map-container"></div>
    <div class="location-badge">目前位置：台北市信義區</div>
    <div v-if="!hasStops && !loading" class="map-hint">行程規劃完成後，景點將顯示於地圖上</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Itinerary, ChatCandidate } from '../types/itinerary'

const props = defineProps<{
  itinerary: Itinerary | null
  candidates: ChatCandidate[]
  loading?: boolean
}>()

const mapEl = ref<HTMLElement | null>(null)
let map: L.Map | null = null
let markers: L.Marker[] = []
let routeLine: L.Polyline | null = null

const TAIPEI: L.LatLngExpression = [25.0330, 121.5654]

const hasStops = computed(
  () => (props.itinerary?.stops ?? []).some(s => s.lat && s.lng)
)

onMounted(() => {
  if (!mapEl.value) return
  map = L.map(mapEl.value, { center: TAIPEI, zoom: 13 })
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(map)
  renderMarkers()
})

onBeforeUnmount(() => {
  map?.remove()
  map = null
})

watch(() => props.itinerary, renderMarkers, { deep: true })

function renderMarkers() {
  if (!map) return

  markers.forEach(m => m.remove())
  markers = []
  routeLine?.remove()
  routeLine = null

  const stops = (props.itinerary?.stops ?? []).filter(s => s.lat && s.lng)
  if (stops.length === 0) return

  const latlngs: L.LatLngExpression[] = []

  for (const [idx, stop] of stops.entries()) {
    const ll: L.LatLngExpression = [stop.lat!, stop.lng!]
    latlngs.push(ll)

    const icon = L.divIcon({
      className: '',
      html: `<div class="stop-pin">${idx + 1}</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    })

    const popup = [
      `<strong>${stop.venue_name}</strong>`,
      stop.arrival_time ? `抵達：${stop.arrival_time}` : '',
      stop.category ? `類型：${stop.category}` : '',
      stop.visit_duration_min ? `停留：${stop.visit_duration_min} 分鐘` : '',
    ].filter(Boolean).join('<br>')

    markers.push(L.marker(ll, { icon }).bindPopup(popup).addTo(map!))
  }

  if (latlngs.length > 1) {
    routeLine = L.polyline(latlngs, { color: '#4d68bf', weight: 3, dashArray: '6 4' }).addTo(map)
  }

  map.fitBounds(L.latLngBounds(latlngs as L.LatLng[]), { padding: [48, 48], maxZoom: 15 })
}
</script>

<style scoped>
.map-panel {
  flex: 1;
  position: relative;
  overflow: hidden;
  min-width: 0;
}

.map-container {
  width: 100%;
  height: 100%;
}

.location-badge {
  position: absolute;
  top: 50px;
  right: 20px;
  background: rgba(77, 104, 191, 0.85);
  color: #fff;
  padding: 8px 18px;
  border-radius: 20px;
  font-size: 13px;
  z-index: 500;
  pointer-events: none;
  backdrop-filter: blur(4px);
}

.map-hint {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(255, 255, 255, 0.9);
  color: #64748b;
  font-size: 12px;
  padding: 6px 14px;
  border-radius: 12px;
  z-index: 500;
  pointer-events: none;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
</style>

<style>
.stop-pin {
  width: 28px;
  height: 28px;
  background: #4d68bf;
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  border: 2px solid #fff;
  box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}
</style>
