import { computed, ref } from 'vue'

const SIM_LOC_KEY = 'chitogo_demo_sim_location'

interface SimLocation {
  lat: number
  lng: number
  label: string
}

function loadStored(): SimLocation | null {
  try {
    const raw = sessionStorage.getItem(SIM_LOC_KEY)
    if (!raw) return null
    return JSON.parse(raw) as SimLocation
  } catch { return null }
}

const _simLoc = ref<SimLocation | null>(loadStored())

export function useSimLocation() {
  const isSimLocating = computed(() => _simLoc.value !== null)

  const simLat = computed(() => _simLoc.value?.lat ?? null)
  const simLng = computed(() => _simLoc.value?.lng ?? null)
  const simLabel = computed(() => _simLoc.value?.label ?? null)

  function setSimLocation(lat: number, lng: number, label: string) {
    _simLoc.value = { lat, lng, label }
    try {
      sessionStorage.setItem(SIM_LOC_KEY, JSON.stringify({ lat, lng, label }))
    } catch { /* ignore */ }
  }

  function clearSimLocation() {
    _simLoc.value = null
    try { sessionStorage.removeItem(SIM_LOC_KEY) } catch { /* ignore */ }
  }

  return {
    isSimLocating,
    simLat,
    simLng,
    simLabel,
    setSimLocation,
    clearSimLocation,
  }
}
