import React, { useState, useEffect } from 'react';
import {
  Clock,
  CheckCircle,
  AlertCircle,
  Loader2,
  CreditCard,
  User,
  Wallet,
  ArrowRight,
  FileText,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Download
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

// Phase configurations
const PHASE_CONFIG = {
  setup: {
    label: 'Configurazione',
    icon: CreditCard,
    color: 'blue',
    bgColor: 'bg-blue-500/20',
    borderColor: 'border-blue-500/30',
    textColor: 'text-blue-400'
  },
  kyc: {
    label: 'Verifica Identità',
    icon: User,
    color: 'purple',
    bgColor: 'bg-purple-500/20',
    borderColor: 'border-purple-500/30',
    textColor: 'text-purple-400'
  },
  payment: {
    label: 'Pagamento',
    icon: CreditCard,
    color: 'yellow',
    bgColor: 'bg-yellow-500/20',
    borderColor: 'border-yellow-500/30',
    textColor: 'text-yellow-400'
  },
  transfer: {
    label: 'Trasferimento',
    icon: ArrowRight,
    color: 'green',
    bgColor: 'bg-green-500/20',
    borderColor: 'border-green-500/30',
    textColor: 'text-green-400'
  },
  completion: {
    label: 'Completamento',
    icon: CheckCircle,
    color: 'emerald',
    bgColor: 'bg-emerald-500/20',
    borderColor: 'border-emerald-500/30',
    textColor: 'text-emerald-400'
  }
};

// Event type labels
const EVENT_LABELS = {
  widget_opened: 'Widget aperto',
  widget_closed: 'Widget chiuso',
  mode_selected: 'Modalità selezionata',
  amount_entered: 'Importo inserito',
  currency_selected: 'Valuta selezionata',
  wallet_entered: 'Wallet inserito',
  order_created: 'Ordine creato',
  order_linked: 'Ordine collegato',
  kyc_started: 'KYC iniziato',
  kyc_completed: 'KYC completato',
  kyc_failed: 'KYC fallito',
  payment_initiated: 'Pagamento iniziato',
  payment_received: 'Pagamento ricevuto',
  payment_failed: 'Pagamento fallito',
  crypto_transfer_initiated: 'Trasferimento crypto iniziato',
  crypto_transfer_completed: 'Trasferimento crypto completato',
  fiat_transfer_initiated: 'Trasferimento fiat iniziato',
  fiat_transfer_completed: 'Trasferimento fiat completato',
  order_completed: 'Ordine completato',
  order_cancelled: 'Ordine annullato',
  order_failed: 'Ordine fallito',
  order_refunded: 'Ordine rimborsato',
  webhook_received: 'Webhook ricevuto',
  status_update: 'Stato aggiornato',
  error_occurred: 'Errore verificato'
};

function formatTimestamp(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleString('it-IT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
}

function formatDuration(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

// Timeline Event Component
function TimelineEvent({ event, isLast }) {
  const isError = event.type.includes('failed') || event.type.includes('error');
  const isSuccess = event.type.includes('completed');
  
  return (
    <div className="flex gap-3 pb-4">
      {/* Timeline line */}
      <div className="flex flex-col items-center">
        <div className={`w-3 h-3 rounded-full ${
          isError ? 'bg-red-500' : isSuccess ? 'bg-green-500' : 'bg-gray-500'
        }`} />
        {!isLast && <div className="w-0.5 flex-1 bg-gray-700 mt-1" />}
      </div>
      
      {/* Event content */}
      <div className="flex-1 pb-2">
        <div className="flex items-center justify-between">
          <span className={`text-sm font-medium ${
            isError ? 'text-red-400' : isSuccess ? 'text-green-400' : 'text-white'
          }`}>
            {EVENT_LABELS[event.type] || event.type}
          </span>
          <span className="text-xs text-gray-500">
            {formatTimestamp(event.timestamp)}
          </span>
        </div>
        {event.description && (
          <p className="text-xs text-gray-400 mt-1">{event.description}</p>
        )}
        {event.metadata && Object.keys(event.metadata).length > 0 && (
          <div className="mt-2 p-2 bg-white/5 rounded text-xs text-gray-400">
            {Object.entries(event.metadata).map(([key, value]) => (
              <div key={key}>
                <span className="text-gray-500">{key}:</span> {JSON.stringify(value)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Phase Card Component
function PhaseCard({ phase, events, config }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = config.icon;
  
  if (events.length === 0) return null;
  
  return (
    <div className={`rounded-xl border ${config.borderColor} ${config.bgColor} overflow-hidden`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 flex items-center justify-between hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-lg ${config.bgColor} flex items-center justify-center`}>
            <Icon className={`w-5 h-5 ${config.textColor}`} />
          </div>
          <div className="text-left">
            <h3 className="text-white font-medium">{config.label}</h3>
            <p className="text-xs text-gray-400">{events.length} eventi</p>
          </div>
        </div>
        {expanded ? (
          <ChevronUp className="w-5 h-5 text-gray-400" />
        ) : (
          <ChevronDown className="w-5 h-5 text-gray-400" />
        )}
      </button>
      
      {expanded && (
        <div className="px-4 pb-4 border-t border-white/10">
          <div className="pt-4">
            {events.map((event, index) => (
              <TimelineEvent
                key={event.event_id}
                event={event}
                isLast={index === events.length - 1}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Main Timeline Component
export default function TransactionTimeline({ sessionId, orderId, onClose }) {
  const [timeline, setTimeline] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    fetchTimeline();
  }, [sessionId, orderId]);

  const fetchTimeline = async () => {
    setLoading(true);
    setError(null);
    
    try {
      let url;
      if (sessionId) {
        url = `${BACKEND_URL}/api/audit/timeline/${sessionId}`;
      } else if (orderId) {
        // First get session by order
        const sessionRes = await fetch(`${BACKEND_URL}/api/audit/sessions/by-order/${orderId}`);
        if (!sessionRes.ok) throw new Error('Session not found');
        const session = await sessionRes.json();
        url = `${BACKEND_URL}/api/audit/timeline/${session.session_id}`;
      } else {
        throw new Error('No session or order ID provided');
      }
      
      const response = await fetch(url);
      if (!response.ok) throw new Error('Failed to load timeline');
      
      const data = await response.json();
      setTimeline(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const exportReport = async () => {
    if (!timeline) return;
    
    setExporting(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/audit/export/${timeline.session_id}`);
      if (!response.ok) throw new Error('Export failed');
      
      const report = await response.json();
      
      // Download as JSON
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `transaction_report_${timeline.session_id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export error:', err);
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-center">
        <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
        <p className="text-red-400">{error}</p>
        <button
          onClick={fetchTimeline}
          className="mt-4 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm"
        >
          Riprova
        </button>
      </div>
    );
  }

  if (!timeline) return null;

  const statusColors = {
    active: 'text-blue-400 bg-blue-500/20',
    completed: 'text-green-400 bg-green-500/20',
    failed: 'text-red-400 bg-red-500/20',
    cancelled: 'text-yellow-400 bg-yellow-500/20'
  };

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-gray-800">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-purple-500/20 rounded-xl flex items-center justify-center">
              <FileText className="w-6 h-6 text-purple-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">Timeline Transazione</h2>
              <p className="text-sm text-gray-400">
                {timeline.product_type === 'BUY' ? 'Acquisto Crypto' : 'Vendita Crypto'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchTimeline}
              className="p-2 hover:bg-white/10 rounded-lg transition-colors"
              title="Aggiorna"
            >
              <RefreshCw className="w-5 h-5 text-gray-400" />
            </button>
            <button
              onClick={exportReport}
              disabled={exporting}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm disabled:opacity-50"
            >
              {exporting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              Esporta
            </button>
          </div>
        </div>
        
        {/* Summary */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-3 bg-white/5 rounded-lg">
            <p className="text-xs text-gray-500">Stato</p>
            <span className={`inline-block px-2 py-1 rounded text-xs font-medium mt-1 ${
              statusColors[timeline.status] || statusColors.active
            }`}>
              {timeline.status}
            </span>
          </div>
          <div className="p-3 bg-white/5 rounded-lg">
            <p className="text-xs text-gray-500">Durata</p>
            <p className="text-white font-medium">{timeline.duration_formatted}</p>
          </div>
          <div className="p-3 bg-white/5 rounded-lg">
            <p className="text-xs text-gray-500">Eventi</p>
            <p className="text-white font-medium">{timeline.total_events}</p>
          </div>
          <div className="p-3 bg-white/5 rounded-lg">
            <p className="text-xs text-gray-500">Inizio</p>
            <p className="text-white font-medium text-sm">
              {formatTimestamp(timeline.started_at)}
            </p>
          </div>
        </div>
      </div>
      
      {/* Phases */}
      <div className="p-6 space-y-4">
        {Object.entries(PHASE_CONFIG).map(([phase, config]) => (
          <PhaseCard
            key={phase}
            phase={phase}
            events={timeline.phases[phase] || []}
            config={config}
          />
        ))}
      </div>
      
      {/* Order Info */}
      {timeline.order_id && (
        <div className="px-6 pb-6">
          <div className="p-4 bg-white/5 rounded-lg">
            <p className="text-xs text-gray-500 mb-1">Order ID</p>
            <p className="text-white font-mono text-sm">{timeline.order_id}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// Sessions List Component
export function TransactionSessionsList({ userId }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSession, setSelectedSession] = useState(null);

  useEffect(() => {
    if (userId) {
      fetchSessions();
    }
  }, [userId]);

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/audit/users/${userId}/sessions`);
      if (response.ok) {
        const data = await response.json();
        setSessions(data.sessions || []);
      }
    } catch (err) {
      console.error('Error fetching sessions:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="w-6 h-6 text-purple-400 animate-spin" />
      </div>
    );
  }

  if (selectedSession) {
    return (
      <div>
        <button
          onClick={() => setSelectedSession(null)}
          className="mb-4 text-purple-400 hover:text-purple-300 text-sm"
        >
          ← Torna alla lista
        </button>
        <TransactionTimeline sessionId={selectedSession} />
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="text-center p-8 text-gray-400">
        <Clock className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>Nessuna transazione registrata</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {sessions.map((session) => (
        <button
          key={session.session_id}
          onClick={() => setSelectedSession(session.session_id)}
          className="w-full p-4 bg-white/5 hover:bg-white/10 rounded-xl border border-white/10 text-left transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                session.product_type === 'BUY' ? 'bg-green-500/20' : 'bg-orange-500/20'
              }`}>
                <Wallet className={`w-5 h-5 ${
                  session.product_type === 'BUY' ? 'text-green-400' : 'text-orange-400'
                }`} />
              </div>
              <div>
                <p className="text-white font-medium">
                  {session.product_type === 'BUY' ? 'Acquisto' : 'Vendita'} Crypto
                </p>
                <p className="text-xs text-gray-400">
                  {formatTimestamp(session.started_at)}
                </p>
              </div>
            </div>
            <div className={`px-2 py-1 rounded text-xs font-medium ${
              session.status === 'completed' ? 'bg-green-500/20 text-green-400' :
              session.status === 'failed' ? 'bg-red-500/20 text-red-400' :
              'bg-blue-500/20 text-blue-400'
            }`}>
              {session.status}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}
