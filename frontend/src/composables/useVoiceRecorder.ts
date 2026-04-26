import { ref } from 'vue'
import { transcribeAudio } from '../services/api'

export function useVoiceRecorder() {
  const isRecording = ref(false)
  const isTranscribing = ref(false)
  const error = ref<string | null>(null)

  let stream: MediaStream | null = null
  let recorder: MediaRecorder | null = null
  let chunks: Blob[] = []
  let autoStopTimer: ReturnType<typeof setTimeout> | null = null

  const isSupported =
    typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia

  async function start() {
    if (!isSupported) {
      error.value = window.isSecureContext
        ? '此瀏覽器不支援錄音'
        : '語音需要 HTTPS 才能使用'
      return
    }
    error.value = null
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      const name = (e as DOMException).name
      error.value = name === 'NotAllowedError' ? '請允許麥克風權限' : '找不到麥克風裝置'
      return
    }

    chunks = []
    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : undefined
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
    recorder.start()
    isRecording.value = true

    autoStopTimer = setTimeout(() => { void stop() }, 30_000)
  }

  async function stop(): Promise<string> {
    if (autoStopTimer) { clearTimeout(autoStopTimer); autoStopTimer = null }
    if (!recorder || recorder.state === 'inactive') {
      isRecording.value = false
      return ''
    }
    return new Promise((resolve) => {
      recorder!.onstop = async () => {
        stream?.getTracks().forEach(t => t.stop())
        const mimeType = recorder!.mimeType || 'audio/webm'
        const blob = new Blob(chunks, { type: mimeType })
        isRecording.value = false
        isTranscribing.value = true
        try {
          const { text } = await transcribeAudio(blob)
          resolve(text)
        } catch {
          error.value = '語音辨識失敗，請再試一次。'
          resolve('')
        } finally {
          isTranscribing.value = false
          stream = null
          recorder = null
          chunks = []
        }
      }
      recorder!.stop()
    })
  }

  function cancel() {
    if (autoStopTimer) { clearTimeout(autoStopTimer); autoStopTimer = null }
    if (recorder && recorder.state !== 'inactive') recorder.stop()
    stream?.getTracks().forEach(t => t.stop())
    isRecording.value = false
    isTranscribing.value = false
    stream = null
    recorder = null
    chunks = []
  }

  return { isSupported, isRecording, isTranscribing, error, start, stop, cancel }
}
