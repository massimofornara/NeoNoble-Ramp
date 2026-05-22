import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Web3Provider } from "./context/Web3Context";
import { I18nProvider } from "./i18n/I18nContext";
import { Toaster } from "@/components/ui/sonner";
import { NotificationToaster } from "./components/NotificationSystem";
import { WalletModal } from "./components/WalletConnect";

// Pages
import Home from "./pages/Home";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Dashboard from "./pages/Dashboard";
import DevPortal from "./pages/DevPortal";
import DevLogin from "./pages/DevLogin";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import AdminDashboard from "./pages/AdminDashboard";
import TokenCreation from "./pages/TokenCreation";
import TokenList from "./pages/TokenList";
import SubscriptionPlans from "./pages/SubscriptionPlans";
import MarketData from "./pages/MarketData";
import CardManagement from "./pages/CardManagement";
import TradingPage from "./pages/TradingPage";
import WalletPage from "./pages/WalletPage";
import NenoExchange from "./pages/NenoExchange";
import MarginTrading from "./pages/MarginTrading";
import KYCPage from "./pages/KYCPage";
import PortfolioAnalytics from "./pages/PortfolioAnalytics";
import SettingsPage from "./pages/SettingsPage";
import ApiDocs from "./pages/ApiDocs";
import AuditLog from "./pages/AuditLog";
import PortfolioTracker from "./pages/PortfolioTracker";
import DCABot from "./pages/DCABot";
import ReferralPage from "./pages/ReferralPage";
import CustomTokenTrade from "./pages/CustomTokenTrade";
import { usePageTracking } from "./hooks/usePageTracking";

// Protected Route Component
function ProtectedRoute({ children, requireDeveloper = false }) {
  const { isAuthenticated, isDeveloper, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requireDeveloper && !isDeveloper) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}

// Public Route (redirect if logged in)
function PublicRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}

function AppRoutes() {
  usePageTracking();
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/" element={<Home />} />
      
      <Route
        path="/login"
        element={
          <PublicRoute>
            <Login />
          </PublicRoute>
        }
      />
      
      <Route
        path="/signup"
        element={
          <PublicRoute>
            <Signup />
          </PublicRoute>
        }
      />
      
      <Route
        path="/forgot-password"
        element={
          <PublicRoute>
            <ForgotPassword />
          </PublicRoute>
        }
      />
      
      <Route
        path="/reset-password"
        element={<ResetPassword />}
      />
      
      <Route
        path="/dev/login"
        element={
          <PublicRoute>
            <DevLogin />
          </PublicRoute>
        }
      />

      {/* Protected Routes */}
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />

      {/* Developer Portal (requires developer role) */}
      <Route
        path="/dev"
        element={
          <ProtectedRoute requireDeveloper>
            <DevPortal />
          </ProtectedRoute>
        }
      />

      {/* Admin Dashboard */}
      <Route
        path="/admin"
        element={
          <ProtectedRoute>
            <AdminDashboard />
          </ProtectedRoute>
        }
      />

      {/* Token Routes */}
      <Route
        path="/tokens/create"
        element={
          <ProtectedRoute>
            <TokenCreation />
          </ProtectedRoute>
        }
      />
      <Route
        path="/tokens/list"
        element={
          <ProtectedRoute>
            <TokenList />
          </ProtectedRoute>
        }
      />
      <Route
        path="/tokens"
        element={<Navigate to="/tokens/list" replace />}
      />

      {/* Subscription Routes */}
      <Route
        path="/subscriptions"
        element={
          <ProtectedRoute>
            <SubscriptionPlans />
          </ProtectedRoute>
        }
      />

      {/* Market Data */}
      <Route
        path="/market"
        element={
          <ProtectedRoute>
            <MarketData />
          </ProtectedRoute>
        }
      />

      {/* Card Management */}
      <Route
        path="/cards"
        element={
          <ProtectedRoute>
            <CardManagement />
          </ProtectedRoute>
        }
      />

      {/* Trading */}
      <Route
        path="/trade"
        element={
          <ProtectedRoute>
            <TradingPage />
          </ProtectedRoute>
        }
      />

      {/* Wallet & Banking */}
      <Route
        path="/wallet"
        element={
          <ProtectedRoute>
            <WalletPage />
          </ProtectedRoute>
        }
      />

      {/* NENO Exchange */}
      <Route
        path="/neno-exchange"
        element={
          <ProtectedRoute>
            <NenoExchange />
          </ProtectedRoute>
        }
      />

      {/* Margin Trading */}
      <Route
        path="/margin"
        element={
          <ProtectedRoute>
            <MarginTrading />
          </ProtectedRoute>
        }
      />

      {/* KYC / AML */}
      <Route
        path="/kyc"
        element={
          <ProtectedRoute>
            <KYCPage />
          </ProtectedRoute>
        }
      />

      {/* Portfolio Analytics */}
      <Route
        path="/portfolio"
        element={
          <ProtectedRoute>
            <PortfolioAnalytics />
          </ProtectedRoute>
        }
      />

      {/* Settings */}
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <SettingsPage />
          </ProtectedRoute>
        }
      />

      {/* API Documentation */}
      <Route
        path="/developer/docs"
        element={<ApiDocs />}
      />

      {/* Audit Log (Admin) */}
      <Route
        path="/audit"
        element={
          <ProtectedRoute>
            <AuditLog />
          </ProtectedRoute>
        }
      />

      {/* Real-time Portfolio Tracker */}
      <Route
        path="/portfolio-tracker"
        element={
          <ProtectedRoute>
            <PortfolioTracker />
          </ProtectedRoute>
        }
      />

      {/* DCA Bot */}
      <Route
        path="/dca"
        element={
          <ProtectedRoute>
            <DCABot />
          </ProtectedRoute>
        }
      />

      {/* Referral */}
      <Route
        path="/referral"
        element={
          <ProtectedRoute>
            <ReferralPage />
          </ProtectedRoute>
        }
      />

      {/* Custom Token Trade (Buy/Sell/Swap) */}
      <Route
        path="/custom-tokens"
        element={
          <ProtectedRoute>
            <CustomTokenTrade />
          </ProtectedRoute>
        }
      />

      {/* Catch all - redirect to home */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Web3Provider>
          <AuthProvider>
            <I18nProvider>
              <AppRoutes />
              <Toaster />
              <NotificationToaster />
              <WalletModal />
            </I18nProvider>
          </AuthProvider>
        </Web3Provider>
      </BrowserRouter>
    </div>
  );
}

export default App;
