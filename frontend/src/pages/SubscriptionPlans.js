import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Check, Crown, Zap, Code, Building, Loader2,
  ArrowRight, Star, Shield, AlertCircle, ArrowLeft
} from 'lucide-react';
import { xhrGet, xhrPost, BACKEND_URL } from '../utils/safeFetch';

const PLAN_ICONS = {
  free: Zap, pro_trader: Crown, premium: Star,
  developer_basic: Code, developer_pro: Code, enterprise: Building,
};
const PLAN_GRADIENTS = {
  free: 'from-gray-600 to-gray-700', pro_trader: 'from-blue-500 to-cyan-500',
  premium: 'from-purple-500 to-pink-500', developer_basic: 'from-green-500 to-emerald-500',
  developer_pro: 'from-orange-500 to-amber-500', enterprise: 'from-red-500 to-rose-500',
};

export default function SubscriptionPlans() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [subscribing, setSubscribing] = useState(null);
  const [plans, setPlans] = useState([]);
  const [currentSub, setCurrentSub] = useState(null);
  const [billingCycle, setBillingCycle] = useState('monthly');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => { fetchData(); }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [plansData, subData] = await Promise.all([
        xhrGet(`${BACKEND_URL}/api/subscriptions/plans/list`),
        xhrGet(`${BACKEND_URL}/api/subscriptions/my-subscription`),
      ]);
      setPlans(plansData.plans || []);
      if (subData && !subData.detail) setCurrentSub(subData);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const handleSubscribe = async (planId) => {
    setSubscribing(planId); setError(''); setSuccess('');
    try {
      const { ok, data } = await xhrPost(`${BACKEND_URL}/api/subscriptions/subscribe`, { plan_id: planId, billing_cycle: billingCycle });
      if (!ok) throw new Error(data.detail || 'Errore nella sottoscrizione');
      setSuccess(`Sottoscrizione a ${data.plan_name} attivata con successo!`);
      await fetchData();
    } catch (e) { setError(e.message); }
    finally { setSubscribing(null); }
  };

  const handleCancel = async () => {
    if (!window.confirm('Sei sicuro di voler cancellare il tuo abbonamento?')) return;
    try {
      const { ok } = await xhrPost(`${BACKEND_URL}/api/subscriptions/cancel`, {});
      if (ok) {
        setSuccess('Abbonamento cancellato. Manterrai l\'accesso fino alla fine del periodo.');
        await fetchData();
      }
    } catch (e) { console.error(e); }
  };

  const userPlans = plans.filter(p => p.plan_type === 'user');
  const devPlans = plans.filter(p => p.plan_type === 'developer');
  const entPlans = plans.filter(p => p.plan_type === 'enterprise');

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950" data-testid="subscription-plans-page">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur-lg">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/dashboard')} className="p-2 hover:bg-gray-800 rounded-lg transition-colors">
              <ArrowLeft className="w-5 h-5 text-gray-400" />
            </button>
            <div>
              <h1 className="text-lg font-bold text-white">Piani di Abbonamento</h1>
              <p className="text-gray-400 text-sm">Sblocca funzionalita' premium su NeoNoble Ramp</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Messages */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}
        {success && (
          <div className="mb-6 p-4 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center gap-2">
            <Check className="w-4 h-4 text-green-400 flex-shrink-0" />
            <p className="text-green-400 text-sm">{success}</p>
          </div>
        )}

        {/* Current Subscription */}
        {currentSub && (
          <div className="mb-8 bg-purple-500/10 border border-purple-500/30 rounded-xl p-5" data-testid="current-subscription">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-gray-400 text-xs mb-1">Il tuo piano attuale</p>
                <h3 className="text-lg font-bold text-white">{currentSub.plan_name}</h3>
                <p className="text-gray-400 text-sm mt-1">
                  {currentSub.billing_cycle === 'monthly' ? 'Mensile' : 'Annuale'} - €{currentSub.amount_paid}/
                  {currentSub.billing_cycle === 'monthly' ? 'mese' : 'anno'}
                </p>
                {currentSub.current_period_end && (
                  <p className="text-gray-500 text-xs mt-1">
                    Scade il {new Date(currentSub.current_period_end).toLocaleDateString('it-IT')}
                  </p>
                )}
              </div>
              <button onClick={handleCancel} data-testid="cancel-subscription-btn"
                className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-sm transition-colors">
                Cancella
              </button>
            </div>
          </div>
        )}

        {/* Billing Toggle */}
        <div className="flex items-center justify-center gap-4 mb-8">
          <span className={`text-sm ${billingCycle === 'monthly' ? 'text-white font-medium' : 'text-gray-400'}`}>Mensile</span>
          <button onClick={() => setBillingCycle(billingCycle === 'monthly' ? 'yearly' : 'monthly')}
            data-testid="billing-toggle"
            className={`relative w-12 h-6 rounded-full transition-colors ${billingCycle === 'yearly' ? 'bg-purple-500' : 'bg-gray-700'}`}>
            <div className={`absolute top-0.5 w-5 h-5 bg-white rounded-full transition-transform ${billingCycle === 'yearly' ? 'translate-x-6' : 'translate-x-0.5'}`} />
          </button>
          <span className={`text-sm ${billingCycle === 'yearly' ? 'text-white font-medium' : 'text-gray-400'}`}>
            Annuale <span className="text-green-400 text-xs ml-1">Risparmia -17%</span>
          </span>
        </div>

        {/* User Plans */}
        {userPlans.length > 0 && (
          <section className="mb-10">
            <h2 className="text-lg font-semibold text-white mb-5 flex items-center gap-2">
              <Crown className="w-5 h-5 text-purple-400" /> Piani Trading
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              {userPlans.map(plan => (
                <PlanCard key={plan.id} plan={plan} billingCycle={billingCycle}
                  isCurrentPlan={currentSub?.plan_id === plan.id}
                  onSubscribe={() => handleSubscribe(plan.id)}
                  subscribing={subscribing === plan.id} />
              ))}
            </div>
          </section>
        )}

        {/* Developer Plans */}
        {devPlans.length > 0 && (
          <section className="mb-10">
            <h2 className="text-lg font-semibold text-white mb-5 flex items-center gap-2">
              <Code className="w-5 h-5 text-green-400" /> Piani Developer
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {devPlans.map(plan => (
                <PlanCard key={plan.id} plan={plan} billingCycle={billingCycle}
                  isCurrentPlan={currentSub?.plan_id === plan.id}
                  onSubscribe={() => handleSubscribe(plan.id)}
                  subscribing={subscribing === plan.id} />
              ))}
            </div>
          </section>
        )}

        {/* Enterprise Plans */}
        {entPlans.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold text-white mb-5 flex items-center gap-2">
              <Building className="w-5 h-5 text-red-400" /> Enterprise
            </h2>
            <div className="grid grid-cols-1 gap-5">
              {entPlans.map(plan => (
                <PlanCard key={plan.id} plan={plan} billingCycle={billingCycle}
                  isCurrentPlan={currentSub?.plan_id === plan.id}
                  onSubscribe={() => handleSubscribe(plan.id)}
                  subscribing={subscribing === plan.id} featured />
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

function PlanCard({ plan, billingCycle, isCurrentPlan, onSubscribe, subscribing, featured }) {
  const Icon = PLAN_ICONS[plan.code] || Shield;
  const gradient = PLAN_GRADIENTS[plan.code] || 'from-purple-500 to-pink-500';
  const price = billingCycle === 'monthly' ? plan.price_monthly : plan.price_yearly;
  const period = billingCycle === 'monthly' ? '/mese' : '/anno';

  const features = [];
  if (plan.trading_fee_discount > 0)
    features.push(`${(plan.trading_fee_discount * 100).toFixed(0)}% sconto commissioni`);
  if (plan.max_api_keys > 0)
    features.push(plan.max_api_keys === -1 ? 'API Keys illimitate' : `${plan.max_api_keys} API Keys`);
  if (plan.max_tokens_created > 0)
    features.push(plan.max_tokens_created === -1 ? 'Token illimitati' : `${plan.max_tokens_created} Token`);
  if (plan.max_listings > 0)
    features.push(plan.max_listings === -1 ? 'Listing illimitati' : `${plan.max_listings} Listing`);

  Object.entries(plan.features || {}).forEach(([key, val]) => {
    if (typeof val === 'boolean' && val) {
      features.push(key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()));
    } else if (typeof val === 'number' && val !== 0) {
      const label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      features.push(val === -1 ? `${label}: Illimitato` : `${label}: ${val.toLocaleString()}`);
    }
  });

  return (
    <div className={`relative bg-gray-900 border rounded-xl overflow-hidden ${
      isCurrentPlan ? 'border-purple-500 ring-2 ring-purple-500/20' :
      featured ? 'border-gray-600' : 'border-gray-800 hover:border-gray-700'
    }`} data-testid={`plan-card-${plan.code}`}>
      {isCurrentPlan && (
        <div className="absolute top-0 right-0 bg-purple-500 text-white text-xs font-bold px-3 py-1 rounded-bl-lg">ATTIVO</div>
      )}
      <div className="p-5">
        <div className="flex items-center gap-2 mb-2">
          <div className={`p-1.5 rounded-lg bg-gradient-to-r ${gradient}`}>
            <Icon className="w-4 h-4 text-white" />
          </div>
          <h3 className="text-lg font-bold text-white">{plan.name}</h3>
        </div>
        {plan.description && <p className="text-gray-400 text-sm mb-4">{plan.description}</p>}

        <div className="mb-5">
          <span className="text-3xl font-bold text-white">€{price.toLocaleString()}</span>
          <span className="text-gray-400 text-sm">{period}</span>
        </div>

        <ul className="space-y-2 mb-5">
          {features.slice(0, 6).map((f, i) => (
            <li key={i} className="flex items-center gap-2 text-sm">
              <Check className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />
              <span className="text-gray-300">{f}</span>
            </li>
          ))}
        </ul>

        <button onClick={onSubscribe}
          disabled={subscribing || isCurrentPlan || price === 0}
          data-testid={`subscribe-${plan.code}`}
          className={`w-full py-2.5 rounded-lg font-semibold text-sm transition-all flex items-center justify-center gap-2 ${
            isCurrentPlan ? 'bg-gray-800 text-gray-500 cursor-default' :
            price === 0 ? 'bg-gray-800 text-gray-500' :
            `bg-gradient-to-r ${gradient} text-white hover:opacity-90`
          }`}>
          {subscribing ? <Loader2 className="w-4 h-4 animate-spin" /> :
           isCurrentPlan ? 'Piano Attivo' :
           price === 0 ? 'Piano Attuale' :
           <><span>Sottoscrivi</span><ArrowRight className="w-4 h-4" /></>}
        </button>
      </div>
    </div>
  );
}
