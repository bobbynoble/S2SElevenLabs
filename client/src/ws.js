// The only module that touches the raw WebSocket API. Everything else talks to
// connectPatientSocket / connectReceptionistSocket.

function wsOrigin() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

function createSocket(path, { onMessage, onClose } = {}) {
  const socket = new WebSocket(`${wsOrigin()}${path}`)
  socket.binaryType = 'arraybuffer'

  socket.addEventListener('message', (event) => {
    if (typeof event.data === 'string') {
      onMessage?.(JSON.parse(event.data), null)
    } else {
      onMessage?.(null, event.data)
    }
  })
  socket.addEventListener('close', () => onClose?.())

  return {
    sendJson(payload) {
      socket.send(JSON.stringify(payload))
    },
    sendBinary(buffer) {
      socket.send(buffer)
    },
    close() {
      socket.close()
    },
  }
}

export function connectPatientSocket(token, handlers) {
  return createSocket(`/ws/patient/${token}`, handlers)
}

export function connectReceptionistSocket(sessionId, secret, handlers) {
  return createSocket(`/ws/receptionist/${sessionId}?secret=${encodeURIComponent(secret)}`, handlers)
}
