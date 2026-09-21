import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { TraceProvider } from './contexts/TraceContext';
import Layout from './components/Layout';

// 9 screens per §31.1
import SubmitRequest from './pages/SubmitRequest';
import RequestStatus from './pages/RequestStatus';
import Sources from './pages/Sources';
import ConfidenceMatrix from './pages/ConfidenceMatrix';
import Conflicts from './pages/Conflicts';
import InformationUnits from './pages/InformationUnits';
import AgentsSolicited from './pages/AgentsSolicited';
import Traceability from './pages/Traceability';
import RequestHistory from './pages/RequestHistory';

import './styles/index.css';
import './styles/App.css';

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <TraceProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<SubmitRequest />} />
              <Route path="requests/status" element={<RequestStatus />} />
              <Route path="requests/:id" element={<RequestStatus />} />
              <Route path="history" element={<RequestHistory />} />
              <Route path="sources" element={<Sources />} />
              <Route path="information" element={<InformationUnits />} />
              <Route path="conflicts" element={<Conflicts />} />
              <Route path="confidence" element={<ConfidenceMatrix />} />
              <Route path="agents" element={<AgentsSolicited />} />
              <Route path="traceability" element={<Traceability />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </TraceProvider>
    </AuthProvider>
  );
};

export default App;
