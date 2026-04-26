import { ref, onMounted } from 'vue'
import { getWeather } from '../services/api'

export interface WeatherState {
  isRainingLikely: boolean
  rainProbability: number | null
  loading: boolean
}

const weather = ref<WeatherState>({
  isRainingLikely: false,
  rainProbability: null,
  loading: true
})

export function useWeather() {
  async function fetchWeather() {
    weather.value.loading = true
    try {
      const data = await getWeather()
      weather.value.isRainingLikely = data.is_raining_likely
      weather.value.rainProbability = data.rain_probability
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
