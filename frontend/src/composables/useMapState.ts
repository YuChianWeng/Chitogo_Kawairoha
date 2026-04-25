import { ref } from 'vue'
import type { CandidateCard, SelectResult, TransportMode } from '../types/trip'

export type MapMode = 'idle' | 'candidates' | 'navigation'
export type LocationSource = 'approximate' | 'gps' | 'fallback'
export type NavigationStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface MapLocation {
  lat: number
  lng: number
  label: string
  source: LocationSource
}

export interface RouteSummary {
  durationText: string | null
  distanceText: string | null
}

export interface RouteStep {
  instruction: string
  distanceText: string | null
  durationText: string | null
  lineName: string | null
  travelMode: string | null
}

export interface ActiveNavigation {
  venue: SelectResult['venue']
  transportMode: TransportMode
  googleMapsUrl: string
  appleMapsUrl: string
  estimatedTravelMin: number
}

const mapMode = ref<MapMode>('idle')
const spotCandidates = ref<CandidateCard[]>([])
const currentLocation = ref<MapLocation | null>(null)
const activeNavigation = ref<ActiveNavigation | null>(null)
const navigationStatus = ref<NavigationStatus>('idle')
const routeSummary = ref<RouteSummary | null>(null)
const navigationSteps = ref<RouteStep[]>([])
const navigationError = ref<string | null>(null)

function clearNavigationState() {
  activeNavigation.value = null
  navigationStatus.value = 'idle'
  routeSummary.value = null
  navigationSteps.value = []
  navigationError.value = null
}

export function useMapState() {
  function setSpotCandidates(candidates: CandidateCard[]) {
    spotCandidates.value = candidates
    mapMode.value = candidates.length > 0 ? 'candidates' : 'idle'
  }

  function clearSpotCandidates() {
    spotCandidates.value = []
    if (mapMode.value === 'candidates') {
      mapMode.value = 'idle'
    }
  }

  function setCurrentLocation(location: MapLocation) {
    currentLocation.value = location
  }

  function setActiveNavigation(navigation: ActiveNavigation) {
    activeNavigation.value = navigation
    navigationStatus.value = 'loading'
    routeSummary.value = null
    navigationSteps.value = []
    navigationError.value = null
    mapMode.value = 'navigation'
  }

  function setNavigationLoading() {
    navigationStatus.value = 'loading'
    navigationError.value = null
  }

  function setNavigationReady(summary: RouteSummary, steps: RouteStep[]) {
    navigationStatus.value = 'ready'
    routeSummary.value = summary
    navigationSteps.value = steps
    navigationError.value = null
  }

  function setNavigationError(message: string) {
    navigationStatus.value = 'error'
    routeSummary.value = null
    navigationSteps.value = []
    navigationError.value = message
  }

  function clearNavigation() {
    clearNavigationState()
    mapMode.value = spotCandidates.value.length > 0 ? 'candidates' : 'idle'
  }

  function resetMapState() {
    spotCandidates.value = []
    currentLocation.value = null
    mapMode.value = 'idle'
    clearNavigationState()
  }

  return {
    mapMode,
    spotCandidates,
    currentLocation,
    activeNavigation,
    navigationStatus,
    routeSummary,
    navigationSteps,
    navigationError,
    setSpotCandidates,
    clearSpotCandidates,
    setCurrentLocation,
    setActiveNavigation,
    setNavigationLoading,
    setNavigationReady,
    setNavigationError,
    clearNavigation,
    resetMapState,
  }
}
