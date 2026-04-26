import { ref, onMounted } from 'vue'
import { getWeather } from '../services/api'

export interface WeatherState {
  loading: boolean
  isRainingLikely: boolean
  rainProbability: number | null
  condition: string | null
  temperature: number | null
  windDirection: string | null
}

const weather = ref<WeatherState>({
  loading: false,
  isRainingLikely: false,
  rainProbability: null,
  condition: null,
  temperature: null,
  windDirection: null,
})

export function useWeather() {
  async function fetchWeather() {
    weather.value.loading = true
    try {
      const data = await getWeather()
      weather.value.isRainingLikely = data.is_raining_likely
      weather.value.rainProbability = data.rain_probability
      weather.value.condition = data.condition
      weather.value.temperature = data.temperature
      weather.value.windDirection = data.wind_direction
    } catch (err) {
      console.error('Failed to fetch weather:', err)
    } finally {
      weather.value.loading = false
    }
  }

  onMounted(() => {
    if (weather.value.loading) {
      fetchWeather()
    }
  })

  return {
    weather,
    fetchWeather
  }
}
