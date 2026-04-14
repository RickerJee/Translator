import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAudioRecorder } from '../hooks/useAudioRecorder';
import { useTranslatorWS } from '../hooks/useTranslatorWS';
import { LanguageSelector } from './LanguageSelector';

const MAX_HISTORY = 50;

export function TranslatorPanel() {
  const [sourceLang, setSourceLang] = useState('en');
  const [targetLang, setTargetLang] = useState('zh');
  const [enableTTS, setEnableTTS] = useState(true);
  const [history, setHistory] = useState([]);
  const [liveTranscript, setLiveTranscript] = useState('');
  const [liveTranslation, setLiveTranslation] = useState('');
  const [wsStatus, setWsStatus] = useState('disconnected');
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);
  const audioQueue = useRef([]);
  const playingRef = useRef(false);

  // ── Audio playback queue ────────────────────────────────────────────────
  const playNextAudio = useCallback(() => {
    if (playingRef.current || audioQueue.current.length === 0) return;
    playingRef.current = true;
    const src = audioQueue.current.shift();
    const audio = new Audio(src);
    audio.onended = () => {
      playingRef.current = false;
      playNextAudio();
    };
    audio.onerror = () => {
      playingRef.current = false;
      playNextAudio();
    };
    audio.play().catch(() => {
      playingRef.current = false;
      playNextAudio();
    });
  }, []);

  // ── WebSocket callbacks ─────────────────────────────────────────────────
  const handleTranscript = useCallback((msg) => {
    setLiveTranscript(msg.text);
  }, []);

  const handleTranslation = useCallback((msg) => {
    setLiveTranslation(msg.text);
    setHistory((prev) => {
      const entry = {
        id: Date.now(),
        source: msg.source_text,
        translation: msg.text,
        sourceLang: sourceLang,
        targetLang: targetLang,
      };
      const next = [entry, ...prev].slice(0, MAX_HISTORY);
      return next;
    });
    setLiveTranscript('');
    setLiveTranslation('');

    if (msg.audio) {
      const blob = new Blob(
        [Uint8Array.from(atob(msg.audio), (c) => c.charCodeAt(0))],
        { type: 'audio/mpeg' }
      );
      const url = URL.createObjectURL(blob);
      audioQueue.current.push(url);
      playNextAudio();
    }
  }, [sourceLang, targetLang, playNextAudio]);

  const handleError = useCallback((msg) => setError(msg), []);
  const handleStatusChange = useCallback((s) => {
    setWsStatus(s);
    setError(null);
  }, []);

  const { connected, connect, disconnect, sendConfig, sendAudioChunk, flush } =
    useTranslatorWS({
      onTranscript: handleTranscript,
      onTranslation: handleTranslation,
      onError: handleError,
      onStatusChange: handleStatusChange,
    });

  // ── Audio recorder ──────────────────────────────────────────────────────
  const handleChunk = useCallback(
    (buffer) => {
      sendAudioChunk(buffer);
    },
    [sendAudioChunk]
  );

  const { recording, start: startRecording, stop: stopRecording, permissionError } =
    useAudioRecorder({ onChunk: handleChunk, chunkIntervalMs: 800 });

  // ── Sync config changes ─────────────────────────────────────────────────
  useEffect(() => {
    if (connected) {
      sendConfig({ source_lang: sourceLang, target_lang: targetLang, enable_tts: enableTTS });
    }
  }, [connected, sourceLang, targetLang, enableTTS, sendConfig]);

  // ── Auto-scroll ─────────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history]);

  // ── Start / stop recording ──────────────────────────────────────────────
  const handleToggleRecording = async () => {
    if (recording) {
      flush();
      stopRecording();
      if (connected) disconnect();
    } else {
      connect();
      await startRecording();
    }
  };

  const handleSwapLanguages = () => {
    setSourceLang(targetLang);
    setTargetLang(sourceLang);
  };

  const displayError = error || permissionError;

  return (
    <div className="panel">
      {/* ── Header ── */}
      <header className="panel-header">
        <span className="logo">🌐</span>
        <h1 className="panel-title">Realtime Translator</h1>
        <span className={`ws-badge ws-badge--${wsStatus}`}>
          {wsStatus === 'connected' ? '● Live' : '○ Offline'}
        </span>
      </header>

      {/* ── Language selector row ── */}
      <div className="lang-row">
        <LanguageSelector
          label="From"
          value={sourceLang}
          onChange={setSourceLang}
          exclude={targetLang}
        />
        <button className="swap-btn" onClick={handleSwapLanguages} title="Swap languages">
          ⇄
        </button>
        <LanguageSelector
          label="To"
          value={targetLang}
          onChange={setTargetLang}
          exclude={sourceLang}
        />
      </div>

      {/* ── TTS toggle ── */}
      <div className="tts-row">
        <label className="tts-label">
          <input
            type="checkbox"
            checked={enableTTS}
            onChange={(e) => setEnableTTS(e.target.checked)}
          />
          <span>Text-to-Speech (Azure)</span>
        </label>
      </div>

      {/* ── Mic button ── */}
      <div className="mic-area">
        <button
          className={`mic-btn${recording ? ' mic-btn--recording' : ''}`}
          onClick={handleToggleRecording}
          aria-label={recording ? 'Stop recording' : 'Start recording'}
        >
          {recording ? (
            <span className="mic-icon">■</span>
          ) : (
            <span className="mic-icon">🎙</span>
          )}
          <span className="mic-label">{recording ? 'Stop' : 'Speak'}</span>
        </button>
        {recording && <div className="pulse-ring" />}
      </div>

      {/* ── Live caption ── */}
      {(liveTranscript || liveTranslation) && (
        <div className="live-caption">
          {liveTranscript && (
            <p className="live-source">{liveTranscript}</p>
          )}
          {liveTranslation && (
            <p className="live-target">{liveTranslation}</p>
          )}
        </div>
      )}

      {/* ── Error banner ── */}
      {displayError && (
        <div className="error-banner" role="alert">
          ⚠ {displayError}
        </div>
      )}

      {/* ── History ── */}
      <div className="history">
        {history.length === 0 && !recording && (
          <p className="history-empty">Press <strong>Speak</strong> to start translating.</p>
        )}
        {history.map((item) => (
          <div key={item.id} className="history-item">
            <p className="history-source">{item.source}</p>
            <p className="history-translation">{item.translation}</p>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
