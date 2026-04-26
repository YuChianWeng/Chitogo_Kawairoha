<template>
  <div class="composer-bar">
    <MicButton
      :disabled="disabled || sending"
      @transcribed="onTranscribed"
      @error="onMicError"
    />
    <div class="composer-field">
      <textarea
        ref="textareaEl"
        v-model="text"
        class="composer-textarea"
        :placeholder="placeholder || locale.common.composerPlaceholder"
        :disabled="disabled || sending"
        rows="1"
        enterkeyhint="send"
        @keydown.enter.exact.prevent="submit"
        @input="autoResize"
      />
      <p v-if="micError" class="composer-error">{{ micError }}</p>
    </div>
    <button
      type="button"
      class="send-btn"
      :disabled="disabled || sending || !text.trim()"
      aria-label="送出"
      @click="submit"
    >
      <span v-if="sending" class="send-spinner" />
      <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <line x1="22" y1="2" x2="11" y2="13"/>
        <polygon points="22 2 15 22 11 13 2 9 22 2"/>
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import MicButton from './MicButton.vue'
import { useLocale } from '../composables/useLocale'

const props = defineProps<{
  disabled?: boolean
  sending?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{ submit: [text: string] }>()

const { locale } = useLocale()
const text = ref('')
const micError = ref<string | null>(null)
const textareaEl = ref<HTMLTextAreaElement | null>(null)

function autoResize() {
  const el = textareaEl.value
  if (!el) return
  el.style.height = 'auto'
  const lineHeight = parseInt(getComputedStyle(el).lineHeight) || 24
  el.style.height = Math.min(el.scrollHeight, lineHeight * 5) + 'px'
}

function submit() {
  const trimmed = text.value.trim()
  if (!trimmed || props.disabled || props.sending) return
  emit('submit', trimmed)
  text.value = ''
  nextTick(() => autoResize())
}

function onTranscribed(transcript: string) {
  micError.value = null
  text.value = text.value ? `${text.value} ${transcript}` : transcript
  nextTick(() => autoResize())
}

function onMicError(msg: string) {
  micError.value = msg
  setTimeout(() => { micError.value = null }, 4000)
}
</script>

<style scoped>
.composer-bar {
  position: sticky;
  bottom: 0;
  z-index: 10;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 12px 20px;
  padding-bottom: max(12px, env(safe-area-inset-bottom));
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  border-top: 1px solid rgba(191, 219, 254, 0.7);
  box-sizing: border-box;
}

.composer-field {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.composer-textarea {
  width: 100%;
  border: 1.5px solid #dbeafe;
  border-radius: 20px;
  padding: 10px 16px;
  font-family: inherit;
  font-size: 15px;
  color: #1e293b;
  background: white;
  resize: none;
  line-height: 1.5;
  box-sizing: border-box;
  overflow-y: hidden;
  transition: border-color 0.18s;
}

.composer-textarea:focus {
  outline: none;
  border-color: #93c5fd;
}

.composer-textarea:disabled {
  background: #f8fafc;
  color: #94a3b8;
}

.composer-error {
  margin: 0;
  font-size: 12px;
  color: #ef4444;
  padding: 0 4px;
}

.send-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: opacity 0.18s, transform 0.18s;
}

.send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none;
}

.send-btn:not(:disabled):hover {
  transform: scale(1.05);
}

.send-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 767px) {
  .composer-bar {
    padding: 10px 12px;
    /* No extra safe-area padding needed here — the root layout already
       reserves padding-bottom for the bottom nav + safe area. */
    padding-bottom: 10px;
    gap: 8px;
  }

  .composer-textarea {
    font-size: 16px; /* prevents iOS auto-zoom */
  }

  .send-btn {
    width: 44px;
    height: 44px;
    flex-shrink: 0;
  }
}
</style>
