import React, { useState, useEffect, useCallback, useRef } from 'react';
import toast, { Toaster } from 'react-hot-toast';
import {
  Bell,
  BellRing,
  Check,
  X,
  ChevronDown,
  Trash2,
  CheckCheck,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Settings,
  Plus
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

// Notification type icons and colors
const NOTIFICATION_STYLES = {
  order_filled: {
    icon: Check,
    color: 'text-green-400',
    bg: 'bg-green-500/10',
    border: 'border-green-500/30'
  },
  order_cancelled: {
    icon: X,
    color: 'text-yellow-400',
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30'
  },
  order_rejected: {
    icon: AlertCircle,
    color: 'text-red-400',
    bg: 'bg-red-500/10',
    border: 'border-red-500/30'
  },
  price_alert: {
    icon: TrendingUp,
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30'
  },
  deposit_received: {
    icon: DollarSign,
    color: 'text-green-400',
    bg: 'bg-green-500/10',
    border: 'border-green-500/30'
  },
  system: {
    icon: Bell,
    color: 'text-blue-400',
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30'
  },
  info: {
    icon: Bell,
    color: 'text-gray-400',
    bg: 'bg-gray-500/10',
    border: 'border-gray-500/30'
  }
};

// Toast notification component
export const showNotificationToast = (notification) => {
  const style = NOTIFICATION_STYLES[notification.type] || NOTIFICATION_STYLES.info;
  const Icon = style.icon;

  toast.custom((t) => (
    <div
      className={`${
        t.visible ? 'animate-enter' : 'animate-leave'
      } max-w-md w-full ${style.bg} ${style.border} border shadow-lg rounded-lg pointer-events-auto flex ring-1 ring-black ring-opacity-5`}
    >
      <div className="flex-1 w-0 p-4">
        <div className="flex items-start">
          <div className={`flex-shrink-0 pt-0.5 ${style.color}`}>
            <Icon className="h-6 w-6" />
          </div>
          <div className="ml-3 flex-1">
            <p className="text-sm font-medium text-white">
              {notification.title}
            </p>
            <p className="mt-1 text-sm text-gray-400">
              {notification.message}
            </p>
          </div>
        </div>
      </div>
      <div className="flex border-l border-gray-700">
        <button
          onClick={() => toast.dismiss(t.id)}
          className="w-full border border-transparent rounded-none rounded-r-lg p-4 flex items-center justify-center text-sm font-medium text-gray-400 hover:text-white focus:outline-none"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
    </div>
  ), {
    duration: 5000,
    position: 'top-right'
  });
};

// Notification Bell Component (for navbar)
export function NotificationBell({ userId = 'system_user' }) {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const wsRef = useRef(null);
  const dropdownRef = useRef(null);

  // Fetch notifications
  const fetchNotifications = useCallback(async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/notifications/`);
      if (response.ok) {
        const data = await response.json();
        setNotifications(data.notifications || []);
        setUnreadCount(data.unread_count || 0);
      }
    } catch (error) {
      console.error('Fetch notifications error:', error);
    }
  }, []);

  // WebSocket connection for real-time notifications
  useEffect(() => {
    const wsUrl = BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://');
    
    const connectWs = () => {
      const ws = new WebSocket(`${wsUrl}/api/notifications/ws/${userId}`);
      
      ws.onopen = () => {
        console.log('[Notifications WS] Connected');
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'notification') {
            // Add new notification
            setNotifications(prev => [data.data, ...prev]);
            setUnreadCount(prev => prev + 1);
            
            // Show toast
            showNotificationToast(data.data);
          } else if (data.type === 'init') {
            setUnreadCount(data.unread_count || 0);
          }
        } catch (e) {
          console.error('[Notifications WS] Parse error:', e);
        }
      };
      
      ws.onclose = () => {
        console.log('[Notifications WS] Disconnected');
        // Reconnect after 5 seconds
        setTimeout(connectWs, 5000);
      };
      
      ws.onerror = (error) => {
        console.error('[Notifications WS] Error:', error);
      };
      
      wsRef.current = ws;
    };
    
    connectWs();
    fetchNotifications();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [userId, fetchNotifications]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Mark notification as read
  const markAsRead = async (notificationId) => {
    try {
      await fetch(`${BACKEND_URL}/api/notifications/mark-read`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notification_id: notificationId })
      });
      
      setNotifications(prev => 
        prev.map(n => 
          n.notification_id === notificationId ? { ...n, read: true } : n
        )
      );
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch (error) {
      console.error('Mark read error:', error);
    }
  };

  // Mark all as read
  const markAllAsRead = async () => {
    try {
      await fetch(`${BACKEND_URL}/api/notifications/mark-all-read`, {
        method: 'POST'
      });
      
      setNotifications(prev => prev.map(n => ({ ...n, read: true })));
      setUnreadCount(0);
    } catch (error) {
      console.error('Mark all read error:', error);
    }
  };

  // Format timestamp
  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) return 'Adesso';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m fa`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h fa`;
    return date.toLocaleDateString('it-IT');
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Bell button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
        data-testid="notification-bell"
      >
        {unreadCount > 0 ? (
          <BellRing className="w-5 h-5 animate-pulse" />
        ) : (
          <Bell className="w-5 h-5" />
        )}
        
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full text-xs text-white flex items-center justify-center font-medium">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-gray-900 border border-gray-800 rounded-xl shadow-xl z-50 overflow-hidden">
          {/* Header */}
          <div className="p-3 border-b border-gray-800 flex items-center justify-between">
            <h3 className="text-white font-semibold">Notifiche</h3>
            {unreadCount > 0 && (
              <button
                onClick={markAllAsRead}
                className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1"
              >
                <CheckCheck className="w-3 h-3" />
                Segna tutte lette
              </button>
            )}
          </div>

          {/* Notifications list */}
          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                <Bell className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>Nessuna notifica</p>
              </div>
            ) : (
              notifications.slice(0, 10).map((notification) => {
                const style = NOTIFICATION_STYLES[notification.type] || NOTIFICATION_STYLES.info;
                const Icon = style.icon;
                
                return (
                  <div
                    key={notification.notification_id}
                    onClick={() => !notification.read && markAsRead(notification.notification_id)}
                    className={`p-3 border-b border-gray-800 cursor-pointer hover:bg-gray-800/50 transition-colors ${
                      !notification.read ? 'bg-gray-800/30' : ''
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`p-2 rounded-lg ${style.bg}`}>
                        <Icon className={`w-4 h-4 ${style.color}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <p className={`text-sm font-medium ${notification.read ? 'text-gray-400' : 'text-white'}`}>
                            {notification.title}
                          </p>
                          {!notification.read && (
                            <span className="w-2 h-2 bg-purple-500 rounded-full flex-shrink-0" />
                          )}
                        </div>
                        <p className="text-xs text-gray-500 mt-1 truncate">
                          {notification.message}
                        </p>
                        <p className="text-xs text-gray-600 mt-1">
                          {formatTime(notification.created_at)}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && (
            <div className="p-2 border-t border-gray-800">
              <button
                onClick={() => {/* Navigate to full notifications page */}}
                className="w-full py-2 text-center text-sm text-purple-400 hover:text-purple-300 transition-colors"
              >
                Vedi tutte le notifiche
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Price Alert Creator Component
export function PriceAlertCreator({ symbol = 'NENO-EUR', currentPrice = 10000 }) {
  const [isOpen, setIsOpen] = useState(false);
  const [condition, setCondition] = useState('above');
  const [targetPrice, setTargetPrice] = useState('');
  const [loading, setLoading] = useState(false);
  const [alerts, setAlerts] = useState([]);

  // Fetch existing alerts
  const fetchAlerts = useCallback(async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/notifications/alerts`);
      if (response.ok) {
        const data = await response.json();
        setAlerts(data.alerts || []);
      }
    } catch (error) {
      console.error('Fetch alerts error:', error);
    }
  }, []);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // Create alert
  const createAlert = async () => {
    if (!targetPrice) return;
    
    setLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/notifications/alerts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          condition,
          target_value: parseFloat(targetPrice)
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        setTargetPrice('');
        setIsOpen(false);
        fetchAlerts();
      }
    } catch (error) {
      toast.error('Errore nella creazione dell\'alert');
    } finally {
      setLoading(false);
    }
  };

  // Delete alert
  const deleteAlert = async (alertId) => {
    try {
      await fetch(`${BACKEND_URL}/api/notifications/alerts/${alertId}`, {
        method: 'DELETE'
      });
      setAlerts(prev => prev.filter(a => a.alert_id !== alertId));
      toast.success('Alert eliminato');
    } catch (error) {
      toast.error('Errore nell\'eliminazione');
    }
  };

  return (
    <div className="bg-gray-800/50 rounded-xl p-4" data-testid="price-alert-creator">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-white font-medium flex items-center gap-2">
          <Bell className="w-4 h-4 text-purple-400" />
          Alert Prezzo
        </h3>
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="p-1 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Create alert form */}
      {isOpen && (
        <div className="mb-4 p-3 bg-gray-900/50 rounded-lg space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => setCondition('above')}
              className={`py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-1 ${
                condition === 'above'
                  ? 'bg-green-500/20 text-green-400 border border-green-500/50'
                  : 'bg-gray-800 text-gray-400'
              }`}
            >
              <TrendingUp className="w-4 h-4" />
              Sopra
            </button>
            <button
              onClick={() => setCondition('below')}
              className={`py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-1 ${
                condition === 'below'
                  ? 'bg-red-500/20 text-red-400 border border-red-500/50'
                  : 'bg-gray-800 text-gray-400'
              }`}
            >
              <TrendingDown className="w-4 h-4" />
              Sotto
            </button>
          </div>

          <input
            type="number"
            value={targetPrice}
            onChange={(e) => setTargetPrice(e.target.value)}
            placeholder={`Prezzo target (attuale: €${currentPrice.toLocaleString()})`}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:border-purple-500 focus:outline-none"
          />

          <button
            onClick={createAlert}
            disabled={loading || !targetPrice}
            className="w-full py-2 bg-purple-500 hover:bg-purple-600 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            {loading ? 'Creazione...' : 'Crea Alert'}
          </button>
        </div>
      )}

      {/* Active alerts */}
      <div className="space-y-2">
        {alerts.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-2">
            Nessun alert attivo
          </p>
        ) : (
          alerts.map(alert => (
            <div
              key={alert.alert_id}
              className="flex items-center justify-between p-2 bg-gray-900/50 rounded-lg"
            >
              <div className="flex items-center gap-2">
                {alert.condition === 'above' ? (
                  <TrendingUp className="w-4 h-4 text-green-400" />
                ) : (
                  <TrendingDown className="w-4 h-4 text-red-400" />
                )}
                <span className="text-sm text-gray-300">
                  {alert.condition === 'above' ? 'Sopra' : 'Sotto'} €{alert.target_value.toLocaleString()}
                </span>
              </div>
              <button
                onClick={() => deleteAlert(alert.alert_id)}
                className="p-1 text-gray-500 hover:text-red-400 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// Main Toaster component to add to App.js
export function NotificationToaster() {
  return (
    <Toaster
      position="top-right"
      toastOptions={{
        duration: 5000,
        style: {
          background: 'transparent',
          boxShadow: 'none',
          padding: 0
        }
      }}
    />
  );
}

export default NotificationBell;
