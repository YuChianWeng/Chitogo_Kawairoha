import { ref } from 'vue'
import RecordRTC from 'recordrtc'
import { transcribeAudio } from '../services/api'

export function useVoiceRecorder() {
  const isRecording = ref(false)
  const isTranscribing = ref(false)
  const error = ref<string | null>(null)

  let stream: MediaStream | null = null
  let rtcRecorder: RecordRTC | null = null
  let autoStopTimer: ReturnType<typeof setTimeout> | null = null

  const isSupported =
    typeof navigator.mediaDevices?.getUserMedia !== 'undefined'

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

    // Use StereoAudioRecorder from RecordRTC to produce WAV
    rtcRecorder = new RecordRTC(stream, {
      type: 'audio',
      mimeType: 'audio/wav',
      recorderType: RecordRTC.StereoAudioRecorder,
      numberOfAudioChannels: 1,
      desiredSampRate: 16000,
    })

    rtcRecorder.startRecording()
    isRecording.value = true

    autoStopTimer = setTimeout(() => { void stop() }, 30_000)
  }

  async function stop(): Promise<string> {
    if (autoStopTimer) { clearTimeout(autoStopTimer); autoStopTimer = null }
    if (!rtcRecorder) {
      isRecording.value = false
      return ''
    }

    return new Promise((resolve) => {
      rtcRecorder!.stopRecording(async () => {
        stream?.getTracks().forEach(t => t.stop())
        const blob = rtcRecorder!.getBlob()
        
        isRecording.value = false
        isTranscribing.value = true
        try {
          const { text } = await transcribeAudio(blob)
          resolve(text)
        } catch (e) {
          console.error('Transcription error:', e)
          error.value = '語音辨識失敗，請再試一次。'
          resolve('')
        } finally {
          isTranscribing.value = false
          stream = null
          rtcRecorder = null
        }
      })
    })
  }

  function cancel() {
    if (autoStopTimer) { clearTimeout(autoStopTimer); autoStopTimer = null }
    if (rtcRecorder) {
      rtcRecorder.destroy()
      rtcRecorder = null
    }
    stream?.getTracks().forEach(t => t.stop())
    isRecording.value = false
    isTranscribing.value = false
    stream = null
  }

  return { isSupported, isRecording, isTranscribing, error, start, stop, cancel }
}
