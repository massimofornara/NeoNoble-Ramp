import React, { createContext, useContext, useState, useCallback } from 'react';
import translations from './translations';

const I18nContext = createContext();

export function I18nProvider({ children }) {
  const [locale, setLocale] = useState(() => localStorage.getItem('neonoble_lang') || 'it');

  const changeLocale = useCallback((newLocale) => {
    setLocale(newLocale);
    localStorage.setItem('neonoble_lang', newLocale);
  }, []);

  const t = useCallback(
    (key, fallback) => {
      const dict = translations[locale] || translations.it;
      return dict[key] || fallback || key;
    },
    [locale],
  );

  return (
    <I18nContext.Provider value={{ locale, changeLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within I18nProvider');
  return ctx;
}
