export interface ItineraryStop {
  order: number
  venue_id: string
  name: string
  district: string
  category: string
  address: string
  lat: number
  lng: number
  suggested_start: string
  suggested_end: string
  duration_minutes: number
  travel_minutes_from_prev: number
  reason: string
  tags: string[]
  cost_level: 'low' | 'medium' | 'high'
  indoor: boolean
}

export interface ItineraryResponse {
  status: string
  district: string
  date: string
  weather_condition: string
  stops: ItineraryStop[]
  total_stops: number
  total_duration_minutes: number
}

export interface ItineraryRequest {
  district: string
  start_time: string
  end_time: string
  interests: string[]
  budget: 'low' | 'medium' | 'high'
  companion: 'solo' | 'couple' | 'family' | 'friends'
  indoor_pref: 'indoor' | 'outdoor' | 'both'
}

export interface ApiError {
  status: 'error'
  code: string
  message: string
}
