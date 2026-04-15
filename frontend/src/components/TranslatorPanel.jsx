import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAudioRecorder } from '../hooks/useAudioRecorder';
import { useTranslatorWS } from '../hooks/useTranslatorWS';
import { LanguageSelector } from './LanguageSelector';

const MAX_HISTORY = 1000;

export function TranslatorPanel() {
  const [sourceLang, setSourceLang] = useState('en');
  const [targetLang, setTargetLang] = useState('zh');
  const [enableTTS, setEnableTTS] = useState(true);
  const [useSystemAudio, setUseSystemAudio] = useState(false);
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
      let next = [...prev];
      
      // Update any previous corrections returned by the AI
      if (msg.updates && Array.isArray(msg.updates)) {
        for (const update of msg.updates) {
          const idx = next.findIndex(x => x.id === update.id);
          if (idx !== -1) {
            // Re-render that item with corrected translation and maybe a flag
            next[idx] = { ...next[idx], translation: update.translation, corrected: true };
          }
        }
      }

      const entry = {
        id: msg.id || Date.now(), // Fallback to Date.now() if no ID
        source: msg.source_text,
        translation: msg.text,
        sourceLang: sourceLang,
        targetLang: targetLang,
      };
      
      next = [entry, ...next].slice(0, MAX_HISTORY);
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
    useAudioRecorder({ onChunk: handleChunk, chunkIntervalMs: 800, useSystemAudio });

  // ── Sync config changes ─────────────────────────────────────────────────
  useEffect(() => {
    if (connected) {
      sendConfig({ source_lang: sourceLang, target_lang: targetLang, enable_tts: enableTTS });
    }
  }, [connected, sourceLang, targetLang, enableTTS, sendConfig]);

  // ── Auto-scroll ─────────────────────────────────────────────────────────
  useEffect(() => {
    // 因为最新的在最上面，所以每次更新记录时自动滚动到顶部
    const historyEl = document.querySelector('.history');
    if (historyEl) {
      historyEl.scrollTop = 0;
    }
  }, [history]);

  // ── Start / stop recording ──────────────────────────────────────────────
  const handleToggleRecording = async () => {
    if (recording) {
      flush();
      stopRecording();
      if (connected) disconnect();
    } else {
      connect();
      // 显式将当前状态传给 startRecording
      await startRecording(useSystemAudio);
    }
  };

  const handleSwapLanguages = () => {
    setSourceLang(targetLang);
    setTargetLang(sourceLang);
  };

  const handleClearHistory = () => {
    if (window.confirm('Clear all translation history?')) {
      setHistory([]);
    }
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
        <button 
          className="clear-btn" 
          onClick={handleClearHistory} 
          title="Clear History"
          disabled={history.length === 0}
        >
          🗑️
        </button>
        <LanguageSelector
          label="To"
          value={targetLang}
          onChange={setTargetLang}
          exclude={sourceLang}
        />
      </div>

      {/* ── Settings Row ── */}
      <div className="settings-row">
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={enableTTS}
            onChange={(e) => setEnableTTS(e.target.checked)}
          />
          <span>Text-to-Speech (TTS)</span>
        </label>
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={useSystemAudio}
            onChange={(e) => setUseSystemAudio(e.target.checked)}
          />
          <span title="Capture YouTube / Chrome Audio instead of Mic">Capture System Audio</span>
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
          <div key={item.id} className={`history-item ${item.corrected ? "corrected" : ""}`}>
            <div className="history-source-row">
              <span className="source-label">{item.sourceLang.toUpperCase()}:</span>
              <p className="history-source">{item.source}</p>
            </div>
            <div className="history-translation-row">
              <span className="target-label" title={item.corrected ? "AI Self-Corrected this line" : ""}>
                {item.corrected ? "✨ COR:" : `${item.targetLang.toUpperCase()}:`}
              </span>
              <p className="history-translation">{item.translation}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
