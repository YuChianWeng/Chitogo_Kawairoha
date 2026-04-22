import axios from 'axios'
import type { ChatRequest, ChatResponse } from '../types/itinerary'

const client = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
})

export async function sendMessage(request: ChatRequest): Promise<ChatResponse> {
  const { data } = await client.post<ChatResponse>('/chat/message', request)
  return data
}
