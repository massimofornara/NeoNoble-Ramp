import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Bell, X, Check, AlertTriangle, TrendingUp, Shield, Settings } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` });

const ICONS = {
  trade: TrendingUp,
  margin: AlertTriangle,
  kyc: Shield,
  security: Shield,
  system: Settings,
};
const COLORS = {
  info: 'text-blue-400',
  warning: 'text-yellow-400',
  critical: 'text-red-400',
};

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unread, setUnread] = useState(0);
  const ref = useRef(null);

  const fetchNotifs = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/notifications/?limit=20`, { headers: headers() });
      const data = await res.json();
      setNotifications(data.notifications || []);
      setUnread(data.unread_count || 0);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetchNotifs(); const iv = setInterval(fetchNotifs, 30000); return () => clearInterval(iv); }, [fetchNotifs]);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const markRead = async (id) => {
    await fetch(`${BACKEND_URL}/api/notifications/read/${id}`, { method: 'POST', headers: headers() });
    fetchNotifs();
  };

  const markAllRead = async () => {
    await fetch(`${BACKEND_URL}/api/notifications/read-all`, { method: 'POST', headers: headers() });
    fetchNotifs();
  };

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(!open)} data-testid="notification-bell" className="relative p-2 hover:bg-zinc-800 rounded-lg transition-colors">
        <Bell className="w-5 h-5 text-zinc-400" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 rounded-full text-white text-[9px] font-bold flex items-center justify-center" data-testid="notif-badge">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl z-50 overflow-hidden" data-testid="notif-panel">
          <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
            <span className="text-white font-bold text-sm">Notifiche</span>
            {unread > 0 && (
              <button onClick={markAllRead} className="text-purple-400 text-xs hover:text-purple-300">Segna tutte lette</button>
            )}
          </div>
          <div className="max-h-72 overflow-y-auto divide-y divide-zinc-800/50">
            {notifications.length === 0 && (
              <div className="py-8 text-center text-zinc-500 text-sm">Nessuna notifica</div>
            )}
            {notifications.map(n => {
              const Icon = ICONS[n.type] || Settings;
              return (
                <div key={n.id} className={`px-4 py-3 hover:bg-zinc-800/30 cursor-pointer ${!n.read ? 'bg-purple-500/5' : ''}`}
                  onClick={() => !n.read && markRead(n.id)}>
                  <div className="flex gap-2">
                    <Icon className={`w-4 h-4 mt-0.5 ${COLORS[n.severity] || 'text-zinc-400'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-zinc-200 text-xs font-medium">{n.title}</div>
                      <div className="text-zinc-500 text-[10px] truncate">{n.message}</div>
                      <div className="text-zinc-600 text-[9px] mt-0.5">
                        {n.created_at ? new Date(n.created_at).toLocaleString('it-IT') : ''}
                      </div>
                    </div>
                    {!n.read && <div className="w-2 h-2 rounded-full bg-purple-500 mt-1" />}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
