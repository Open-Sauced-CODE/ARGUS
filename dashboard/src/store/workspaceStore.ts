import { create } from 'zustand';
import { HealthPayload, LocalStatusPayload, TenantInfo } from '../types';

export interface UserPersona {
  id: 'judge' | 'startup_ciso' | 'custom';
  name: string;
  title: string;
  org: string;
  initials: string;
  email: string;
}

export const PERSONAS: Record<'judge' | 'startup_ciso', UserPersona> = {
  judge: {
    id: 'judge',
    name: 'Hackathon Judge / Evaluator',
    title: 'Evaluation Jury',
    org: 'Campus to Cloud • IIT Bombay & AWS',
    initials: 'JD',
    email: 'judge@evaluation.aws',
  },
  startup_ciso: {
    id: 'startup_ciso',
    name: 'Arjun Sharma',
    title: 'Chief Information Security Officer',
    org: 'SwasthyaPay Technologies Pvt Ltd',
    initials: 'AS',
    email: 'arjun.sharma@swasthya-pay.in',
  },
};

function detectInitialRuntimeTarget(): 'cloud' | 'local' {
  if (typeof window !== 'undefined') {
    const { hostname, port } = window.location;
    if ((hostname === '127.0.0.1' || hostname === 'localhost') && port === '8742') {
      return 'local';
    }
  }
  return 'cloud';
}

interface WorkspaceState {
  mode: 'sandbox' | 'startup';
  runtimeTarget: 'cloud' | 'local';
  workspaceRevision: number;
  localEngineUrl: string;
  localEngineDetected: boolean;
  localEngineChecking: boolean;
  localStatus: LocalStatusPayload | null;
  serverHealth: HealthPayload | null;
  persona: UserPersona;
  isOnboardingModalOpen: boolean;
  isTourOpen: boolean;
  tourDock: 'bottom-right' | 'bottom-left';
  tenant: TenantInfo;

  setMode: (mode: 'sandbox' | 'startup') => void;
  setPersona: (personaId: 'judge' | 'startup_ciso' | 'custom', custom?: Partial<UserPersona>) => void;
  setRuntimeTarget: (target: 'cloud' | 'local') => void;
  bumpWorkspaceRevision: () => void;
  setLocalEngineDetected: (detected: boolean, status?: LocalStatusPayload | null) => void;
  setLocalEngineChecking: (checking: boolean) => void;
  setServerHealth: (health: HealthPayload | null) => void;
  openOnboardingModal: () => void;
  closeOnboardingModal: () => void;
  openTour: () => void;
  closeTour: () => void;
  toggleTourDock: () => void;
  connectTenant: (tenantData: Partial<TenantInfo>, keepModalOpen?: boolean) => void;
  resetToSandbox: () => void;
}

const DEFAULT_STARTUP_TENANT: TenantInfo = {
  tenantId: 'tnt_in_9021',
  orgName: 'SwasthyaPay Technologies Pvt Ltd',
  awsAccountId: '987654321098',
  region: 'ap-south-1',
  iamRoleArn: 'arn:aws:iam::987654321098:role/argus-audit-role',
  externalId: 'argus-tnt-9021-mumbai',
  ollamaEndpoint: 'http://localhost:11434',
  status: 'ACTIVE',
  nodesDiscovered: 48,
  edgesDiscovered: 112,
  rulesEvaluated: 12,
  dpdpScore: 98,
  connectedAt: '2026-11-21T11:45:00Z',
};

const initialTarget = detectInitialRuntimeTarget();

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  mode: initialTarget === 'local' ? 'startup' : 'sandbox',
  runtimeTarget: initialTarget,
  workspaceRevision: 0,
  localEngineUrl: 'http://127.0.0.1:8742',
  localEngineDetected: initialTarget === 'local',
  localEngineChecking: false,
  localStatus: null,
  serverHealth: null,
  persona: initialTarget === 'local' ? PERSONAS.startup_ciso : PERSONAS.judge,
  isOnboardingModalOpen: false,
  isTourOpen: false,
  tourDock: 'bottom-right',
  tenant: DEFAULT_STARTUP_TENANT,

  setMode: (mode) =>
    set({
      mode,
      persona: mode === 'sandbox' ? PERSONAS.judge : PERSONAS.startup_ciso,
    }),

  setRuntimeTarget: (runtimeTarget) =>
    set((state) => ({
      runtimeTarget,
      workspaceRevision: state.workspaceRevision + 1,
      mode: runtimeTarget === 'local' ? 'startup' : state.mode,
      persona: runtimeTarget === 'local' ? PERSONAS.startup_ciso : state.persona,
    })),

  bumpWorkspaceRevision: () =>
    set((state) => ({ workspaceRevision: state.workspaceRevision + 1 })),

  setLocalEngineDetected: (localEngineDetected, localStatus = null) =>
    set((state) => ({
      localEngineDetected,
      localStatus: localStatus ?? state.localStatus,
    })),

  setLocalEngineChecking: (localEngineChecking) => set({ localEngineChecking }),

  setServerHealth: (serverHealth) =>
    set((state) => {
      if (!serverHealth) return { serverHealth };
      const isLocalBackend = serverHealth.runtime_mode === 'local_agent';
      const localOrigin =
        isLocalBackend && typeof window !== 'undefined'
          ? window.location.origin
          : state.localEngineUrl;
      return {
        serverHealth,
        runtimeTarget: isLocalBackend ? 'local' : state.runtimeTarget,
        localEngineDetected: isLocalBackend ? true : state.localEngineDetected,
        localEngineUrl: localOrigin,
        mode: isLocalBackend ? 'startup' : state.mode,
        persona: isLocalBackend ? PERSONAS.startup_ciso : state.persona,
      };
    }),

  setPersona: (personaId, custom) =>
    set(() => {
      if (personaId === 'judge') {
        return { persona: PERSONAS.judge, mode: 'sandbox' };
      }
      if (personaId === 'startup_ciso') {
        return { persona: PERSONAS.startup_ciso, mode: 'startup' };
      }
      return {
        persona: {
          id: 'custom',
          name: custom?.name || 'DevSecOps Engineer',
          title: custom?.title || 'Security Lead',
          org: custom?.org || 'Custom Indian Startup',
          initials: custom?.initials || 'DS',
          email: custom?.email || 'security@startup.in',
        },
        mode: 'startup',
      };
    }),

  openOnboardingModal: () => set({ isOnboardingModalOpen: true }),
  closeOnboardingModal: () => set({ isOnboardingModalOpen: false }),

  openTour: () => set({ isTourOpen: true }),
  closeTour: () => set({ isTourOpen: false }),
  toggleTourDock: () =>
    set((state) => ({
      tourDock: state.tourDock === 'bottom-right' ? 'bottom-left' : 'bottom-right',
    })),

  connectTenant: (tenantData, keepModalOpen = false) =>
    set((state) => ({
      mode: 'startup',
      persona: {
        ...PERSONAS.startup_ciso,
        org: tenantData.orgName || state.tenant.orgName,
      },
      isOnboardingModalOpen: keepModalOpen ? state.isOnboardingModalOpen : false,
      tenant: {
        ...state.tenant,
        ...tenantData,
        status: 'ACTIVE',
        connectedAt: new Date().toISOString(),
      },
    })),

  resetToSandbox: () =>
    set((state) => ({
      mode: 'sandbox',
      runtimeTarget: 'cloud',
      workspaceRevision: state.workspaceRevision + 1,
      persona: PERSONAS.judge,
    })),
}));

