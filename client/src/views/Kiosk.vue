<template>
  <div class="page">
    <AppHeader />
    <main class="kiosk">
      <div class="card">
        <template v-if="!session">
          <h1>Reception desk</h1>
          <p class="helper">Start a new interpreted conversation with a patient.</p>
          <button type="button" class="btn btn-primary new-patient" @click="startSession">
            New Patient
          </button>
        </template>

        <div v-else class="session-panel">
          <QRCodeDisplay :qr-url="session.qr_url" :join-url="session.patient_join_url" />
          <ConnectionStatus :state="status.state" />
          <button type="button" class="btn btn-secondary" @click="cancelSession">Cancel</button>
        </div>
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

const router = useRouter()
const session = ref(null)
const { status, connectAsReceptionist, disconnect } = useSession()

async function startSession() {
  session.value = await api.createSession()
  connectAsReceptionist(session.value.session_id, session.value.receptionist_secret)
}

function cancelSession() {
  disconnect()
  session.value = null
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
</style>
