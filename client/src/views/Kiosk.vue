<template>
  <div class="kiosk">
    <h1>Hospital Reception Interpreter</h1>

    <button v-if="!session" type="button" class="new-patient" @click="startSession">
      New Patient
    </button>

    <div v-else class="session-panel">
      <QRCodeDisplay :qr-url="session.qr_url" :join-url="session.patient_join_url" />
      <ConnectionStatus :state="status.state" />
      <button type="button" class="cancel" @click="cancelSession">Cancel</button>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api.js'
import { useSession } from '../composables/useSession.js'
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
.kiosk {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2rem;
  padding: 2rem;
  text-align: center;
}
.new-patient {
  padding: 1.5rem 3rem;
  font-size: 1.5rem;
  font-weight: 600;
  border-radius: 1rem;
  border: none;
  background: var(--color-accent);
  color: white;
  cursor: pointer;
}
.session-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
}
.cancel {
  padding: 0.5rem 1.25rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-muted);
  cursor: pointer;
}
</style>
