// Runs on the audio rendering thread. Posts raw Float32 mic samples to the main thread --
// no interpretation of the audio happens here, just capture.
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0]?.[0]
    if (channel && channel.length > 0) {
      this.port.postMessage(channel.slice())
    }
    return true
  }
}

registerProcessor('pcm-capture-processor', PcmCaptureProcessor)
