import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { getInterdiction, getInitialInterdiction } from '../api';
import { iamRem, SelectedFix } from '../types';
import { useBudgetStore, clampK } from '../store/budgetStore';
import { useWorkspaceStore } from '../store/workspaceStore';
import { FrontierChart } from '../components/plan/FrontierChart';
import { FooterTitleBlock } from '../components/layout/FooterTitleBlock';
import { ArrowRight, MapPin, AlertCircle, RefreshCw } from 'lucide-react';

const NUMBER_WORDS: Record<number, string> = {
  1: 'One',
  2: 'Two',
  3: 'Three',
  4: 'Four',
  5: 'Five',
  6: 'Six',
  7: 'Seven',
  8: 'Eight',
  9: 'Nine',
  10: 'Ten',
};

export const PlanPage: React.FC = () => {
  // URL param sync with fallback to store k (default 3)
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { runtimeTarget, workspaceRevision, tenant } = useWorkspaceStore();

  const urlParam = searchParams.get('k');
  const { k, setK } = useBudgetStore();
  const activeK = urlParam ? clampK(urlParam) : k;

  // Local sync to store on mount or url change
  useEffect(() => {
    if (urlParam) {
      const parsed = clampK(urlParam);
      if (parsed !== k) {
        setK(parsed);
      }
    } else {
      // Sync store K to url
      setSearchParams({ k: String(k) }, { replace: true });
    }
  }, [urlParam, k, setK, setSearchParams]);

  // Sync store K change back to URL ?k=N
  const handleBudgetChange = useCallback((newK: number) => {
    const clamped = clampK(newK);
    setK(clamped);
    setSearchParams({ k: String(clamped) }, { replace: true });
  }, [setK, setSearchParams]);

  // Data state initialized with activeK
  const [data, setData] = useState<iamRem>(() => getInitialInterdiction(activeK));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch when activeK changes
  const loadData = useCallback(async (budgetValue: number) => {
    try {
      setLoading(true);
      setError(null);
      const res = await getInterdiction(budgetValue);
      setData(res);
    } catch (err: any) {
      setError(err?.message || 'Failed to load interdiction plan.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(activeK);
  }, [activeK, loadData, runtimeTarget, workspaceRevision]);

  // Headline & subline derived from data
  const headline = useMemo(() => {
    const word = NUMBER_WORDS[activeK] || String(activeK);
    if (activeK === 1) return 'One fix removes most of your exposure.';
    return `${word} fixes remove most of your exposure.`;
  }, [activeK]);

  const baselinePct = Math.round((data.baseline_likelihood ?? 0.906) * 100);
  const residualPct = Math.round((data.residual_likelihood ?? 0.586) * 100);
  const subline = `Modelled attack likelihood drops from ${baselinePct}% to ${residualPct}%.`;

  // Attacker path cost formatting
  const baselineCost = data.baseline_path_cost ?? 1.2;
  const currentCost = data.attacker_shortest_path_cost ?? 5.8;
  const pathCostDisplay = `${baselineCost.toFixed(1)} → ${currentCost.toFixed(1)}`;

  // Display exactly activeK fixes
  const fixes: SelectedFix[] = useMemo(() => {
    return (data.selected_fixes || []).slice(0, activeK);
  }, [data.selected_fixes, activeK]);

  // Keyboard navigation on slider container
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Home') {
      e.preventDefault();
      handleBudgetChange(1);
    } else if (e.key === 'End') {
      e.preventDefault();
      handleBudgetChange(10);
    }
  };

  return (
    <div className="w-full space-y-5">
      {/* 1. Header Section */}
      <section className="space-y-1.5 max-w-3xl">
        <h1 className="font-headline text-3xl sm:text-4xl text-ink tracking-tight font-medium">
          {headline}
        </h1>
        <p className="text-[15px] text-ink-muted">
          {subline}
        </p>
      </section>

      {/* 2. Budget Slider Section (open on mist canvas, no boxed card, hairline divider) */}
      <section
        className="pt-1 pb-3 space-y-3 border-b border-ink-border"
        aria-label="Budget optimization controls"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <label
              htmlFor="budget-slider"
              className="font-medium text-[15px] text-ink block"
            >
              Fixes you can apply today
            </label>
            <p className="text-[12.5px] text-ink-muted">
              Choose the interdiction budget K. The algorithm selects the mathematically optimal subset.
            </p>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="text-[12px] uppercase font-mono text-ink-faint">Budget</span>
            <span className="font-headline text-3xl text-peacock font-medium tabular-nums min-w-[2rem] text-right">
              {activeK}
            </span>
          </div>
        </div>

        {/* The Range Input with tick marks */}
        <div className="space-y-2 pt-0.5">
          <input
            id="budget-slider"
            type="range"
            min={1}
            max={10}
            step={1}
            value={activeK}
            onChange={(e) => handleBudgetChange(parseInt(e.target.value, 10))}
            onKeyDown={handleKeyDown}
            aria-valuemin={1}
            aria-valuemax={10}
            aria-valuenow={activeK}
            aria-valuetext={`Budget of ${activeK} fixes`}
            className="w-full h-2 bg-ink-border/40 rounded-lg appearance-none cursor-pointer accent-peacock focus:outline-none focus:ring-2 focus:ring-peacock/40 transition-all"
          />

          {/* Tick marks 1 to 10 */}
          <div className="flex justify-between text-[11px] font-mono text-ink-faint px-0.5">
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((tick) => (
              <button
                key={tick}
                type="button"
                onClick={() => handleBudgetChange(tick)}
                className={`transition-colors hover:text-ink ${
                  tick === activeK ? 'text-peacock font-semibold' : ''
                }`}
              >
                {tick}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* 3. Metric Row: 3 open stats separated by hairlines */}
      <section
        className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-ink-border border-b border-ink-border py-3 text-ink select-none"
        aria-label="Impact metrics"
      >
        <div className="px-4 py-1.5 sm:py-0">
          <p className="text-[12px] text-ink-muted">Residual likelihood</p>
          <p className="font-headline text-2xl font-medium text-ink tabular-nums pt-0.5">
            {residualPct}%
          </p>
          <p className="text-[11px] text-ink-faint">Modelled attack likelihood</p>
        </div>

        <div className="px-4 py-1.5 sm:py-0">
          <p className="text-[12px] text-ink-muted">Attacker path cost</p>
          <p className="font-headline text-2xl font-medium text-peacock tabular-nums pt-0.5">
            {pathCostDisplay}
          </p>
          <p className="text-[11px] text-ink-faint">Shortest path distance to crown jewel</p>
        </div>

        <div className="px-4 py-1.5 sm:py-0">
          <p className="text-[12px] text-ink-muted">Fixes selected</p>
          <p className="font-headline text-2xl font-medium text-ink tabular-nums pt-0.5">
            {fixes.length}{' '}
            <span className="text-[13px] font-sans text-ink-muted font-normal">
              (budget K={activeK})
            </span>
          </p>
          <p className="text-[11px] text-ink-faint">MILP globally optimal frontier</p>
        </div>
      </section>

      {/* 4. Error or Loading State */}
      {error ? (
        <div className="p-6 bg-paper rounded-panel border border-garnet/40 text-garnet flex items-center justify-between">
          <div className="flex items-center gap-2 text-[14px]">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>Could not load the interdiction plan.</span>
          </div>
          <button
            onClick={() => loadData(k)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-control bg-peacock text-paper text-[12px] font-medium"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Try again</span>
          </button>
        </div>
      ) : loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 pt-2 animate-pulse">
          <div className="h-64 bg-ink-border/30 rounded-panel" />
          <div className="h-64 bg-ink-border/30 rounded-panel" />
        </div>
      ) : (
        /* 5. Two-column section with hairline divider */
        <section className="grid grid-cols-1 lg:grid-cols-2 lg:divide-x lg:divide-ink-border pt-1">
          {/* Left Column: Prioritised fixes ruled list */}
          <div className="pr-0 lg:pr-8 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-2 border-b border-ink-border">
                <h2 className="font-headline text-2xl text-ink font-medium">Prioritised fixes</h2>
                <span className="text-[12px] text-ink-muted">
                  Showing {fixes.length} {fixes.length === 1 ? 'fix' : 'fixes'}
                </span>
              </div>

              {/* Column Header */}
              <div className="flex items-center justify-between text-[12px] text-ink-faint py-2 border-b border-ink-border/60">
                <span className="w-8">Rank</span>
                <span className="flex-1 px-2">Remediation action</span>
                <span className="text-right">Marginal gain</span>
              </div>

              {/* Ruled List of Fixes */}
              <div className="divide-y divide-ink-border/50">
                {fixes.map((fix) => {
                  const gainPct = Math.round(fix.marginal_reduction * 100);
                  return (
                    <div
                      key={`${fix.finding_id}-${fix.rank}`}
                      className="py-2.5 flex items-start justify-between gap-3 group hover:bg-ink-border/30 -mx-1 px-1 rounded-control transition-colors"
                    >
                      {/* Rank */}
                      <span className="w-8 font-mono text-[12px] text-ink-faint pt-0.5">
                        #{fix.rank}
                      </span>

                      {/* Title & Resource */}
                      <div className="flex-1 min-w-0 pr-2 space-y-0.5">
                        <p className="text-[13.5px] font-medium text-ink group-hover:text-peacock transition-colors truncate">
                          {fix.title}
                        </p>
                        <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
                          <span className="font-mono text-ink-faint">{fix.resource_id}</span>
                          <span className="text-ink-border">•</span>
                          <span>{fix.rule_id}</span>
                        </div>
                      </div>

                      {/* Marginal Likelihood Reduction */}
                      <div className="text-right flex-shrink-0 pt-0.5">
                        {gainPct > 0 ? (
                          <span className="text-[13px] font-medium text-verdigris font-tabular">
                            -{gainPct}%
                          </span>
                        ) : (
                          <span className="text-[12px] font-mono text-ink-faint">
                            cut
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Bottom summary text */}
            <div className="pt-2.5 mt-2 border-t border-ink-border/60 text-[12px] text-ink-muted flex items-center justify-between">
              <span>Optimal cut set covers critical paths</span>
              <span className="font-mono text-[11px] text-ink-faint">
                {fixes.length} selected
              </span>
            </div>
          </div>

          {/* Right Column: Frontier Line Chart */}
          <div className="pl-0 lg:pl-8 mt-6 lg:mt-0">
            <FrontierChart
              data={data.pareto_curve || []}
              selectedK={activeK}
            />
          </div>
        </section>
      )}

      {/* 6. Action buttons left-aligned */}
      <section className="flex flex-wrap items-center gap-4 pt-2">
        <button
          onClick={() => navigate('/approvals')}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-control bg-peacock text-paper font-medium text-[14px] hover:bg-peacock-hover active:bg-peacock-dark transition-colors shadow-sm"
        >
          <span>Send these fixes to approvals</span>
          <ArrowRight strokeWidth={1.5} className="w-4 h-4" />
        </button>

        <button
          onClick={() => navigate('/map')}
          className="inline-flex items-center gap-1.5 text-peacock hover:underline font-medium text-[13px] px-2 py-2"
        >
          <MapPin strokeWidth={1.5} className="w-4 h-4" />
          <span>See the cuts on the map</span>
        </button>
      </section>

      {/* 7. Footer Title Block */}
      <FooterTitleBlock
        scanId={tenant.tenantId || 'scan-swasthya-mumbai-042'}
        region={tenant.region || 'ap-south-1'}
        scannedTime={tenant.connectedAt || 'Verified MILP Solve'}
        isOnDevice={true}
      />
    </div>
  );
};
