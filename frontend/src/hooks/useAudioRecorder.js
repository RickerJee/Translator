import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * useAudioRecorder
 * Captures microphone audio via MediaRecorder, down-samples to 16 kHz mono
 * Int16 PCM, and calls onChunk(arrayBuffer) periodically.
 */
export function useAudioRecorder({ onChunk, chunkIntervalMs = 1000, useSystemAudio = false }) {
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const processorRef = useRef(null);
  const [recording, setRecording] = useState(false);
  const [permissionError, setPermissionError] = useState(null);

  const start = useCallback(async (overriddenSystemAudio) => {
    setPermissionError(null);
    const activeUseSystemAudio = overriddenSystemAudio ?? useSystemAudio;
    try {
      let stream;
      if (activeUseSystemAudio) {
        // 简化参数以确保在 Edge/Chrome 中顺利弹出窗口
        stream = await navigator.mediaDevices.getDisplayMedia({
          video: true,
          audio: true
        });

        // 检查音频轨道
        if (stream.getAudioTracks().length === 0) {
          stream.getTracks().forEach(t => t.stop());
          throw new Error("No audio track found. Please ensure 'Share audio' is checked in the dialog.");
        }
      } else {
        // 传统的麦克风捕获
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true },
          video: false,
        });
      }
      streamRef.current = stream;

      // 如果是系统音频，当用户点击浏览器的“停止分享”按钮时，自动停止录音
      stream.oninactive = () => {
        console.log("Stream became inactive, stopping...");
        stop();
      };

      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000,
      });
      audioCtxRef.current = audioCtx;

      // ScriptProcessorNode is deprecated but has the broadest browser support
      // (including older iOS/Android WebViews). An AudioWorklet replacement would
      // require a separate worker file and HTTPS on all platforms.
      // NOTE: Silero VAD requires specific chunk sizes (512, 1024, or 1536 for 16kHz).
      const bufferSize = 512;
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
        
        // Immediate send for Silero VAD (which needs 512 sample chunks)
        onChunk?.(int16.buffer);
      };

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(processor);
      // 必须连接到 destination 否则 Chrome 等浏览器可能不会触发 onaudioprocess
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
