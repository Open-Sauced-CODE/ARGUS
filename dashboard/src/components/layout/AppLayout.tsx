import React, { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { NavRail } from './NavRail';
import { HeaderBar } from './HeaderBar';
import { useFindingsStore } from '../../store/findingsStore';
import { useWorkspaceStore } from '../../store/workspaceStore';
import { getFindings, getHealth, getLocalStatus, probeLocalEngine } from '../../api';
import { OnboardingTutorial } from '../common/OnboardingTutorial';
import { StartupConnectModal } from '../startup/StartupConnectModal';

export const AppLayout: React.FC = () => {
  const location = useLocation();
  const {
    isOnboardingModalOpen,
    openOnboardingModal,
    closeOnboardingModal,
    isTourOpen,
    openTour,
    closeTour,
    localEngineUrl,
    setServerHealth,
    setLocalEngineDetected,
    runtimeTarget,
  } = useWorkspaceStore();

  // Sync backend health, optional local engine bridge probe, and findings on boot / target switch
  useEffect(() => {
    getHealth()
      .then((h) => {
        if (h) setServerHealth(h);
        if (h?.runtime_mode !== 'local_agent') {
          return probeLocalEngine(localEngineUrl)
            .then((status) => {
              if (status) setLocalEngineDetected(true, status);
            })
            .catch(() => {});
        }
        return undefined;
      })
      .catch(() => {
        probeLocalEngine(localEngineUrl)
          .then((status) => {
            if (status) setLocalEngineDetected(true, status);
          })
          .catch(() => {});
      });

    if (new URLSearchParams(location.search).get('connect') === '1') {
      openOnboardingModal();
    }
  }, []);

  useEffect(() => {
    getFindings().catch((err) => console.warn('Could not sync findings with backend:', err));
    if (runtimeTarget === 'local') {
      getLocalStatus()
        .then((st) => setLocalEngineDetected(true, st))
        .catch(() => {});
    }
  }, [runtimeTarget]);

  const pendingCount = useFindingsStore((s) =>
    s.findings.filter(
      (f) => f.auto_apply_status === 'NEEDS_APPROVAL' || f.auto_apply_status === 'ESCALATED'
    ).length
  );

  const isFullBleed = location.pathname === '/map';

  return (
    <div className="flex h-screen bg-mist text-ink overflow-hidden">
      {/* Left Navigation Rail */}
      <NavRail
        approvalsCount={pendingCount}
        onOpenTutorial={openTour}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header Bar with Mode Switcher & Tenant Profile */}
        <HeaderBar />

        {/* Page Container */}
        {isFullBleed ? (
          <main className="flex-1 min-h-0 overflow-hidden">
            <Outlet />
          </main>
        ) : (
          <main className="flex-1 px-8 py-4 w-full max-w-7xl mx-auto overflow-y-auto">
            <Outlet />
          </main>
        )}
      </div>

      {/* Interactive Startup Tutorial Walkthrough (Floating non-blocking card) */}
      <OnboardingTutorial
        forceOpen={isTourOpen}
        onClose={closeTour}
      />

      {/* Startup Cloud Infrastructure Connect Modal */}
      <StartupConnectModal
        isOpen={isOnboardingModalOpen}
        onClose={closeOnboardingModal}
      />
    </div>
  );
};
