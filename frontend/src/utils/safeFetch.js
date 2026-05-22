/**
 * Universal safe fetch utilities for NeoNoble Ramp.
 * Prevents "body stream already read" errors by using XMLHttpRequest.
 */

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

export function getAuthHeaders() {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/**
 * XHR-based GET request — immune to body stream errors.
 */
export function xhrGet(url, options = {}) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    const headers = options.headers || getAuthHeaders();
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    if (options.signal) {
      options.signal.addEventListener('abort', () => {
        xhr.abort();
        resolve({ detail: 'Aborted' });
      });
    }
    xhr.onload = () => {
      try { resolve(JSON.parse(xhr.responseText)); }
      catch { resolve({ detail: `Errore ${xhr.status}` }); }
    };
    xhr.onerror = () => resolve({ detail: 'Connessione di rete fallita' });
    xhr.send();
  });
}

/**
 * XHR-based POST request — immune to body stream errors.
 */
export function xhrPost(url, body, options = {}) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open(options.method || 'POST', url, true);
    const headers = options.headers || getAuthHeaders();
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.onload = () => {
      let data;
      try { data = JSON.parse(xhr.responseText); }
      catch { data = { detail: `Errore ${xhr.status}` }; }
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data });
    };
    xhr.onerror = () => resolve({ ok: false, status: 0, data: { detail: 'Connessione di rete fallita' } });
    xhr.send(typeof body === 'string' ? body : JSON.stringify(body));
  });
}

/**
 * XHR-based generic fetch — drop-in replacement for fetch().json()
 */
export function xhrFetch(url, options = {}) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open(options.method || 'GET', url, true);
    if (options.headers) {
      Object.entries(options.headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    }
    if (options.signal) {
      options.signal.addEventListener('abort', () => {
        xhr.abort();
        resolve({});
      });
    }
    xhr.onload = () => {
      try { resolve(JSON.parse(xhr.responseText)); } catch { resolve({}); }
    };
    xhr.onerror = () => resolve({});
    xhr.send(options.body || null);
  });
}

export { BACKEND_URL };
