<template>
  <div class="quiz-container">
    <div class="quiz-card" v-if="phase === 'quiz'">
      <div class="card-topbar">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: `${(currentQ / 9) * 100}%` }"></div>
        </div>
        <LangToggle class="lang-toggle-inline" />
      </div>
      <p class="progress-label">{{ locale.quiz.progress(currentQ) }}</p>

      <h2 class="question-text">{{ currentQuestion.text }}</h2>

      <div class="options">
        <button
          v-for="opt in currentQuestion.options"
          :key="opt.key"
          class="option-btn"
          :class="{ selected: selectedAnswer === opt.key }"
          @click="selectAnswer(opt.key)"
        >
          {{ opt.label }}
        </button>
      </div>

      <button
        class="next-btn"
        :disabled="!selectedAnswer || loading"
        @click="nextQuestion"
      >
        {{ currentQ < 9 ? locale.quiz.next : locale.quiz.viewResult }}
      </button>

      <div v-if="errorText" class="error">{{ errorText }}</div>
    </div>

    <div class="result-card" v-else-if="phase === 'result'">
      <div class="result-header">
        <div class="result-topbar">
          <LangToggle />
        </div>
        <div class="mascot-container">
          <img
            :src="`/images/mascot_${mascot}${lang === 'en' ? '_en' : ''}.png`"
            :alt="displayGeneName"
            class="mascot-animate"
            @error="onMascotImgError"
          >
        </div>
        <p class="result-subtitle">{{ locale.quiz.resultSubtitle }}</p>
        <h2 class="gene-title">{{ displayGeneName }}</h2>
      </div>

      <div class="description-box">
        <p class="gene-desc">{{ displayGeneDescription }}</p>
      </div>

      <div class="action-group">
        <button class="start-btn" @click="goToSetup">{{ locale.quiz.startPlanning }}</button>
        <button class="retry-link" @click="resetQuiz">{{ locale.quiz.retake }}</button>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { createSession, submitQuiz } from '../services/api'
import type { QuizAnswers } from '../types/trip'
import { clearAccommodationState } from '../utils/accommodation'
import { useLocale } from '../composables/useLocale'
import LangToggle from '../components/LangToggle.vue'

const router = useRouter()
const { lang, locale } = useLocale()

const phase = ref<'quiz' | 'result'>('quiz')
const currentQ = ref(1)
const selectedAnswer = ref<string>('')
const answers = ref<Record<string, string>>({})
const loading = ref(false)
const errorText = ref('')
const gene = ref('')
const mascot = ref('')
const backendGeneDescription = ref('')
const sessionId = ref('')

const currentQuestion = computed(() => locale.value.quiz.questions[currentQ.value - 1])

const displayGeneName = computed(() => locale.value.quiz.genes[gene.value] || gene.value)

const displayGeneDescription = computed(() => {
  return locale.value.quiz.geneDescriptions[gene.value] || backendGeneDescription.value
})

onMounted(async () => {
  try {
    const session = await createSession()
    sessionId.value = session.session_id
    localStorage.setItem('chitogo_session_id', session.session_id)
    localStorage.removeItem('chitogo_gene')
    localStorage.removeItem('chitogo_mascot')
    clearAccommodationState()
  } catch {
    errorText.value = locale.value.quiz.sessionError
  }
})

function selectAnswer(key: string) {
  selectedAnswer.value = key
}

async function nextQuestion() {
  if (!selectedAnswer.value) return
  answers.value[`Q${currentQ.value}`] = selectedAnswer.value
  selectedAnswer.value = ''

  if (currentQ.value < 9) {
    currentQ.value++
    return
  }

  loading.value = true
  errorText.value = ''
  try {
    const result = await submitQuiz(sessionId.value, answers.value as QuizAnswers)
    gene.value = result.travel_gene
    mascot.value = result.mascot
    backendGeneDescription.value = result.gene_description
    localStorage.setItem('chitogo_gene', result.travel_gene)
    localStorage.setItem('chitogo_mascot', result.mascot)
    phase.value = 'result'
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    errorText.value = e?.response?.data?.detail ?? locale.value.quiz.submitError
  } finally {
    loading.value = false
  }
}

function onMascotImgError(e: Event) {
  (e.target as HTMLImageElement).style.display = 'none'
}

function goToSetup() {
  router.push('/setup')
}
function resetQuiz() {
  phase.value = 'quiz'
  currentQ.value = 1
  answers.value = {}
  selectedAnswer.value = ''
  errorText.value = ''
}
</script>

<style scoped>
.quiz-container {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #f0f4ff;
  padding: 20px;
}

.quiz-card, .result-card {
  background: white;
  border-radius: 20px;
  padding: 40px 32px;
  max-width: 480px;
  width: 100%;
  box-shadow: 0 8px 32px rgba(77, 104, 191, 0.12);
}

.card-topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.card-topbar .progress-bar {
  flex: 1;
  margin-bottom: 0;
}

.result-topbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.progress-bar {
  height: 6px;
  background: #e2e8f0;
  border-radius: 3px;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  background: #4d68bf;
  border-radius: 3px;
  transition: width 0.3s;
}

.progress-label {
  text-align: right;
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 24px;
}

.question-text {
  font-size: 20px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 24px;
  line-height: 1.5;
}

.options {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 28px;
}

.option-btn {
  padding: 14px 20px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  background: white;
  color: #334155;
  font-size: 15px;
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s;
}

.option-btn:hover {
  border-color: #4d68bf;
  background: #f0f4ff;
}

.option-btn.selected {
  border-color: #4d68bf;
  background: #4d68bf;
  color: white;
}

.next-btn {
  width: 100%;
  padding: 14px;
  background: #4d68bf;
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 16px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.next-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.next-btn:not(:disabled):hover {
  background: #3d55a0;
}

.error {
  margin-top: 12px;
  color: #ef4444;
  font-size: 14px;
  text-align: center;
}

/* Result card */
.result-card {
  text-align: center;
  animation: slideUp 0.6s ease-out;
}

.result-header {
  margin-bottom: 24px;
}

.mascot-container {
  border-radius: 12px;
  width: 100%;
  max-width: 320px;
  height: auto;
  aspect-ratio: 2336 / 1824;
  margin: 0 auto 20px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #f0f4ff;
  overflow: hidden;
}

.mascot-animate {
  width: 100%;
  height: 100%;
  object-fit: cover;
  animation: float 3s ease-in-out infinite;
}

.result-subtitle {
  font-size: 14px;
  color: #94a3b8;
  margin-bottom: 4px;
}

.gene-title {
  font-size: 28px;
  font-weight: 800;
  color: #4d68bf;
  letter-spacing: 1px;
}

.description-box {
  background: #f8fafc;
  border-radius: 16px;
  padding: 20px;
  margin-bottom: 32px;
  border-left: 4px solid #4d68bf;
  text-align: left;
}

.gene-desc {
  color: #475569;
  font-size: 15px;
  line-height: 1.8;
  margin: 0;
  white-space: pre-wrap;
}

.start-btn {
  width: 100%;
  padding: 14px;
  background: #4d68bf;
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 16px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
}

.start-btn:hover {
  background: #3d55a0;
}

.retry-link {
  display: block;
  margin: 16px auto 0;
  background: none;
  border: none;
  color: #94a3b8;
  font-size: 14px;
  cursor: pointer;
  text-decoration: underline;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

@media (max-width: 767px) {
  .quiz-container {
    align-items: flex-start;
    padding: 16px 12px 80px;
  }

  .quiz-card, .result-card {
    padding: 24px 16px;
    border-radius: 16px;
  }

  .question-text {
    font-size: 17px;
  }

  .option-btn {
    padding: 12px 16px;
    font-size: 14px;
    min-height: 48px;
    text-align: left;
  }

  .next-btn,
  .start-btn {
    min-height: 48px;
  }

  .mascot-container {
    max-width: 240px;
  }
}
</style>
