type GoogleMapsApi = {
  maps?: unknown
}

type GoogleMapsWindow = Window & {
  google?: GoogleMapsApi
  __chitogoGoogleMapsInit__?: () => void
}

let googleMapsPromise: Promise<GoogleMapsApi> | null = null

export function loadGoogleMapsApi(): Promise<GoogleMapsApi> {
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY?.trim()
  if (!apiKey) {
    return Promise.reject(new Error('missing_google_maps_api_key'))
  }

  const mapWindow = window as GoogleMapsWindow
  if (mapWindow.google?.maps) {
    return Promise.resolve(mapWindow.google)
  }

  if (googleMapsPromise) {
    return googleMapsPromise
  }

  googleMapsPromise = new Promise((resolve, reject) => {
    mapWindow.__chitogoGoogleMapsInit__ = () => {
      if (mapWindow.google?.maps) {
        resolve(mapWindow.google)
      } else {
        googleMapsPromise = null
        reject(new Error('google_maps_unavailable'))
      }
      delete mapWindow.__chitogoGoogleMapsInit__
    }

    const script = document.createElement('script')
    script.src =
      `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}` +
      '&libraries=places&language=zh-TW&region=TW&callback=__chitogoGoogleMapsInit__'
    script.async = true
    script.defer = true
    script.dataset.googleMapsLoader = 'chitogo'
    script.onerror = () => {
      googleMapsPromise = null
      delete mapWindow.__chitogoGoogleMapsInit__
      reject(new Error('google_maps_script_failed'))
    }
    document.head.appendChild(script)
  })

  return googleMapsPromise
}
