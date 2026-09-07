import React, { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Layout/Sidebar';
import Header from './components/Layout/Header';
import ErrorBoundary from './components/ErrorBoundary';
import { useWebSocket } from './hooks/useWebSocket';

import Dashboard from './pages/Dashboard';
import Topology from './pages/Topology';
import Redundancy from './pages/Redundancy';
import Devices from './pages/Devices';
import Links from './pages/Links';
import Discovery from './pages/Discovery';
import PlatformSettings from './pages/PlatformSettings';
import Login from './pages/Login';
import PasswordChange from './components/PasswordChange';
import api, { getAuthToken, setAuthToken } from './api/client';

const DeviceAnalytics = lazy(() => import('./pages/DeviceAnalytics'));
const Alerts = lazy(() => import('./pages/Alerts'));
const History = lazy(() => import('./pages/History'));
const Reports = lazy(() => import('./pages/Reports'));
const SystemHealth = lazy(() => import('./pages/SystemHealth'));
const loadingPage = <div className="analytics-state">Loading page…</div>;

export default function App() {
  const [user,setUser]=useState(null); const [checkingAuth,setCheckingAuth]=useState(true); const [authError,setAuthError]=useState(''); const [changingPassword,setChangingPassword]=useState(false); const [feedback,setFeedback]=useState('');
  const completeLogin=authenticatedUser=>{window.history.replaceState(null,'','/');setUser(authenticatedUser)};
  const checkSession=()=>{const token=getAuthToken();setAuthError('');if(!token){setCheckingAuth(false);return}setCheckingAuth(true);api.get('/auth/me').then(response=>setUser(response.data)).catch(error=>{if(!error.response)setAuthError('The backend is unavailable. Confirm that NetMonitor is running on port 5555.')}).finally(()=>setCheckingAuth(false))};
  useEffect(()=>{checkSession();const expired=()=>setUser(null);window.addEventListener('netmonitor:session-expired',expired);return()=>window.removeEventListener('netmonitor:session-expired',expired)},[]);
  const { isConnected } = useWebSocket(() => {}, Boolean(user));
  const logout=async()=>{try{await api.post('/auth/logout')}catch{}setAuthToken(null);window.history.replaceState(null,'','/');setUser(null)};

  if(checkingAuth)return <div className="analytics-state">Checking secure session…</div>;
  if(authError)return <div className="analytics-state"><strong>Unable to open the secure session</strong><span>{authError}</span><button className="btn btn-primary" onClick={checkSession}>Try again</button></div>;
  if(!user)return <Login onAuthenticated={completeLogin}/>;
  if(user.must_change_password||changingPassword)return <PasswordChange forced={user.must_change_password} onCancel={()=>setChangingPassword(false)} onComplete={()=>{setUser(current=>({...current,must_change_password:false}));setChangingPassword(false);setFeedback('Password updated successfully. Your other active sessions were signed out for security.');window.setTimeout(()=>setFeedback(''),6000)}}/>;

  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar user={user} />
        <div className="main-content">
          <Header isConnected={isConnected} user={user} onLogout={logout} onChangePassword={()=>setChangingPassword(true)} />
          <div className="page-body">
            {feedback&&<div className="notice success" role="status">{feedback}</div>}
            <ErrorBoundary>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/topology" element={<Topology />} />
                <Route path="/redundancy" element={<Redundancy user={user} />} />
                <Route path="/alerts" element={<Suspense fallback={loadingPage}><Alerts /></Suspense>} />
                <Route path="/devices" element={<Devices user={user} />} />
                <Route path="/devices/:deviceId" element={<Suspense fallback={<div className="analytics-state">Loading device metrics…</div>}><DeviceAnalytics /></Suspense>} />
                <Route path="/links" element={<Links user={user} />} />
                <Route path="/history" element={<Suspense fallback={loadingPage}><History /></Suspense>} />
                <Route path="/reports" element={<Suspense fallback={loadingPage}><Reports /></Suspense>} />
                <Route path="/discovery" element={<Discovery user={user} />} />
                <Route path="/settings" element={<PlatformSettings />} />
                {user.role === 'ADMINISTRATOR' && <Route path="/system-health" element={<Suspense fallback={loadingPage}><SystemHealth /></Suspense>} />}
              </Routes>
            </ErrorBoundary>
          </div>
        </div>
      </div>
    </BrowserRouter>
  );
}
