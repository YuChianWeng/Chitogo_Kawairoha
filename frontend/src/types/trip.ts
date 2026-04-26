export type TravelGene =
  | '文山包種茶'
  | '古早味彈珠汽水'
  | '珍珠奶茶'
  | '深夜永和豆漿'
  | '甘蔗青茶'
  | '野生愛玉冰'
  | '文清'
  | '親子'
  | '不常來'
  | '夜貓子'
  | '一日'
  | '野外'
export type TransportMode = 'walk' | 'transit' | 'drive'
export type FlowState = 'QUIZ' | 'TRANSPORT' | 'RECOMMENDING' | 'RATING' | 'ENDED'
export type AccommodationMode = 'booked' | 'need_hotel' | 'no_stay'
export type RecommendationStatus =
  | 'matched_preferences'
  | 'relaxed_budget'
  | 'expanded_citywide'
  | 'expanded_citywide_and_budget'
  | 'no_results'

export interface QuizAnswers {
  Q1: 'A' | 'B' | 'C'
  Q2: 'A' | 'B'
  Q3: 'A' | 'B'
  Q4: 'A' | 'B'
  Q5: 'A' | 'B'
  Q6: 'A' | 'B'
  Q7: 'A' | 'B'
  Q8: 'A' | 'B'
  Q9: 'A' | 'B'
}

export interface QuizResult {
  session_id: string
  travel_gene: TravelGene
  mascot: string
  gene_description: string
}

export interface AccommodationInput {
  mode: AccommodationMode
  hotel_name?: string
  district?: string
  budget_tier?: 'budget' | 'mid' | 'luxury'
}

export interface CandidateTransportInput {
  mode: TransportMode
  max_minutes_per_leg: number
}

export interface TripSetup {
  accommodation?: AccommodationInput
  return_time?: string
  return_destination?: string
  return_dest_lat?: number
  return_dest_lng?: number
  return_dest_place_id?: string
}

export interface HotelRecommendationCard {
  license_no: string | null
  place_id: number | null
  name: string
  district: string | null
  address: string | null
  rating: number | null
  budget_level: string | null
  google_maps_uri: string | null
  confidence: number | null
}

export interface HotelValidation {
  valid: boolean
  matched_name: string | null
  match_type: string | null
  confidence: number | null
  district: string | null
  address: string | null
  alternatives: HotelRecommendationCard[]
  last_updated: string
}

export interface SetupResult {
  session_id: string
  accommodation_status: 'validated' | 'fuzzy_match' | 'not_found' | 'not_required' | 'recommending'
  hotel_validation: HotelValidation | null
  hotel_recommendations: HotelRecommendationCard[]
  recommendation_status: RecommendationStatus | null
  next_step: 'accommodation' | 'setup' | 'trip'
  setup_complete: boolean
}

export interface CandidateCard {
  venue_id: string | number
  name: string
  name_en?: string | null
  category: 'restaurant' | 'attraction' | 'go_home'
  primary_type: string | null
  address: string | null
  lat: number
  lng: number
  rating: number | null
  distance_min: number
  why_recommended: string
  rain_note?: string | null
  vibe_tags?: string[]
  mention_count?: number | null
  sentiment_score?: number | null
  trend_score?: number | null
}

export interface CandidatesResult {
  session_id: string
  candidates: CandidateCard[]
  rain_filtered?: CandidateCard[]
  partial: boolean
  fallback_reason: string | null
  restaurant_count: number
  attraction_count: number
  go_home_reminder?: string | null
  homing_active?: boolean
  urgency_level?: string
}

export interface SelectResult {
  session_id: string
  venue: Pick<CandidateCard, 'venue_id' | 'name' | 'name_en' | 'category' | 'address' | 'lat' | 'lng'>
  navigation: {
    google_maps_url: string
    apple_maps_url: string
    estimated_travel_min: number
    transport_mode: TransportMode
  }
  encouragement_message: string
}

export interface RateResult {
  session_id: string
  visit_recorded: boolean
  stop_number: number
  affinity_update: { category: string; adjustment: number }
}

export interface DemandResult {
  session_id: string
  alternatives: CandidateCard[]
  rain_filtered?: CandidateCard[]
  fallback_reason: string | null
}

export interface GoHomeStatus {
  session_id: string
  remind: boolean
  message: string | null
  time_remaining_min: number | null
}

export interface VisitedStopSummary {
  stop_number: number
  venue_id: string | number
  venue_name: string
  category: 'restaurant' | 'attraction'
  address: string | null
  arrived_at: string
  star_rating: number
  tags: string[]
}

export interface JourneySummary {
  session_id: string
  travel_gene: TravelGene
  mascot: string
  stops: VisitedStopSummary[]
  total_stops: number
  total_elapsed_min: number
  total_distance_m: number
  mascot_farewell: string
}
