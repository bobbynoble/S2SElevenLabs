<template>
  <div class="page">
    <AppHeader />
    <main class="kiosk">
      <div class="card" :class="{ wide: phase === 'kiosk_flow' }">
        <template v-if="phase === 'idle'">
          <h1>Reception desk</h1>
          <p class="helper">Start a new interpreted conversation with a patient.</p>
          <button type="button" class="btn btn-primary new-patient" @click="phase = 'choosing_mode'">
            New Patient
          </button>
          <p class="trust-strip">Conversations are interpreted live and are not saved once the session ends.</p>
        </template>

        <template v-else-if="phase === 'choosing_mode'">
          <h1>How will the patient join?</h1>
          <p class="helper">Choose based on what's available at this desk.</p>
          <div class="mode-options">
            <button type="button" class="mode-option" @click="chooseMode('kiosk')">
              <span class="mode-title">This tablet</span>
              <span class="mode-detail">Patient uses this screen to pick their language and speak.</span>
            </button>
            <button type="button" class="mode-option" @click="chooseMode('qr')">
              <span class="mode-title">Patient's own phone</span>
              <span class="mode-detail">Show a QR code for the patient to scan and join from their phone.</span>
            </button>
          </div>
          <button type="button" class="btn btn-secondary" @click="phase = 'idle'">Back</button>
        </template>

        <div v-else-if="phase === 'qr_flow'" class="session-panel">
          <QRCodeDisplay :qr-url="session.qr_url" :join-url="session.patient_join_url" />
          <ConnectionStatus :state="status.state" />
          <button type="button" class="btn btn-secondary" @click="cancelSession">Cancel</button>
        </div>

        <KioskConversation v-else-if="phase === 'kiosk_flow'" :session="session" @end="resetToIdle" />
      </div>
    </main>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api.js'
import { useSession } from '../composables/useSession.js'
import AppHeader from '../components/AppHeader.vue'
import QRCodeDisplay from '../components/QRCodeDisplay.vue'
import ConnectionStatus from '../components/ConnectionStatus.vue'
import KioskConversation from './KioskConversation.vue'

const router = useRouter()
const session = ref(null)
const phase = ref('idle')
const { status, connectAsReceptionist, disconnect } = useSession()

async function chooseMode(mode) {
  session.value = await api.createSession()
  if (mode === 'qr') {
    connectAsReceptionist(session.value.session_id, session.value.receptionist_secret)
    phase.value = 'qr_flow'
  } else {
    phase.value = 'kiosk_flow'
  }
}

function cancelSession() {
  disconnect()
  session.value = null
  phase.value = 'idle'
}

function resetToIdle() {
  session.value = null
  phase.value = 'idle'
}

watch(
  () => status.value.state,
  (state) => {
    if (state === 'patient_joined' && session.value) {
      router.push({
        path: `/receptionist/${session.value.session_id}`,
        query: { secret: session.value.receptionist_secret },
      })
    }
  }
)

onBeforeUnmount(() => disconnect())
</script>

<style scoped>
.page {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}
.kiosk {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
}
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  box-shadow: var(--shadow-card);
  padding: 2.5rem 2rem;
  max-width: 480px;
  width: 100%;
  text-align: center;
}
.card.wide {
  max-width: 720px;
}
.mode-options {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.mode-option {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 1.25rem 1.5rem;
  min-height: 64px;
  border-radius: 4px;
  border: 2px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  text-align: left;
  box-shadow: var(--shadow-card);
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.mode-option:hover {
  border-color: var(--color-primary);
}
.mode-title {
  font-size: 1.15rem;
  font-weight: 700;
}
.mode-detail {
  font-size: 0.9rem;
  color: var(--color-muted);
}
h1 {
  margin: 0 0 0.5rem;
  font-size: 1.75rem;
}
.helper {
  color: var(--color-muted);
  margin: 0 0 1.75rem;
  font-size: 1.05rem;
}
.new-patient {
  font-size: 1.2rem;
  padding: 1.25rem 2.5rem;
}
.session-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
}
.trust-strip {
  margin: 1.25rem 0 0;
  font-size: 0.85rem;
  color: var(--color-muted);
}
</style>
