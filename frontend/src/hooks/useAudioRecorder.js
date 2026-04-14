import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * useAudioRecorder
 * Captures microphone audio via MediaRecorder, down-samples to 16 kHz mono
 * Int16 PCM, and calls onChunk(arrayBuffer) periodically.
 */
export function useAudioRecorder({ onChunk, chunkIntervalMs = 1000 }) {
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const processorRef = useRef(null);
  const [recording, setRecording] = useState(false);
  const [permissionError, setPermissionError] = useState(null);

  const start = useCallback(async () => {
    setPermissionError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true },
        video: false,
      });
      streamRef.current = stream;

      // Use AudioContext + ScriptProcessor for reliable PCM extraction across browsers.
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000,
      });
      audioCtxRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);
      // ScriptProcessorNode is deprecated but has the broadest browser support
      // (including older iOS/Android WebViews). An AudioWorklet replacement would
      // require a separate worker file and HTTPS on all platforms.
      const bufferSize = 4096;
      const processor = audioCtx.createScriptProcessor(bufferSize, 1, 1);
      processorRef.current = processor;

      let pcmBuffer = [];
      let lastFlush = Date.now();

      processor.onaudioprocess = (e) => {
        const float32 = e.inputBuffer.getChannelData(0);
        // Convert float32 → int16
        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
          const s = Math.max(-1, Math.min(1, float32[i]));
          int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        pcmBuffer.push(int16.buffer);

        const now = Date.now();
        if (now - lastFlush >= chunkIntervalMs) {
          lastFlush = now;
          // Concatenate accumulated PCM buffers
          const totalLen = pcmBuffer.reduce((a, b) => a + b.byteLength, 0);
          const merged = new Uint8Array(totalLen);
          let offset = 0;
          for (const buf of pcmBuffer) {
            merged.set(new Uint8Array(buf), offset);
            offset += buf.byteLength;
          }
          pcmBuffer = [];
          onChunk?.(merged.buffer);
        }
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);

      setRecording(true);
    } catch (err) {
      setPermissionError(err.message || 'Microphone access denied');
    }
  }, [onChunk, chunkIntervalMs]);

  const stop = useCallback(() => {
    processorRef.current?.disconnect();
    processorRef.current = null;
    audioCtxRef.current?.close();
    audioCtxRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setRecording(false);
  }, []);

  useEffect(() => () => stop(), [stop]);

  return { recording, start, stop, permissionError };
}
