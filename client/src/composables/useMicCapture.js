// Captures microphone audio and encodes it as 16-bit PCM chunks. This is a mic-capture
// utility only -- it does no speech recognition, translation, or synthesis. The silence
// timer decides *when* to stop sending audio (a UX safety net for push-to-talk), it does
// not interpret what was said.

import { createNoiseGraph } from '../audio/hospitalNoise.js'

const TARGET_SAMPLE_RATE = 16000
const CHUNK_FLUSH_MS = 200
const SILENCE_RMS_THRESHOLD = 0.01
const SILENCE_AUTO_STOP_MS = 1800

function floatTo16BitPCM(floatSamples) {
  const buffer = new ArrayBuffer(floatSamples.length * 2)
  const view = new DataView(buffer)
  for (let i = 0; i < floatSamples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, floatSamples[i]))
    view.setInt16(i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
  }
  return buffer
}

function rms(floatSamples) {
  let sum = 0
  for (let i = 0; i < floatSamples.length; i++) {
    sum += floatSamples[i] * floatSamples[i]
  }
  return Math.sqrt(sum / floatSamples.length)
}

export function useMicCapture({ onChunk, onSilenceTimeout, getNoiseLevel } = {}) {
  let audioContext = null
  let sourceNode = null
  let workletNode = null
  let stream = null
  let noiseGraph = null
  let pendingSamples = []
  let pendingSampleCount = 0
  let flushTimer = null
  let silenceTimer = null

  function flushPending() {
    if (pendingSampleCount === 0) return
    const merged = new Float32Array(pendingSampleCount)
    let offset = 0
    for (const chunk of pendingSamples) {
      merged.set(chunk, offset)
      offset += chunk.length
    }
    pendingSamples = []
    pendingSampleCount = 0
    onChunk?.(floatTo16BitPCM(merged))
  }

  function armSilenceTimer() {
    clearTimeout(silenceTimer)
    silenceTimer = setTimeout(() => onSilenceTimeout?.(), SILENCE_AUTO_STOP_MS)
  }

  async function start() {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } })
    audioContext = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE })
    const workletUrl = new URL('../worklets/pcm-capture-processor.js', import.meta.url)
    await audioContext.audioWorklet.addModule(workletUrl)

    sourceNode = audioContext.createMediaStreamSource(stream)
    workletNode = new AudioWorkletNode(audioContext, 'pcm-capture-processor')

    // Testing aid: optionally mix synthesized hospital-reception noise in with the real mic
    // signal before it reaches the worklet, so noise robustness can be exercised with real
    // speech rather than only offline. With noise enabled, ambient level alone can sit above
    // SILENCE_RMS_THRESHOLD, so the auto-stop timer may not fire -- release the button
    // manually in that case.
    const level = getNoiseLevel?.() ?? 'off'
    const mixNode = audioContext.createGain()
    sourceNode.connect(mixNode)
    if (level !== 'off') {
      noiseGraph = createNoiseGraph(audioContext, level)
      noiseGraph.output.connect(mixNode)
      // Also route to the speakers -- otherwise the noise silently affects only the audio
      // sent for transcription, with nothing audible to confirm it's actually on.
      noiseGraph.output.connect(audioContext.destination)
    }

    workletNode.port.onmessage = (event) => {
      const samples = event.data
      pendingSamples.push(samples)
      pendingSampleCount += samples.length
      if (rms(samples) >= SILENCE_RMS_THRESHOLD) {
        armSilenceTimer()
      } else if (!silenceTimer) {
        armSilenceTimer()
      }
    }

    mixNode.connect(workletNode)
    flushTimer = setInterval(flushPending, CHUNK_FLUSH_MS)
    armSilenceTimer()
  }

  function stop() {
    clearInterval(flushTimer)
    clearTimeout(silenceTimer)
    flushTimer = null
    silenceTimer = null
    flushPending()
    workletNode?.disconnect()
    sourceNode?.disconnect()
    noiseGraph?.stop()
    noiseGraph = null
    stream?.getTracks().forEach((track) => track.stop())
    audioContext?.close()
    audioContext = null
  }

  return { start, stop }
}
