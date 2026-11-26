import React, { useState, useRef, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Sparkles,
  Building2,
  Cloud,
  Activity,
  ChevronDown,
  Check,
  ExternalLink,
} from 'lucide-react';
import { useWorkspaceStore, PERSONAS } from '../../store/workspaceStore';

export const HeaderBar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    mode,
    setMode,
    runtimeTarget,
    localEngineDetected,
    setRuntimeTarget,
    persona,
    setPersona,
    tenant,
    openOnboardingModal,
    openTour,
  } = useWorkspaceStore();

  const [isUserDropdownOpen, setIsUserDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const isPipelinePage = location.pathname === '/pipeline';

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsUserDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header className="w-full bg-paper border-b border-ink-border/60 px-6 py-2.5 flex items-center justify-between gap-4 select-none flex-shrink-0 z-20">
      {/* Left: Mode Switcher */}
      <div className="flex items-center gap-3">
        <div className="p-0.5 bg-mist/90 border border-ink-border/80 rounded-control flex items-center shadow-xs">
          <button
            type="button"
            onClick={() => setMode('sandbox')}
            className={`px-3 py-1.5 rounded-control text-xs font-semibold transition-all flex items-center gap-1.5 ${
              mode === 'sandbox'
                ? 'bg-paper text-peacock shadow-xs border border-ink-border/60'
                : 'text-ink-muted hover:text-ink'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-peacock" />
            <span>Hackathon Demo Sandbox</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setMode('startup');
              if (tenant.status !== 'ACTIVE') {
                openOnboardingModal();
              }
            }}
            className={`px-3 py-1.5 rounded-control text-xs font-semibold transition-all flex items-center gap-1.5 ${
              mode === 'startup'
                ? 'bg-paper text-copper shadow-xs border border-ink-border/60'
                : 'text-ink-muted hover:text-ink'
            }`}
          >
            <Building2 className="w-3.5 h-3.5 text-copper" />
            <span>Live Startup Workspace</span>
          </button>
        </div>

        {/* Active Context & Hybrid Runtime Badge */}
        <div className="hidden lg:flex items-center gap-2 text-xs">
          {runtimeTarget === 'local' ? (
            <button
              type="button"
              onClick={() => setRuntimeTarget('cloud')}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-forest/10 border border-forest/30 rounded-full text-[11px] font-semibold text-forest hover:bg-forest/15 transition-colors"
              title="Connected to Local Desktop Engine (127.0.0.1:8742). Click to switch back to Cloud Showcase."
            >
              <span className="w-1.5 h-1.5 rounded-full bg-forest animate-pulse" />
              <span>Local Engine (127.0.0.1:8742 • Zero Egress)</span>
            </button>
          ) : localEngineDetected ? (
            <button
              type="button"
              onClick={() => setRuntimeTarget('local')}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-forest/15 border border-forest/40 rounded-full text-[11px] font-semibold text-forest hover:bg-forest/20 transition-colors"
              title="Local ARGUS Engine detected on 127.0.0.1:8742! Click to switch directly to live local data."
            >
              <span className="w-1.5 h-1.5 rounded-full bg-forest animate-ping" />
              <span>Local Engine Detected — Switch Live</span>
            </button>
          ) : mode === 'sandbox' ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-saffron/10 border border-saffron/25 rounded-full text-[11px] font-medium text-ink">
              <span className="w-1.5 h-1.5 rounded-full bg-saffron animate-pulse" />
              <span>Cloud Showcase • Zero Customer Secrets</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-forest/10 border border-forest/20 rounded-full text-[11px] font-medium text-forest">
              <span className="w-1.5 h-1.5 rounded-full bg-forest" />
              <span className="font-semibold">{tenant.orgName}</span>
              <span className="text-ink-muted font-mono">({tenant.awsAccountId} • {tenant.region})</span>
            </span>
          )}
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-2.5">
        {/* Interactive Tour Launcher */}
        <button
          type="button"
          onClick={openTour}
          className="px-2.5 py-1 text-xs font-semibold text-peacock bg-peacock/10 border border-peacock/30 hover:bg-peacock/15 rounded-control transition-colors flex items-center gap-1.5"
          title="Start non-blocking interactive tour"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Guided Tour</span>
        </button>

        {/* Connect Startup AWS / Local Scan button */}
        <button
          type="button"
          onClick={openOnboardingModal}
          className="px-2.5 py-1 text-xs font-medium text-ink-muted hover:text-ink border border-ink-border rounded-control hover:bg-mist/70 transition-colors flex items-center gap-1.5"
          title="Configure AWS account or scan GitHub / local Terraform infrastructure"
        >
          <Cloud className="w-3.5 h-3.5 text-peacock" />
          <span className="hidden sm:inline">
            {runtimeTarget === 'local' ? 'Scan Repo / AWS' : 'Connect AWS Account'}
          </span>
        </button>

        {/* Quick Link to Pipeline Visualizer */}
        {!isPipelinePage && (
          <button
            type="button"
            onClick={() => navigate('/pipeline')}
            className="px-2.5 py-1 text-xs font-semibold bg-peacock/10 text-peacock border border-peacock/25 rounded-control hover:bg-peacock/20 transition-colors flex items-center gap-1.5"
          >
            <Activity className="w-3.5 h-3.5 animate-pulse" />
            <span className="hidden md:inline">Run Pipeline (demo.py)</span>
          </button>
        )}

        {/* Live In-VPC Pill */}
        <div className="hidden xl:flex items-center gap-1.5 px-2 py-1 bg-mist/60 border border-ink-border/60 rounded-control text-[11px] text-ink-muted font-mono">
          <span className="w-1.5 h-1.5 rounded-full bg-forest" />
          <span>ap-south-1 Mumbai</span>
        </div>

        {/* User Persona Dropdown */}
        <div className="relative pl-1 border-l border-ink-border/60" ref={dropdownRef}>
          <button
            type="button"
            onClick={() => setIsUserDropdownOpen(!isUserDropdownOpen)}
            className="flex items-center gap-2 p-1 hover:bg-mist/70 rounded-control transition-colors cursor-pointer text-left"
            aria-expanded={isUserDropdownOpen}
          >
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold border ${
              persona.id === 'judge'
                ? 'bg-peacock/15 text-peacock border-peacock/30'
                : 'bg-copper/15 text-copper border-copper/30'
            }`}>
              {persona.initials}
            </div>
            <div className="hidden sm:block leading-tight">
              <p className="font-semibold text-xs text-ink">{persona.name}</p>
              <p className="text-[10px] text-ink-muted truncate max-w-[130px]">{persona.title}</p>
            </div>
            <ChevronDown className="w-3 h-3 text-ink-muted hidden sm:block" />
          </button>

          {/* Dropdown Menu */}
          {isUserDropdownOpen && (
            <div className="absolute right-0 mt-2 w-64 bg-paper border border-ink-border shadow-xl rounded-xl py-2 z-50 animate-fade-in text-xs">
              <div className="px-3 py-1.5 border-b border-ink-border/50 text-[11px] text-ink-muted">
                <span className="font-semibold text-ink uppercase tracking-wider text-[10px]">Select Evaluation Persona</span>
              </div>

              {/* Persona 1: Judge */}
              <button
                type="button"
                onClick={() => {
                  setPersona('judge');
                  setIsUserDropdownOpen(false);
                }}
                className={`w-full px-3 py-2 flex items-center justify-between text-left hover:bg-mist/80 transition-colors ${
                  persona.id === 'judge' ? 'bg-peacock/5 text-peacock font-semibold' : 'text-ink'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div className="w-6 h-6 rounded-full bg-peacock/15 text-peacock flex items-center justify-center text-[10px] font-bold">
                    JD
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-ink">{PERSONAS.judge.name}</p>
                    <p className="text-[10px] text-ink-muted">{PERSONAS.judge.org}</p>
                  </div>
                </div>
                {persona.id === 'judge' && <Check className="w-3.5 h-3.5 text-peacock" />}
              </button>

              {/* Persona 2: Startup CISO */}
              <button
                type="button"
                onClick={() => {
                  setPersona('startup_ciso');
                  setIsUserDropdownOpen(false);
                }}
                className={`w-full px-3 py-2 flex items-center justify-between text-left hover:bg-mist/80 transition-colors ${
                  persona.id === 'startup_ciso' ? 'bg-copper/5 text-copper font-semibold' : 'text-ink'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div className="w-6 h-6 rounded-full bg-copper/15 text-copper flex items-center justify-center text-[10px] font-bold">
                    AS
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-ink">{PERSONAS.startup_ciso.name}</p>
                    <p className="text-[10px] text-ink-muted">{PERSONAS.startup_ciso.org}</p>
                  </div>
                </div>
                {persona.id === 'startup_ciso' && <Check className="w-3.5 h-3.5 text-copper" />}
              </button>

              <div className="my-1 border-t border-ink-border/50" />

              {/* Action: Connect Custom Startup */}
              <button
                type="button"
                onClick={() => {
                  setIsUserDropdownOpen(false);
                  openOnboardingModal();
                }}
                className="w-full px-3 py-1.5 flex items-center gap-2 text-ink-muted hover:text-ink hover:bg-mist text-left text-xs"
              >
                <ExternalLink className="w-3.5 h-3.5 text-peacock" />
                <span>Onboard Real AWS Tenant...</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

