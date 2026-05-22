import { useEffect, useRef } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

/**
 * Hook that polls for browser push notifications and shows them via Notification API.
 * No external service needed — uses the standard Web Notification API.
 */
export function useBrowserPush() {
  const intervalRef = useRef(null);
  const permissionRef = useRef(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().then(p => { permissionRef.current = p; });
    } else {
      permissionRef.current = window.Notification ? Notification.permission : 'denied';
    }

    const poll = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/browser-push/pending`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return;
        const data = await res.json();
        const notifs = data.notifications || [];

        if (notifs.length > 0 && permissionRef.current === 'granted') {
          for (const n of notifs) {
            try {
              new Notification(n.title || 'NeoNoble Ramp', {
                body: n.body || '',
                icon: '/favicon.ico',
                tag: n.created_at,
              });
            } catch (e) { /* SW only in some browsers */ }
          }
          // Mark as delivered
          await fetch(`${BACKEND_URL}/api/browser-push/delivered`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          });
        }
      } catch (e) { /* silent */ }
    };

    // Poll every 15 seconds
    intervalRef.current = setInterval(poll, 15000);
    // Initial poll after 3 seconds
    setTimeout(poll, 3000);

    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);
}
