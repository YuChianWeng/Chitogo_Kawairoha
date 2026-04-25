import { createRouter, createWebHistory, type RouteLocationNormalized, type NavigationGuardNext } from 'vue-router'
import QuizPage from '../pages/QuizPage.vue'
import AccommodationPage from '../pages/AccommodationPage.vue'
import SetupPage from '../pages/SetupPage.vue'
import TripPage from '../pages/TripPage.vue'
import SummaryPage from '../pages/SummaryPage.vue'
import { readAccommodationState } from '../utils/accommodation'

function requireSession(
  _to: RouteLocationNormalized,
  _from: RouteLocationNormalized,
  next: NavigationGuardNext
) {
  if (!localStorage.getItem('chitogo_session_id')) {
    next('/quiz')
  } else {
    next()
  }
}

function requireSessionAndGene(
  _to: RouteLocationNormalized,
  _from: RouteLocationNormalized,
  next: NavigationGuardNext
) {
  if (!localStorage.getItem('chitogo_session_id') || !localStorage.getItem('chitogo_gene')) {
    next('/quiz')
  } else {
    next()
  }
}

function requireAccommodationStep(
  _to: RouteLocationNormalized,
  _from: RouteLocationNormalized,
  next: NavigationGuardNext
) {
  if (!localStorage.getItem('chitogo_session_id') || !localStorage.getItem('chitogo_gene')) {
    next('/quiz')
  } else if (!readAccommodationState()) {
    next('/accommodation')
  } else {
    next()
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/quiz' },
    { path: '/quiz', component: QuizPage },
    { path: '/accommodation', component: AccommodationPage, beforeEnter: requireSessionAndGene },
    { path: '/setup', component: SetupPage, beforeEnter: requireAccommodationStep },
    { path: '/trip', component: TripPage, beforeEnter: requireSessionAndGene },
    { path: '/summary', component: SummaryPage, beforeEnter: requireSession },
  ],
})

export default router
