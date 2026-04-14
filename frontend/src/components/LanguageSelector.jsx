import React from 'react';

const LANGUAGES = {
  en: '🇺🇸 English',
  zh: '🇨🇳 Chinese (Simplified)',
  'zh-tw': '🇹🇼 Chinese (Traditional)',
  ja: '🇯🇵 Japanese',
  ko: '🇰🇷 Korean',
  fr: '🇫🇷 French',
  de: '🇩🇪 German',
  es: '🇪🇸 Spanish',
  pt: '🇧🇷 Portuguese',
  ru: '🇷🇺 Russian',
  ar: '🇸🇦 Arabic',
  hi: '🇮🇳 Hindi',
  it: '🇮🇹 Italian',
  nl: '🇳🇱 Dutch',
  pl: '🇵🇱 Polish',
  tr: '🇹🇷 Turkish',
  vi: '🇻🇳 Vietnamese',
  th: '🇹🇭 Thai',
};

export function LanguageSelector({ label, value, onChange, exclude }) {
  return (
    <div className="lang-selector">
      <label className="lang-label">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="lang-select"
      >
        {Object.entries(LANGUAGES)
          .filter(([code]) => code !== exclude)
          .map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
      </select>
    </div>
  );
}
