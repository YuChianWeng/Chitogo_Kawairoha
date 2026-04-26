<template>
  <div class="return-dest-picker">
    <input
      ref="inputRef"
      :value="displayValue"
      :placeholder="placeholder"
      class="text-input"
      autocomplete="off"
      @input="onManualInput"
    />
    <p v-if="loadError" class="picker-fallback-notice">無法載入地點建議，將使用文字輸入</p>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadGoogleMapsApi } from '../../utils/googleMaps'

export interface PlaceValue {
  name: string
  place_id: string | null
  lat: number | null
  lng: number | null
}

const props = defineProps<{
  modelValue: PlaceValue | null
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: PlaceValue | null): void
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const loadError = ref(false)
// Track what the input shows independently so we can update it without a full re-render cycle
const displayValue = ref(props.modelValue?.name ?? '')

// When parent clears modelValue externally, sync the display
watch(
  () => props.modelValue,
  (val) => {
    if (!val) displayValue.value = ''
  },
)

let autocomplete: google.maps.places.Autocomplete | null = null

function onManualInput(event: Event) {
  const raw = (event.target as HTMLInputElement).value
  displayValue.value = raw
  // Emit free-text payload so geocoding fallback still applies
  emit('update:modelValue', raw.trim() ? { name: raw, place_id: null, lat: null, lng: null } : null)
}

function onPlaceChanged() {
  if (!autocomplete) return
  const place = autocomplete.getPlace()
  const loc = place.geometry?.location
  if (loc) {
    const value: PlaceValue = {
      name: place.name ?? displayValue.value,
      place_id: place.place_id ?? null,
      lat: loc.lat(),
      lng: loc.lng(),
    }
    displayValue.value = value.name
    emit('update:modelValue', value)
  } else {
    // User typed and pressed Enter without selecting a dropdown item — free-text fallback
    emit('update:modelValue', {
      name: displayValue.value,
      place_id: null,
      lat: null,
      lng: null,
    })
  }
}

onMounted(async () => {
  if (!inputRef.value) return

  try {
    await loadGoogleMapsApi()

    const g = (window as unknown as { google: typeof google }).google
    autocomplete = new g.maps.places.Autocomplete(inputRef.value, {
      fields: ['place_id', 'name', 'geometry'],
      componentRestrictions: { country: 'tw' },
      types: ['establishment', 'geocode'],
      // Bias toward central Taipei
      bounds: new g.maps.LatLngBounds(
        new g.maps.LatLng(24.9, 121.4),
        new g.maps.LatLng(25.2, 121.7),
      ),
      strictBounds: false,
    })

    autocomplete.addListener('place_changed', onPlaceChanged)
  } catch {
    loadError.value = true
  }
})

onBeforeUnmount(() => {
  if (autocomplete) {
    google.maps.event.clearInstanceListeners(autocomplete)
    autocomplete = null
  }
})
</script>

<style scoped>
.return-dest-picker {
  width: 100%;
}

.picker-fallback-notice {
  margin-top: 4px;
  font-size: 12px;
  color: #94a3b8;
}
</style>
