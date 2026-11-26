import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
import { OverviewPage } from './pages/OverviewPage';
import { PipelinePage } from './pages/PipelinePage';
import { MapPage } from './pages/MapPage';
import { PlanPage } from './pages/PlanPage';
import { CompliancePage } from './pages/CompliancePage';
import { ApprovalsPage } from './pages/ApprovalsPage';
import { ProofPage } from './pages/ProofPage';
import { ArchitecturePage } from './pages/ArchitecturePage';
import { ResultsPage } from './pages/ResultsPage';
import { DocsPage } from './pages/DocsPage';
import { DownloadsPage } from './pages/DownloadsPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<OverviewPage />} />
          <Route path="pipeline" element={<PipelinePage />} />
          <Route path="map" element={<MapPage />} />
          <Route path="plan" element={<PlanPage />} />
          <Route path="compliance" element={<CompliancePage />} />
          <Route path="approvals" element={<ApprovalsPage />} />
          <Route path="proof" element={<ProofPage />} />
          <Route path="results" element={<ResultsPage />} />
          <Route path="architecture" element={<ArchitecturePage />} />
          <Route path="docs" element={<DocsPage />} />
          <Route path="downloads" element={<DownloadsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
