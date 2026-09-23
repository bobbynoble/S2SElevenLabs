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
    console.log(`[ws] connected: ${path}`)
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
  // No standard WebSocket API exposes *why* a connection failed -- the 'error' event carries
  // no detail (that's the browser's own choice, not something we can improve on here), but
  // without even this listener a connection that never opens fails completely silently: no
  // console output, no thrown exception, nothing -- messages just queue forever in `pending`.
  socket.addEventListener('error', () => {
    console.error(`[ws] connection error: ${path} (readyState=${socket.readyState})`)
  })
  socket.addEventListener('close', (event) => {
    console.log(`[ws] closed: ${path} (code=${event.code}, wasOpen=${open})`)
    // Without this, a socket that drops after a successful handshake (a real risk over a
    // mobile network through a tunnel, e.g. an idle timeout while someone lingers on the
    // language picker) leaves `open` stuck true forever. Every later send() would then call
    // socket.send() on an already-closed socket, which throws synchronously -- silently, as
    // an unhandled rejection inside the caller's async handler, with no visible sign anything
    // is wrong (a button's pressed/active state is separate local UI state, unrelated to
    // whether the underlying socket is still alive).
    open = false
    onClose?.()
  })

  function send(payload) {
    if (!open) {
      pending.push(payload)
      return
    }
    try {
      socket.send(payload)
    } catch (err) {
      // The 'close' event can lag behind the socket actually dying, so still guard the send
      // itself -- report at the source that the connection is gone instead of failing silently.
      console.error('WebSocket send failed -- connection is no longer open:', err)
      open = false
      onClose?.()
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
