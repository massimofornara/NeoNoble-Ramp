import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

function getSessionId() {
  let sid = sessionStorage.getItem('nn_session');
  if (!sid) {
    sid = Math.random().toString(36).substring(2) + Date.now().toString(36);
    sessionStorage.setItem('nn_session', sid);
  }
  return sid;
}

export function usePageTracking() {
  const location = useLocation();
  const lastPath = useRef('');

  useEffect(() => {
    if (location.pathname === lastPath.current) return;
    lastPath.current = location.pathname;

    fetch(`${BACKEND_URL}/api/analytics/track`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        page: location.pathname,
        referrer: document.referrer || null,
        session_id: getSessionId()
      })
    }).catch(() => {});
  }, [location.pathname]);
}
