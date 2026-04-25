import axios from 'axios'
import type { ChatRequest, ChatResponse } from '../types/itinerary'
import type {
  QuizAnswers,
  QuizResult,
  TripSetup,
  CandidateTransportInput,
  SetupResult,
  CandidatesResult,
  SelectResult,
  RateResult,
  DemandResult,
  GoHomeStatus,
  JourneySummary,
} from '../types/trip'

const client = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
})

export async function sendMessage(request: ChatRequest): Promise<ChatResponse> {
  const { data } = await client.post<ChatResponse>('/chat/message', request)
  return data
}

export async function createSession(): Promise<{ session_id: string }> {
  const { data } = await client.post<{ session_id: string }>('/chat/sessions')
  return data
}

export async function submitQuiz(sessionId: string, answers: QuizAnswers): Promise<QuizResult> {
  const { data } = await client.post<QuizResult>('/trip/quiz', {
    session_id: sessionId,
    answers,
  })
  return data
}

export async function submitSetup(sessionId: string, setup: TripSetup): Promise<SetupResult> {
  const { data } = await client.post<SetupResult>('/trip/setup', {
    session_id: sessionId,
    ...setup,
  })
  return data
}

export async function getCandidates(
  sessionId: string,
  lat: number,
  lng: number,
  transport: CandidateTransportInput
): Promise<CandidatesResult> {
  const params = new URLSearchParams()
  params.set('session_id', sessionId)
  params.set('lat', String(lat))
  params.set('lng', String(lng))
  params.set('mode', transport.mode)
  params.set('max_minutes_per_leg', String(transport.max_minutes_per_leg))

  const { data } = await client.get<CandidatesResult>('/trip/candidates', {
    params,
  })
  return data
}

export async function selectVenue(
  sessionId: string,
  venueId: string | number,
  lat: number,
  lng: number
): Promise<SelectResult> {
  const { data } = await client.post<SelectResult>('/trip/select', {
    session_id: sessionId,
    venue_id: venueId,
    current_lat: lat,
    current_lng: lng,
  })
  return data
}

export async function submitRating(
  sessionId: string,
  stars: number,
  tags: string[]
): Promise<RateResult> {
  const { data } = await client.post<RateResult>('/trip/rate', {
    session_id: sessionId,
    stars,
    tags,
  })
  return data
}

export async function submitDemand(
  sessionId: string,
  text: string,
  lat: number,
  lng: number
): Promise<DemandResult> {
  const { data } = await client.post<DemandResult>('/trip/demand', {
    session_id: sessionId,
    demand_text: text,
    lat,
    lng,
  })
  return data
}

export async function checkGoHome(
  sessionId: string,
  lat: number,
  lng: number
): Promise<GoHomeStatus> {
  const { data } = await client.get<GoHomeStatus>('/trip/should_go_home', {
    params: { session_id: sessionId, lat, lng },
  })
  return data
}

export async function getSummary(sessionId: string): Promise<JourneySummary> {
  const { data } = await client.get<JourneySummary>('/trip/summary', {
    params: { session_id: sessionId },
  })
  return data
}
