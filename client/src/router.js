import { createRouter, createWebHistory } from 'vue-router'
import Kiosk from './views/Kiosk.vue'
import PatientJoin from './views/PatientJoin.vue'
import Receptionist from './views/Receptionist.vue'

const routes = [
  { path: '/', component: Kiosk },
  { path: '/join/:token', component: PatientJoin, props: true },
  { path: '/receptionist/:sessionId', component: Receptionist, props: true },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
