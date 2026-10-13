import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import SubmitView from './views/SubmitView.vue'
import DiagnosisView from './views/DiagnosisView.vue'
import './style.css'

const router = createRouter({ history: createWebHashHistory(), scrollBehavior: () => ({ top: 0 }), routes: [
  { path: '/', component: SubmitView },
  { path: '/diagnoses/:id?', component: DiagnosisView },
] })
createApp(App).use(router).use(ElementPlus).mount('#app')
