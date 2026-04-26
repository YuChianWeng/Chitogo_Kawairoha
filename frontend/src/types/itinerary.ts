export interface ChatRequest {
  message: string
  session_id?: string
  user_context?: { lat: number; lng: number } | null
}

export interface ChatCandidate {
  place_id: string | number
  name: string
  name_en?: string | null
  district?: string
  category?: string
  primary_type?: string | null
  address?: string | null
  lat?: number | null
  lng?: number | null
  rating?: number
  budget_level?: string
  why_recommended?: string
  vibe_tags?: string[] | null
  mention_count?: number | null
  sentiment_score?: number | null
  trend_score?: number | null
}

export interface ItineraryLeg {
  from_stop: number
  to_stop: number
  transit_method: string
  duration_min: number
}

export interface ItineraryStop {
  stop_index: number
  venue_name: string
  category?: string
  arrival_time?: string
  visit_duration_min?: number
  lat?: number
  lng?: number
}

export interface Itinerary {
  summary?: string
  total_duration_min?: number
  stops: ItineraryStop[]
  legs: ItineraryLeg[]
}

export interface ChatResponse {
  session_id: string
  turn_id: string
  intent: 'GENERATE_ITINERARY' | 'REPLAN' | 'EXPLAIN' | 'CHAT_GENERAL'
  needs_clarification: boolean
  message: string
  itinerary?: Itinerary | null
  candidates: ChatCandidate[]
  routing_status?: 'full' | 'partial_fallback' | 'failed' | null
}

export interface ApiError {
  error: string
  detail?: string
}
