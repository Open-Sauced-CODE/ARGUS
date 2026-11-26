import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Home,
  Map as MapIcon,
  Route,
  ShieldCheck,
  UserCheck,
  FileCheck2,
  Cpu,
  Sparkles,
  Activity,
  BarChart3,
  BookOpen,
  Download,
} from 'lucide-react';
import { Logo } from '../common/LogoMark';
import { useWorkspaceStore } from '../../store/workspaceStore';

interface NavRailProps {
  approvalsCount?: number;
  onOpenTutorial?: () => void;
}

export const NavRail: React.FC<NavRailProps> = ({
  approvalsCount = 9,
  onOpenTutorial,
}) => {
  const { runtimeTarget } = useWorkspaceStore();

  const workspaceItems = [
    { to: '/', label: 'Overview', icon: Home, end: true },
    { to: '/pipeline', label: 'Live Pipeline', icon: Activity, badge: 'Live' },
    { to: '/map', label: 'Attack Map', icon: MapIcon },
    { to: '/plan', label: 'Plan (MILP)', icon: Route },
    { to: '/compliance', label: 'Compliance', icon: ShieldCheck },
    {
      to: '/approvals',
      label: 'Approvals',
      icon: UserCheck,
      badge: approvalsCount > 0 ? approvalsCount : undefined,
    },
    { to: '/proof', label: 'Privacy Proof', icon: FileCheck2 },
  ];

  const platformItems = [
    { to: '/results', label: 'Results & OOF', icon: BarChart3, badge: '94.5%' },
    { to: '/architecture', label: 'Architecture', icon: Cpu },
    { to: '/docs', label: 'Documentation', icon: BookOpen },
    { to: '/downloads', label: 'Versions & .exe', icon: Download, badge: 'v2.0' },
  ];

  const renderGroup = (title: string, items: typeof workspaceItems) => (
    <div className="space-y-0.5">
      <p className="px-3 pb-1 text-[10px] font-mono uppercase tracking-wider text-ink-faint font-semibold">
        {title}
      </p>
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `
              group relative flex items-center justify-between px-3 py-2 rounded-control text-[13.5px] font-medium transition-colors duration-150
              ${
                isActive
                  ? 'bg-peacock text-paper font-semibold shadow-sm'
                  : 'text-ink-muted hover:text-ink hover:bg-mist/70'
              }
            `}
          >
            {({ isActive }) => (
              <>
                <div className="flex items-center gap-2.5 min-w-0">
                  <Icon
                    strokeWidth={1.5}
                    className={`w-4 h-4 flex-shrink-0 transition-colors ${
                      isActive ? 'text-paper' : 'text-ink-muted group-hover:text-ink'
                    }`}
                  />
                  <span className="truncate">{item.label}</span>
                </div>

                {item.badge !== undefined && (
                  <span
                    className={`
                      inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-[11px] font-semibold rounded-full tabular-nums flex-shrink-0
                      ${
                        isActive
                          ? 'bg-saffron text-ink'
                          : 'bg-saffron/20 text-saffron-dark group-hover:bg-saffron group-hover:text-ink'
                      }
                    `}
                  >
                    {item.badge}
                  </span>
                )}
              </>
            )}
          </NavLink>
        );
      })}
    </div>
  );

  return (
    <aside className="w-60 flex-shrink-0 flex flex-col justify-between border-r border-ink-border/60 bg-paper py-5 px-3.5 h-screen overflow-y-auto select-none">
      <div>
        {/* Brand Header */}
        <div className="px-2 mb-6">
          <Logo />
        </div>

        {/* Navigation Groups */}
        <nav className="space-y-5" aria-label="Main Navigation">
          {renderGroup('Workspace', workspaceItems)}
          {renderGroup('Platform & Docs', platformItems)}
        </nav>
      </div>

      {/* Bottom Area: Tutorial Launcher & Live Deployment Status */}
      <div className="pt-4 mt-4 border-t border-ink-border/50 space-y-2.5">
        <button
          type="button"
          onClick={onOpenTutorial}
          className="w-full flex items-center justify-between px-3 py-2 rounded-control text-xs font-semibold text-peacock bg-peacock/10 hover:bg-peacock/15 transition-colors border border-peacock/20"
        >
          <div className="flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Interactive Tour</span>
          </div>
          <span className="text-[10px] uppercase font-mono px-1 bg-peacock/20 rounded">Demo</span>
        </button>

        <div className="p-2.5 bg-mist/50 border border-ink-border/60 rounded-control text-[11px] text-ink-muted space-y-1">
          <div className="flex items-center gap-1.5 text-forest font-semibold">
            <span className="w-1.5 h-1.5 rounded-full bg-forest animate-pulse" />
            <span>{runtimeTarget === 'local' ? 'Local Engine (127.0.0.1)' : 'AWS ap-south-1 Showcase'}</span>
          </div>
          <p className="text-[10px] text-ink-muted/80 leading-tight">
            {runtimeTarget === 'local'
              ? 'Zero cloud egress active. Local scanners + OPA gate ready.'
              : 'Zero customer secrets stored on AWS EC2. Pre-seeded sandbox.'}
          </p>
        </div>
      </div>
    </aside>
  );
};
