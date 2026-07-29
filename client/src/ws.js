// The only module that touches the raw WebSocket API. Everything else talks to
// connectPatientSocket / connectReceptionistSocket.

function wsOrigin() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

function createSocket(path, { onMessage, onClose } = {}) {
  const socket = new WebSocket(`${wsOrigin()}${path}`)
  socket.binaryType = 'arraybuffer'

  // Messages sent before the handshake completes are queued rather than thrown away --
  // send() throws synchronously while the socket is still CONNECTING, and callers (e.g. the
  // 'join' message fired the instant a patient picks a language) can easily race the handshake
  // over a real network like the ngrok tunnel.
  const pending = []
  let open = false

  socket.addEventListener('open', () => {
    open = true
    for (const payload of pending) socket.send(payload)
    pending.length = 0
  })
  socket.addEventListener('message', (event) => {
    if (typeof event.data === 'string') {
      onMessage?.(JSON.parse(event.data), null)
    } else {
      onMessage?.(null, event.data)
    }
  })
  socket.addEventListener('close', () => onClose?.())

  function send(payload) {
    if (open) {
      socket.send(payload)
    } else {
      pending.push(payload)
    }
  }

  return {
    sendJson(payload) {
      send(JSON.stringify(payload))
    },
    sendBinary(buffer) {
      send(buffer)
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
