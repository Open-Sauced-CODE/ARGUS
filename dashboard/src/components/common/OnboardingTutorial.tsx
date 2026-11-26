import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  ShieldAlert,
  Network,
  Route,
  Activity,
  CheckCircle2,
  X,
  ChevronRight,
  ChevronLeft,
  Sparkles,
  Minimize2,
  Maximize2,
  Lock,
  MoveHorizontal,
} from 'lucide-react';
import { useWorkspaceStore } from '../../store/workspaceStore';

interface OnboardingTutorialProps {
  forceOpen?: boolean;
  onClose?: () => void;
}

export const OnboardingTutorial: React.FC<OnboardingTutorialProps> = ({
  forceOpen = false,
  onClose,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isTourOpen, closeTour, tourDock, toggleTourDock } = useWorkspaceStore();

  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (forceOpen || isTourOpen) {
      setIsOpen(true);
      setIsMinimized(false);
      setStep(0);
      if (location.pathname !== '/') {
        navigate('/');
      }
      return;
    }
    const hasSeen = localStorage.getItem('argus_tutorial_completed_v3');
    if (!hasSeen) {
      const timer = setTimeout(() => {
        setIsOpen(true);
        setIsMinimized(false);
      }, 600);
      return () => clearTimeout(timer);
    }
  }, [forceOpen, isTourOpen]);

  const handleClose = () => {
    localStorage.setItem('argus_tutorial_completed_v3', 'true');
    setIsOpen(false);
    closeTour();
    if (onClose) onClose();
  };

  const steps = [
    {
      title: 'The Indian Startup Challenge: DPDP Act 2023',
      subtitle: 'Why organizations handling citizen data cannot use public cloud LLMs',
      icon: ShieldAlert,
      iconColor: 'text-rose-700 bg-rose-50 border-rose-200',
      badge: 'Step 1 of 6 • Statutory Risk',
      previewPath: '/',
      content: (
        <div className="space-y-3 text-[13px] text-slate-700 leading-relaxed">
          <p>
            Under India's <strong className="text-slate-900 font-semibold">Digital Personal Data Protection (DPDP) Act 2023</strong> (Rules 6, 6a, 7, 8, 15), 
            Indian startups and institutions face statutory penalties up to <span className="font-bold text-rose-700 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200">₹250 Crores (~$30M)</span> for 
            citizen PII leaks, unencrypted data stores, or missing forensic audit trails.
          </p>
          <div className="p-3 bg-amber-50/90 border border-amber-300 rounded-lg text-slate-800 text-xs space-y-1">
            <span className="font-bold text-amber-900 flex items-center gap-1">
              ⚠️ The Sovereign Data Privacy Conflict:
            </span>
            <p className="text-slate-700 leading-normal">
              Piping production Terraform configs, IAM access keys, or citizen Aadhaar records to external LLM APIs (OpenAI, Anthropic) 
              violates statutory sovereignty rules. ARGUS runs <strong className="text-slate-900">100% on-device / in-VPC</strong> with zero data egress.
            </p>
          </div>
        </div>
      ),
      actionLabel: 'Next: Attack Graph Analysis',
    },
    {
      title: 'Cartographic Attack Graph & Blast Radius',
      subtitle: 'Multi-hop privilege escalation discovery to Crown Jewels',
      icon: Network,
      iconColor: 'text-teal-700 bg-teal-50 border-teal-200',
      badge: 'Step 2 of 6 • Attack Graph',
      previewPath: '/map',
      content: (
        <div className="space-y-3 text-[13px] text-slate-700 leading-relaxed">
          <p>
            Real security breaches do not occur in silos. Attackers chain mundane misconfigurations across compute, identity, and storage layers into multi-hop attack graphs.
          </p>
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-2 text-xs">
            <div className="flex items-start gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-teal-600 mt-1.5 flex-shrink-0" />
              <p>
                <strong className="text-slate-900">Cartography Ingestion:</strong> Ingests AWS IAM, EC2, VPC, and S3 resources into an interconnected Neo4j graph.
              </p>
            </div>
            <div className="flex items-start gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-teal-600 mt-1.5 flex-shrink-0" />
              <p>
                <strong className="text-slate-900">Personalized PageRank:</strong> Calculates the exact mathematical probability that an attacker reaches sensitive crown jewels.
              </p>
            </div>
            <div className="flex items-start gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-teal-600 mt-1.5 flex-shrink-0" />
              <p>
                <strong className="text-slate-900">Live Canvas:</strong> Look at the graph behind this card to see lateral movement paths in real time.
              </p>
            </div>
          </div>
        </div>
      ),
      actionLabel: 'Next: Interdiction Planning',
    },
    {
      title: 'Game-Theoretic Network Interdiction (MILP)',
      subtitle: 'Minimum-cost cut-set optimization on the Pareto frontier',
      icon: Route,
      iconColor: 'text-indigo-700 bg-indigo-50 border-indigo-200',
      badge: 'Step 3 of 6 • Stackelberg Optimizer',
      previewPath: '/plan',
      content: (
        <div className="space-y-3 text-[13px] text-slate-700 leading-relaxed">
          <p>
            Security teams face severe alert fatigue and limited engineering bandwidth (e.g. 3–5 fixes per sprint). ARGUS formulates remediation as a 
            <strong className="text-slate-900"> Stackelberg Game</strong> solved via Mixed-Integer Linear Programming.
          </p>
          <div className="p-3 bg-emerald-50 border border-emerald-300 rounded-lg text-slate-800 text-xs space-y-1">
            <p className="font-bold text-emerald-900">The 80/20 Interdiction Theorem:</p>
            <p className="text-slate-700 leading-normal">
              Setting budget <code className="font-mono bg-white px-1.5 py-0.5 rounded border border-emerald-200 text-emerald-800 font-bold">K=3</code> cuts attacker reaching likelihood from 
              <strong className="text-rose-700 font-bold"> 90.6%</strong> down to <strong className="text-emerald-700 font-bold">31.0%</strong>, severing the primary exploit corridor with minimal operational cost.
            </p>
          </div>
        </div>
      ),
      actionLabel: 'Next: Live Pipeline Visualizer',
    },
    {
      title: 'Live Autonomous Pipeline Visualizer',
      subtitle: 'Bringing demo.py to life with full 6-stage interactive transparency',
      icon: Activity,
      iconColor: 'text-amber-700 bg-amber-50 border-amber-300',
      badge: 'Step 4 of 6 • Live Pipeline',
      previewPath: '/pipeline',
      content: (
        <div className="space-y-3 text-[13px] text-slate-700 leading-relaxed">
          <p>
            Watch ARGUS execute in real time across 6 coordinated stages:
          </p>
          <div className="grid grid-cols-2 gap-1.5 text-[11px] font-mono text-slate-800">
            <span className="p-1.5 bg-slate-100 rounded border border-slate-200 font-medium">1. Cloud IaC Ingestion</span>
            <span className="p-1.5 bg-slate-100 rounded border border-slate-200 font-medium">2. Privacy Airlock (HMAC)</span>
            <span className="p-1.5 bg-slate-100 rounded border border-slate-200 font-medium">3. PageRank Blast Radius</span>
            <span className="p-1.5 bg-slate-100 rounded border border-slate-200 font-medium">4. Local Ollama Model (M1)</span>
            <span className="p-1.5 bg-slate-100 rounded border border-slate-200 font-medium">5. OPA Rego Policy Gate</span>
            <span className="p-1.5 bg-slate-100 rounded border border-slate-200 font-medium">6. Terraform HCL Diff</span>
          </div>
          <p className="text-xs text-slate-600">
            You can test 4 real-world misconfigurations with both <strong className="text-slate-800">Auto-Play</strong> and <strong className="text-slate-800">Step-by-Step</strong> controls on the live pipeline page.
          </p>
        </div>
      ),
      actionLabel: 'Next: Verification & Approvals',
    },
    {
      title: 'Formal Verification Gate & Approvals',
      subtitle: 'Open Policy Agent (Rego) policy gate prevents AI hallucination',
      icon: CheckCircle2,
      iconColor: 'text-teal-700 bg-teal-50 border-teal-200',
      badge: 'Step 5 of 6 • Safety Gate',
      previewPath: '/approvals',
      content: (
        <div className="space-y-3 text-[13px] text-slate-700 leading-relaxed">
          <p>
            Unlike unconstrained AI assistants, ARGUS passes every generated patch through a formal 
            <strong className="text-slate-900"> OPA Rego Verification Gate</strong> enforcing:
          </p>
          <ul className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1.5 text-xs text-slate-800">
            <li className="flex items-start gap-1.5">
              <span className="text-teal-600 font-bold">✓</span>
              <span><strong>Schema Conformance:</strong> 100% syntactically valid JSON Patch-IR.</span>
            </li>
            <li className="flex items-start gap-1.5">
              <span className="text-teal-600 font-bold">✓</span>
              <span><strong>Intent Preservation:</strong> 0 unauthorized resource deletions.</span>
            </li>
            <li className="flex items-start gap-1.5">
              <span className="text-teal-600 font-bold">✓</span>
              <span><strong>Risk-Controlled Dispatch:</strong> High-confidence certified fixes auto-apply; complex cases route to human architect review.</span>
            </li>
          </ul>
        </div>
      ),
      actionLabel: 'Next: Privacy Receipts',
    },
    {
      title: 'Zero-Egress Cryptographic Privacy Proof',
      subtitle: 'Tamper-evident proof that 0 bytes left your local tenancy',
      icon: Lock,
      iconColor: 'text-blue-700 bg-blue-50 border-blue-200',
      badge: 'Step 6 of 6 • Cryptographic Proof',
      previewPath: '/proof',
      content: (
        <div className="space-y-3 text-[13px] text-slate-700 leading-relaxed">
          <p>
            Every execution generates a tamper-evident, cryptographically signed 
            <strong className="text-slate-900"> Privacy Receipt</strong> containing HMAC-SHA256 digests.
          </p>
          <div className="p-3 bg-blue-50 border border-blue-300 rounded-lg text-slate-800 text-xs space-y-1">
            <span className="font-bold text-blue-900 flex items-center gap-1">
              🛡️ Auditor-Ready Statutory Evidence:
            </span>
            <p className="text-slate-700 leading-normal">
              Provides irrefutable technical evidence to the Data Protection Board of India (DPBI) and CERT-In 
              proving that proprietary secrets, AWS keys, and Aadhaar numbers remained strictly within your local VPC boundary.
            </p>
          </div>
        </div>
      ),
      actionLabel: 'Finish Tour & Explore',
    },
  ];

  if (!isOpen) return null;

  const currentStep = steps[step];
  const StepIcon = currentStep.icon;

  const goToStep = (targetStep: number) => {
    setStep(targetStep);
    const target = steps[targetStep];
    if (target && target.previewPath && location.pathname !== target.previewPath) {
      navigate(target.previewPath);
    }
  };

  const handleNext = () => {
    if (step < steps.length - 1) {
      goToStep(step + 1);
    } else {
      handleClose();
    }
  };

  const handlePrev = () => {
    if (step > 0) {
      goToStep(step - 1);
    }
  };

  const dockPositionClass =
    tourDock === 'bottom-left' ? 'bottom-4 left-6' : 'bottom-4 right-6';

  // Minimized floating pill view
  if (isMinimized) {
    return (
      <div className={`fixed ${dockPositionClass} z-50 animate-fade-in select-none`}>
        <div className="flex items-center gap-2.5 px-4 py-2 bg-white text-slate-900 border-2 border-slate-300 shadow-2xl rounded-full text-xs font-semibold">
          <Sparkles className="w-4 h-4 text-teal-700 animate-pulse" />
          <span>ARGUS Tour ({step + 1}/6): <span className="text-slate-600 font-normal">{currentStep.badge.split('•')[1]}</span></span>
          <button
            onClick={() => setIsMinimized(false)}
            className="p-1 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-full transition-colors ml-1"
            title="Expand tour card"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleClose}
            className="p-1 text-slate-400 hover:text-slate-900 hover:bg-slate-100 rounded-full transition-colors"
            title="Close tour"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    );
  }

  // Expanded non-blocking floating tour card (100% OPAQUE background - crystal clear text, NO screen blur)
  return (
    <aside
      className={`fixed ${dockPositionClass} z-50 w-full max-w-[440px] bg-white border-2 border-slate-300 shadow-[0_20px_50px_rgba(0,0,0,0.35)] rounded-2xl overflow-hidden flex flex-col animate-slide-up select-none pointer-events-auto`}
      role="complementary"
      aria-label="ARGUS Guided Tour"
      style={{ backgroundColor: '#FFFFFF' }}
    >
      {/* Top Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-slate-50">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 text-[11px] font-bold text-teal-800 bg-teal-50 border border-teal-200 rounded-full">
            <Sparkles className="w-3 h-3 text-teal-700" />
            <span>Interactive Tour</span>
          </span>
          <span className="text-[11px] text-slate-600 font-mono font-medium">{currentStep.badge}</span>
        </div>
        <div className="flex items-center gap-1 text-slate-500">
          <button
            onClick={toggleTourDock}
            className="p-1.5 hover:text-slate-900 hover:bg-slate-200 rounded-md transition-colors"
            title={tourDock === 'bottom-left' ? 'Move to bottom-right' : 'Move to bottom-left'}
          >
            <MoveHorizontal className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsMinimized(true)}
            className="p-1.5 hover:text-slate-900 hover:bg-slate-200 rounded-md transition-colors"
            title="Minimize tour card"
          >
            <Minimize2 className="w-4 h-4" />
          </button>
          <button
            onClick={handleClose}
            className="p-1.5 hover:text-slate-900 hover:bg-slate-200 rounded-md transition-colors"
            title="Close tour"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Card Body - 100% Solid White with high-contrast text */}
      <div className="px-5 py-4 flex-1 space-y-3 bg-white text-slate-900 max-h-[360px] overflow-y-auto">
        <div className="flex items-start gap-3">
          <div className={`p-2.5 rounded-xl border flex-shrink-0 ${currentStep.iconColor}`}>
            <StepIcon className="w-5 h-5 stroke-[2]" />
          </div>
          <div className="space-y-0.5">
            <h3 className="font-sans text-base font-bold text-slate-950 leading-snug">
              {currentStep.title}
            </h3>
            <p className="text-[12px] text-slate-600 font-medium">
              {currentStep.subtitle}
            </p>
          </div>
        </div>

        <div className="pt-1">{currentStep.content}</div>
      </div>

      {/* Footer Stepper & Controls */}
      <div className="px-5 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
        {/* Stepper Dots */}
        <div className="flex items-center gap-1.5">
          {steps.map((_, idx) => (
            <button
              key={idx}
              onClick={() => goToStep(idx)}
              className={`h-2 rounded-full transition-all duration-200 ${
                idx === step
                  ? 'w-6 bg-teal-700'
                  : 'w-2 bg-slate-300 hover:bg-slate-400'
              }`}
              title={`Go to step ${idx + 1}`}
            />
          ))}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          {step > 0 && (
            <button
              type="button"
              onClick={handlePrev}
              className="px-2.5 py-1 text-xs font-semibold text-slate-700 hover:text-slate-900 border border-slate-300 rounded-md hover:bg-white transition-colors flex items-center gap-0.5"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              <span>Back</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleClose}
            className="px-2 py-1 text-xs font-medium text-slate-500 hover:text-slate-900 transition-colors"
          >
            Skip
          </button>

          <button
            type="button"
            onClick={handleNext}
            className="px-3.5 py-1.5 text-xs font-semibold bg-teal-800 text-white rounded-md hover:bg-teal-900 active:bg-teal-950 transition-colors shadow-sm flex items-center gap-1"
          >
            <span>{currentStep.actionLabel}</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
};
