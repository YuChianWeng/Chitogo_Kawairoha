<template>
  <button
    type="button"
    class="mic-btn"
    :class="{ recording: isRecording, transcribing: isTranscribing }"
    :disabled="!isSupported || disabled || isTranscribing"
    :aria-label="label"
    :aria-pressed="isRecording"
    @click="toggle"
  >
    <span v-if="isTranscribing" class="mic-spinner" />
    <span v-else-if="isRecording" class="mic-stop" />
    <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
      <line x1="12" y1="19" x2="12" y2="23"/>
      <line x1="8" y1="23" x2="16" y2="23"/>
    </svg>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useVoiceRecorder } from '../composables/useVoiceRecorder'
import { useLocale } from '../composables/useLocale'

const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{
  transcribed: [text: string]
  error: [message: string]
}>()

const { isSupported, isRecording, isTranscribing, error, start, stop } = useVoiceRecorder()
const { locale } = useLocale()

const label = computed(() => {
  if (isTranscribing.value) return locale.value.common.mic.transcribing
  if (isRecording.value) return locale.value.common.mic.recording
  return locale.value.common.mic.idle
})

async function toggle() {
  if (isRecording.value) {
    const text = await stop()
    if (error.value) {
      emit('error', error.value)
    } else if (text) {
      emit('transcribed', text)
    }
  } else {
    await start()
    if (error.value) emit('error', error.value)
  }
}
</script>

<style scoped>
.mic-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1.5px solid #dbeafe;
  background: white;
  color: #2563eb;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.18s, border-color 0.18s, transform 0.18s;
}

.mic-btn:hover:not(:disabled) {
  background: #eff6ff;
  border-color: #93c5fd;
  transform: scale(1.05);
}

.mic-btn.recording {
  background: #fef2f2;
  border-color: #fca5a5;
  color: #ef4444;
  animation: pulse-mic 1.2s ease-in-out infinite;
}

.mic-btn.transcribing {
  background: #f0f9ff;
  border-color: #bae6fd;
  color: #0284c7;
}

.mic-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none;
}

.mic-stop {
  width: 10px;
  height: 10px;
  background: currentColor;
  border-radius: 2px;
}

.mic-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #bae6fd;
  border-top-color: #0284c7;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes pulse-mic {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.08); }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
