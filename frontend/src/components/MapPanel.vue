<template>
  <div class="map-panel">
    <div ref="mapEl" class="map-container"></div>
    <div class="location-badge">{{ locationBadge }}</div>
    <div v-if="mapMessage" class="map-hint" :class="mapMessageClass">{{ mapMessage }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useMapState } from '../composables/useMapState'
import { loadGoogleMapsApi } from '../utils/googleMaps'

type GoogleMapsApi = any
type GoogleMapInstance = any
type GoogleMarker = any
type GoogleDirectionsService = any
type GoogleDirectionsRenderer = any
type GoogleDirectionsResult = any

const TAIPEI = { lat: 25.033, lng: 121.5654 }
const REROUTE_DISTANCE_M = 100

const mapEl = ref<HTMLElement | null>(null)
const isMapLoading = ref(true)
const mapLoadError = ref<string | null>(null)

const {
  mapMode,
  spotCandidates,
  currentLocation,
  activeNavigation,
  navigationStatus,
  navigationError,
  setNavigationLoading,
  setNavigationReady,
  setNavigationError,
} = useMapState()

let googleMaps: GoogleMapsApi | null = null
let map: GoogleMapInstance | null = null
let directionsService: GoogleDirectionsService | null = null
let directionsRenderer: GoogleDirectionsRenderer | null = null
let candidateMarkers: GoogleMarker[] = []
let currentMarker: GoogleMarker | null = null
let destinationMarker: GoogleMarker | null = null
let routeRequestId = 0
let lastRouteModeKey = ''
let lastRouteOrigin: { lat: number; lng: number } | null = null

const locationBadge = computed(() => (
  `目前位置：${currentLocation.value?.label ?? '等待定位'}`
))

const mapMessage = computed(() => {
  if (mapLoadError.value) return mapLoadError.value
  if (isMapLoading.value) return 'Google 地圖載入中…'
  if (mapMode.value === 'navigation') {
    if (navigationStatus.value === 'loading') return '正在計算右側導航路線…'
    if (navigationStatus.value === 'error') {
      return navigationError.value ?? '目前無法取得導航路線，請改用外部地圖。'
    }
    return ''
  }
  if (mapMode.value === 'idle') {
    return '行程規劃完成後，景點將顯示於地圖上'
  }
  return ''
})

const mapMessageClass = computed(() => (
  mapLoadError.value || navigationStatus.value === 'error' ? 'map-hint--error' : ''
))

onMounted(async () => {
  if (!mapEl.value) return

  try {
    isMapLoading.value = true
    googleMaps = await loadGoogleMapsApi()
    initializeMap()
    await syncMapScene()
  } catch (error) {
    mapLoadError.value = toMapErrorMessage(error)
    if (activeNavigation.value) {
      setNavigationError('右側 Google 地圖載入失敗，請先改用外部導航。')
    }
  } finally {
    isMapLoading.value = false
  }
})

onBeforeUnmount(() => {
  clearCandidateMarkers()
  clearRoute()
  clearPositionMarkers()
  map = null
  googleMaps = null
})

watch(
  [
    () => mapMode.value,
    () => spotCandidates.value,
    () => currentLocation.value,
    () => activeNavigation.value,
  ],
  () => {
    void syncMapScene()
  },
  { deep: true },
)

async function syncMapScene() {
  if (!map || !googleMaps) return

  if (mapMode.value === 'navigation' && activeNavigation.value) {
    await renderNavigation()
    return
  }

  if (mapMode.value === 'candidates' && spotCandidates.value.length > 0) {
    renderCandidateMarkers()
    return
  }

  renderIdleState()
}

function initializeMap() {
  if (!mapEl.value || !googleMaps?.maps) return

  map = new googleMaps.maps.Map(mapEl.value, {
    center: TAIPEI,
    zoom: 13,
    streetViewControl: false,
    mapTypeControl: false,
    fullscreenControl: false,
  })

  directionsService = new googleMaps.maps.DirectionsService()
  directionsRenderer = createDirectionsRenderer()
}

function createDirectionsRenderer() {
  if (!googleMaps?.maps || !map) return null

  return new googleMaps.maps.DirectionsRenderer({
    map,
    suppressMarkers: true,
    preserveViewport: false,
    polylineOptions: {
      strokeColor: '#2563eb',
      strokeOpacity: 0.92,
      strokeWeight: 6,
    },
  })
}

function renderIdleState() {
  clearCandidateMarkers()
  clearRoute()
  removeMarker(destinationMarker)
  destinationMarker = null

  if (currentLocation.value) {
    const origin = toLatLngLiteral(currentLocation.value)
    currentMarker = updateMarker(currentMarker, origin, '你', '#2563eb', '目前位置')
    map?.setCenter(origin)
    map?.setZoom(13)
  } else {
    removeMarker(currentMarker)
    currentMarker = null
    map?.setCenter(TAIPEI)
    map?.setZoom(12)
  }
}

function renderCandidateMarkers() {
  if (!googleMaps?.maps || !map) return

  clearRoute()
  removeMarker(destinationMarker)
  destinationMarker = null
  clearCandidateMarkers()

  const bounds = new googleMaps.maps.LatLngBounds()

  if (currentLocation.value) {
    const origin = toLatLngLiteral(currentLocation.value)
    currentMarker = updateMarker(currentMarker, origin, '你', '#2563eb', '目前位置')
    bounds.extend(origin)
  } else {
    removeMarker(currentMarker)
    currentMarker = null
  }

  for (const [index, card] of spotCandidates.value.entries()) {
    const position = { lat: card.lat, lng: card.lng }
    const marker = new googleMaps.maps.Marker({
      position,
      map,
      title: card.name,
      label: {
        text: String(index + 1),
        color: '#ffffff',
        fontWeight: '700',
      },
      icon: buildCircleIcon('#f97316', 12),
    })
    candidateMarkers.push(marker)
    bounds.extend(position)
  }

  if (candidateMarkers.length > 0) {
    map.fitBounds(bounds, 56)
  } else if (currentLocation.value) {
    map.setCenter(toLatLngLiteral(currentLocation.value))
    map.setZoom(13)
  }
}

async function renderNavigation() {
  if (!googleMaps?.maps || !map || !directionsService || !activeNavigation.value) return

  clearCandidateMarkers()

  const navigation = activeNavigation.value
  const destination = { lat: navigation.venue.lat, lng: navigation.venue.lng }
  destinationMarker = updateMarker(
    destinationMarker,
    destination,
    '終',
    '#dc2626',
    navigation.venue.name,
  )

  if (!currentLocation.value) {
    clearRoute()
    removeMarker(currentMarker)
    currentMarker = null
    fitNavigationBounds(null, destination)
    setNavigationError('暫時抓不到目前位置，請先改用外部導航。')
    return
  }

  const origin = toLatLngLiteral(currentLocation.value)
  currentMarker = updateMarker(currentMarker, origin, '你', '#2563eb', '目前位置')

  if (!shouldReroute(navigation.transportMode)) {
    fitNavigationBounds(origin, destination)
    return
  }

  setNavigationLoading()
  routeRequestId += 1
  const requestId = routeRequestId

  try {
    const result = await requestDirections(origin, destination, navigation.transportMode)
    if (requestId !== routeRequestId) return

    directionsRenderer = directionsRenderer ?? createDirectionsRenderer()
    directionsRenderer?.setMap(map)
    directionsRenderer?.setDirections(result)

    lastRouteModeKey = buildRouteModeKey(navigation.transportMode, navigation.venue.venue_id)
    lastRouteOrigin = { lat: origin.lat, lng: origin.lng }

    const summary = extractRouteSummary(result)
    const steps = extractRouteSteps(result)
    setNavigationReady(summary, steps)
  } catch {
    if (requestId !== routeRequestId) return

    clearRoute()
    lastRouteModeKey = ''
    lastRouteOrigin = null
    fitNavigationBounds(origin, destination)
    setNavigationError('Google 路線暫時不可用，請改用下方外部導航。')
  }
}

function requestDirections(
  origin: { lat: number; lng: number },
  destination: { lat: number; lng: number },
  transportMode: string,
): Promise<GoogleDirectionsResult> {
  return new Promise((resolve, reject) => {
    directionsService?.route(
      {
        origin,
        destination,
        travelMode: toGoogleTravelMode(transportMode),
      },
      (result: GoogleDirectionsResult | null, status: string) => {
        if (status === 'OK' && result) {
          resolve(result)
          return
        }
        reject(new Error(status || 'directions_failed'))
      },
    )
  })
}

function shouldReroute(transportMode: string) {
  const navigation = activeNavigation.value
  const origin = currentLocation.value
  if (!navigation || !origin) return false

  const routeModeKey = buildRouteModeKey(transportMode, navigation.venue.venue_id)
  if (routeModeKey !== lastRouteModeKey) return true
  if (!lastRouteOrigin) return true

  return distanceMeters(origin, lastRouteOrigin) >= REROUTE_DISTANCE_M
}

function buildRouteModeKey(transportMode: string, venueId: string | number) {
  return `${transportMode}:${String(venueId)}`
}

function toGoogleTravelMode(transportMode: string) {
  if (transportMode === 'walk') return 'WALKING'
  if (transportMode === 'drive') return 'DRIVING'
  return 'TRANSIT'
}

function updateMarker(
  marker: GoogleMarker | null,
  position: { lat: number; lng: number },
  label: string,
  color: string,
  title: string,
) {
  if (!googleMaps?.maps || !map) return marker

  if (!marker) {
    return new googleMaps.maps.Marker({
      position,
      map,
      title,
      label: {
        text: label,
        color: '#ffffff',
        fontWeight: '700',
      },
      icon: buildCircleIcon(color, label === '你' ? 11 : 12),
      zIndex: label === '你' ? 1000 : undefined,
    })
  }

  marker.setPosition(position)
  marker.setTitle(title)
  marker.setLabel({
    text: label,
    color: '#ffffff',
    fontWeight: '700',
  })
  marker.setIcon(buildCircleIcon(color, label === '你' ? 11 : 12))
  marker.setMap(map)
  return marker
}

function buildCircleIcon(color: string, scale: number) {
  return {
    path: googleMaps?.maps?.SymbolPath?.CIRCLE,
    fillColor: color,
    fillOpacity: 1,
    strokeColor: '#ffffff',
    strokeWeight: 2,
    scale,
  }
}

function clearCandidateMarkers() {
  candidateMarkers.forEach(removeMarker)
  candidateMarkers = []
}

function clearPositionMarkers() {
  removeMarker(currentMarker)
  currentMarker = null
  removeMarker(destinationMarker)
  destinationMarker = null
}

function clearRoute(resetRenderer = true) {
  if (directionsRenderer) {
    directionsRenderer.setMap(null)
  }

  if (resetRenderer) {
    directionsRenderer = createDirectionsRenderer()
  }
}

function fitNavigationBounds(
  origin: { lat: number; lng: number } | null,
  destination: { lat: number; lng: number },
) {
  if (!googleMaps?.maps || !map) return

  const bounds = new googleMaps.maps.LatLngBounds()
  if (origin) bounds.extend(origin)
  bounds.extend(destination)
  map.fitBounds(bounds, 64)
}

function extractRouteSummary(result: GoogleDirectionsResult) {
  const leg = result?.routes?.[0]?.legs?.[0]
  return {
    durationText: leg?.duration?.text ?? null,
    distanceText: leg?.distance?.text ?? null,
  }
}

function extractRouteSteps(result: GoogleDirectionsResult) {
  const steps = result?.routes?.[0]?.legs?.[0]?.steps ?? []
  return steps.map((step: any) => ({
    instruction: htmlToText(step.instructions ?? ''),
    distanceText: step.distance?.text ?? null,
    durationText: step.duration?.text ?? null,
    lineName: step.transit?.line?.short_name ?? step.transit?.line?.name ?? null,
    travelMode: step.travel_mode ?? null,
  }))
}

function htmlToText(value: string) {
  const container = document.createElement('div')
  container.innerHTML = value
  return container.textContent?.trim() || value
}

function removeMarker(marker: GoogleMarker | null) {
  marker?.setMap(null)
}

function toLatLngLiteral(point: { lat: number; lng: number }) {
  return { lat: point.lat, lng: point.lng }
}

function distanceMeters(
  a: { lat: number; lng: number },
  b: { lat: number; lng: number },
) {
  const rad = (deg: number) => deg * (Math.PI / 180)
  const radius = 6_371_000
  const dLat = rad(b.lat - a.lat)
  const dLng = rad(b.lng - a.lng)
  const lat1 = rad(a.lat)
  const lat2 = rad(b.lat)
  const haversine =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2

  return 2 * radius * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine))
}

function toMapErrorMessage(error: unknown) {
  if (error instanceof Error && error.message === 'missing_google_maps_api_key') {
    return '尚未設定 Google Maps 金鑰，右側地圖無法顯示。'
  }
  return 'Google 地圖暫時無法載入。'
}
</script>

<style scoped>
.map-panel {
  flex: 1;
  position: relative;
  overflow: hidden;
  min-width: 0;
  border-radius: 0 15px 15px 0;
  background:
    radial-gradient(circle at top left, rgba(191, 219, 254, 0.35), transparent 28%),
    linear-gradient(180deg, #eff6ff 0%, #f8fbff 100%);
}

.map-container {
  width: 100%;
  height: 100%;
}

.location-badge {
  position: absolute;
  top: 24px;
  right: 20px;
  background: rgba(15, 23, 42, 0.82);
  color: #fff;
  padding: 9px 18px;
  border-radius: 999px;
  font-size: 13px;
  z-index: 2;
  pointer-events: none;
  backdrop-filter: blur(6px);
}

.map-hint {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(255, 255, 255, 0.94);
  color: #475569;
  font-size: 13px;
  padding: 8px 16px;
  border-radius: 14px;
  z-index: 2;
  pointer-events: none;
  white-space: nowrap;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.12);
}

.map-hint--error {
  background: rgba(127, 29, 29, 0.92);
  color: #fff7ed;
}
</style>

<style>
/* Preserve a second style block so Vite HMR can reconcile the previous
   MapPanel style module indices after the Leaflet-to-Google-Maps rewrite. */
</style>
