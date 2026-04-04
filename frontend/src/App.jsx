import React, { useState, useCallback } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import '@/App.css';
import Navbar from '@/components/Navbar';
import OrderScreen from '@/components/OrderScreen';
import PaymentScreen from '@/components/PaymentScreen';
import DeliveryScreen from '@/components/DeliveryScreen';
import PostDeliveryScreen from '@/components/PostDeliveryScreen';
import FinalDecisionScreen from '@/components/FinalDecisionScreen';
import LogsPanel from '@/components/LogsPanel';
import AdminDashboard from '@/components/AdminDashboard';
import { verifyDelivery, settlePayment } from '@/services/api';

function TrustOSApp() {
  const [step, setStep] = useState('order');
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [riskData, setRiskData] = useState(null);
  const [deliveryStage, setDeliveryStage] = useState('placed');
  const [verificationResult, setVerificationResult] = useState(null);
  const [finalOutcome, setFinalOutcome] = useState(null);
  const [deliveryTimestamps, setDeliveryTimestamps] = useState({});
  const [transactions, setTransactions] = useState([]);
  const [contractVerifyResult, setContractVerifyResult] = useState(null);
  const [contractSettleResult, setContractSettleResult] = useState(null);
  const [showAdmin, setShowAdmin] = useState(false);
  const [logs, setLogs] = useState([
    { message: 'TrustOS Engine v2.4.1 initialized.', type: 'system', ts: Date.now() },
    { message: 'Settlement protocol active. Awaiting transaction...', type: 'info', ts: Date.now() + 50 },
  ]);

  const addLog = useCallback((message, type = 'info') => {
    setLogs(prev => [...prev, { message, type, ts: Date.now() }]);
  }, []);

  const handleOrderPlaced = (product, risk) => {
    setSelectedProduct(product);
    setRiskData(risk);
    const ts = new Date().toLocaleTimeString();
    setDeliveryTimestamps({ placed: ts });
    addLog(`--- New Transaction Started ---`, 'system');
    addLog(`Product: ${product.name} @ ${product.priceLabel}`, 'info');
    addLog(`Evaluating buyer trust... BT = ${risk.bt.toFixed(1)}`, 'info');
    addLog(`Evaluating seller trust... ST = ${risk.st.toFixed(1)}`, 'info');
    addLog(`Value risk: +${risk.valueRisk} | Interaction: +${risk.interactionRisk} | Context: +${risk.contextRisk}`, 'info');
    addLog(`Risk Score: ${risk.score.toFixed(1)} → ${risk.level.toUpperCase()} RISK`, risk.level);
    const statusMap = { low: 'Captured', medium: 'Authorized', high: 'Held' };
    addLog(`Payment ${statusMap[risk.level]} — settlement deferred to TrustOS`, 'system');
    setStep('payment');
  };

  const handlePaymentContinued = () => {
    addLog('Order confirmed. Awaiting fulfillment...', 'info');
    setDeliveryStage('placed');
    setStep('delivery');
  };

  const handleDeliveryUpdate = (stage) => {
    const ts = new Date().toLocaleTimeString();
    setDeliveryStage(stage);
    setDeliveryTimestamps(prev => ({ ...prev, [stage]: ts }));
    if (stage === 'shipped') addLog('Order dispatched by seller. In transit...', 'info');
    if (stage === 'delivered') addLog('Package delivered to buyer address.', 'info');
  };

  const handleDeliveryComplete = () => {
    addLog('Delivery confirmed. Initiating post-delivery protocol...', 'system');
    if (riskData.level === 'low') {
      addLog('LOW RISK: Silent windows started (≈30 min–1 hr then ≈2–8 hr, demo timers).', 'low');
    } else if (riskData.level === 'medium') {
      addLog('MEDIUM RISK: Awaiting buyer delivery confirmation...', 'medium');
    } else {
      addLog('HIGH RISK: Multi-factor verification required.', 'high');
      addLog('OTP dispatched to buyer registered device (****6789).', 'system');
    }
    setStep('post_delivery');
  };

  const handleVerificationComplete = async (result) => {
    try {
      const verifyRes = await verifyDelivery({ passed: result === 'passed' });
      setContractVerifyResult(verifyRes);
      const settleRes = await settlePayment({
        action: result === 'passed' ? 'capture' : 'release',
      });
      setContractSettleResult(settleRes);
      addLog(`Demo contract: verify → ${verifyRes.result}`, 'info');
      addLog(`Demo contract: settle → ${settleRes.status}`, 'info');
    } catch (e) {
      setContractVerifyResult(null);
      setContractSettleResult(null);
      addLog(`Settlement API error: ${e.message || e}`, 'high');
    }
    setVerificationResult(result);
    const outcome = result === 'passed' ? 'released' : 'refunded';
    setFinalOutcome(outcome);
    if (outcome === 'released') {
      addLog('Verification passed. Release condition met.', 'low');
      addLog(`Payment of ${selectedProduct.priceLabel} released to ${selectedProduct.seller.name}.`, 'system');
    } else {
      addLog('Verification failed or dispute raised.', 'high');
      addLog(`Funds of ${selectedProduct.priceLabel} returned to buyer.`, 'system');
    }
    addLog('--- Transaction Complete ---', 'system');
    // Record to transaction history
    setTransactions(prev => [{
      id: `user-${Date.now()}`,
      productName: selectedProduct.name,
      priceLabel: selectedProduct.priceLabel,
      riskLevel: riskData.level,
      riskScore: riskData.score,
      paymentStatus: { low: 'Captured', medium: 'Authorized', high: 'Held' }[riskData.level],
      outcome,
      buyerName: selectedProduct.buyer.name,
      sellerName: selectedProduct.seller.name,
      timestamp: Date.now(),
    }, ...prev]);
    setStep('final');
  };

  const handleReset = () => {
    setStep('order');
    setSelectedProduct(null);
    setRiskData(null);
    setDeliveryStage('placed');
    setVerificationResult(null);
    setFinalOutcome(null);
    setDeliveryTimestamps({});
    setContractVerifyResult(null);
    setContractSettleResult(null);
    setLogs([
      { message: 'TrustOS Engine v2.4.1 initialized.', type: 'system', ts: Date.now() },
      { message: 'Settlement protocol active. Awaiting transaction...', type: 'info', ts: Date.now() + 50 },
    ]);
  };

  const sharedProps = {
    selectedProduct,
    riskData,
    deliveryStage,
    deliveryTimestamps,
    verificationResult,
    finalOutcome,
    contractVerifyResult,
    contractSettleResult,
    addLog,
  };

  return (
    <div className="trust-app-shell font-sans text-slate-800 antialiased">
      <Navbar
        step={step}
        onReset={handleReset}
        showAdmin={showAdmin}
        onToggleAdmin={() => setShowAdmin(a => !a)}
        txCount={transactions.length}
      />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {showAdmin ? (
          <AdminDashboard userTransactions={transactions} />
        ) : (
          <div className="flex gap-6 items-start">
            <main className="flex-1 min-w-0 animate-fade-in">
              {step === 'order' && <OrderScreen {...sharedProps} onOrderPlaced={handleOrderPlaced} />}
              {step === 'payment' && <PaymentScreen {...sharedProps} onContinue={handlePaymentContinued} />}
              {step === 'delivery' && <DeliveryScreen {...sharedProps} onDeliveryUpdate={handleDeliveryUpdate} onProceed={handleDeliveryComplete} />}
              {step === 'post_delivery' && <PostDeliveryScreen {...sharedProps} onComplete={handleVerificationComplete} />}
              {step === 'final' && <FinalDecisionScreen {...sharedProps} onReset={handleReset} />}
            </main>
            <aside className="hidden lg:block w-80 flex-shrink-0 sticky top-24">
              <LogsPanel logs={logs} />
            </aside>
          </div>
        )}
      </div>
      <div className="lg:hidden fixed bottom-0 left-0 right-0 z-40">
        <LogsPanel logs={logs} mobile />
      </div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/*" element={<TrustOSApp />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
