import { createRouter, createWebHashHistory } from 'vue-router'
import { clearSession, loadPublicConfig, loadSession, session } from '../composables/useSession'
import LoginView from '../views/LoginView.vue'
import CourseView from '../views/CourseView.vue'
import CourseDetailView from '../views/CourseDetailView.vue'
import SubmitView from '../views/SubmitView.vue'
import DiagnosisView from '../views/DiagnosisView.vue'
import LearningView from '../views/LearningView.vue'
import QuizView from '../views/QuizView.vue'
import LearningReportView from '../views/LearningReportView.vue'
import TeacherDashboardView from '../views/TeacherDashboardView.vue'
import NotFoundView from '../views/NotFoundView.vue'
export const router = createRouter({
  history: createWebHashHistory(), scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/', redirect: '/courses' },
    { path: '/login', component: LoginView },
    { path: '/courses', component: CourseView, meta: { auth: true } },
    { path: '/courses/:id', component: CourseDetailView, meta: { auth: true } },
    { path: '/teacher/courses/:id', component: CourseDetailView, meta: { auth: true, teacher: true } },
    { path: '/courses/:id/learn', component: LearningView, meta: { auth: true } },
    { path: '/courses/:id/quiz', component: QuizView, meta: { auth: true } },
    { path: '/courses/:id/report', component: LearningReportView, meta: { auth: true } },
    { path: '/teacher/courses/:id/dashboard', component: TeacherDashboardView, meta: { auth: true, teacher: true } },
    { path: '/dev/submit', component: SubmitView, meta: { dev: true, auth: true, student: true } },
    { path: '/diagnoses/:id?', component: DiagnosisView, meta: { dev: true, auth: true, student: true } },
    { path: '/:pathMatch(.*)*', component: NotFoundView },
  ],
})
router.beforeEach(async to => {
  if (to.meta.dev) {
    await loadPublicConfig()
    if (!session.devEnabled) return '/courses'
  }
  if (to.meta.auth) {
    try { await loadSession() } catch { return { path: '/login', query: { unavailable: '1' } } }
    if (!session.user) return { path: '/login', query: { redirect: to.fullPath } }
    if (to.meta.teacher && session.user.role !== 'teacher') return '/courses'
    if (to.meta.student && session.user.role !== 'student') return '/courses'
  }
})
window.addEventListener('session-expired', () => {
  clearSession()
  if (router.currentRoute.value.meta.auth) void router.replace({ path: '/login', query: { expired: '1' } })
})
