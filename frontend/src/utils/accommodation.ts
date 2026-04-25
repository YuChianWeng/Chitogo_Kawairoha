import type { AccommodationMode } from '../types/trip'

const ACCOMMODATION_STATE_KEY = 'chitogo_accommodation_state'

export interface StoredAccommodationState {
  mode: AccommodationMode
  hotelName: string | null
  displayName: string | null
}

export function readAccommodationState(): StoredAccommodationState | null {
  const raw = localStorage.getItem(ACCOMMODATION_STATE_KEY)
  if (!raw) return null

  try {
    return JSON.parse(raw) as StoredAccommodationState
  } catch {
    localStorage.removeItem(ACCOMMODATION_STATE_KEY)
    return null
  }
}

export function saveAccommodationState(state: StoredAccommodationState) {
  localStorage.setItem(ACCOMMODATION_STATE_KEY, JSON.stringify(state))
}

export function clearAccommodationState() {
  localStorage.removeItem(ACCOMMODATION_STATE_KEY)
}
