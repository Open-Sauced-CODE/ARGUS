import React, { useEffect, useState } from 'react';
import {
  Monitor,
  ShieldCheck,
  Cpu,
  Terminal,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Clock,
  ExternalLink,
  Copy,
  Package,
  Download,
  FolderSearch,
  Info,
  Sparkles,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  getReleases,
  getLocalStatus,
  probeLocalEngine,
  importLocalModelApi,
  getDiscoveredModelsApi,
  pickLocalFileApi,
  pullOllamaModelApi,
  getPullStatusApi,
  startOllamaApi,
} from '../api';
import { useWorkspaceStore } from '../store/workspaceStore';
import { ReleasesPayload, LocalStatusPayload, DiscoveredGguf, OllamaPullStatus } from '../types';
import { FooterTitleBlock } from '../components/layout/FooterTitleBlock';
import rawReleases from '../mock/mockReleases.json';

export const DownloadsPage: React.FC = () => {
  const navigate = useNavigate();
  const {
    runtimeTarget,
    workspaceRevision,
    localEngineUrl,
    localEngineDetected,
    localStatus,
    setLocalEngineDetected,
    setRuntimeTarget,
    openOnboardingModal,
  } = useWorkspaceStore();

  const [releases, setReleases] = useState<ReleasesPayload>(() =>
    JSON.parse(JSON.stringify(rawReleases))
  );
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);

  // Model onboarding states
  const [discoveredGgufs, setDiscoveredGgufs] = useState<DiscoveredGguf[]>([]);
  const [ggufPath, setGgufPath] = useState('');
  const [importModelName, setImportModelName] = useState('argus-m1-sft');
  const [importingModel, setImportingModel] = useState(false);
  const [browsingGguf, setBrowsingGguf] = useState(false);
  const [startingOllama, setStartingOllama] = useState(false);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  // Background Ollama Pull states
  const [pullTag, setPullTag] = useState('');
  const [pullStatus, setPullStatus] = useState<OllamaPullStatus | null>(null);
  const [pullError, setPullError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    getReleases()
      .then((res) => {
        if (mounted && res?.current_release) setReleases(res);
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, [runtimeTarget, workspaceRevision]);

  const refreshDiscovered = async () => {
    const state = useWorkspaceStore.getState();
    if (!state.localEngineDetected || state.runtimeTarget !== 'local') return;
    try {
      const [data, freshStatus] = await Promise.all([
        getDiscoveredModelsApi(),
        getLocalStatus().catch(() => null),
      ]);
      setDiscoveredGgufs(data.ggufs || []);
      if (data.pull_status) setPullStatus(data.pull_status);
      if (freshStatus) {
        setLocalEngineDetected(true, freshStatus);
      } else if (state.localStatus) {
        setLocalEngineDetected(true, { ...state.localStatus, ollama: data.ollama });
      }
    } catch {}
  };

  useEffect(() => {
    if (localEngineDetected && runtimeTarget === 'local') {
      refreshDiscovered();
    }
  }, [localEngineDetected, runtimeTarget]);

  // Poll active pull progress
  useEffect(() => {
    if (!pullStatus?.active) return;
    const timer = setInterval(async () => {
      try {
        const st = await getPullStatusApi();
        setPullStatus(st);
        if (!st.active) {
          await refreshDiscovered();
        }
      } catch {}
    }, 1000);
    return () => clearInterval(timer);
  }, [pullStatus?.active]);

  const handleProbeLocal = async () => {
    setProbing(true);
    setProbeError(null);
    const status: LocalStatusPayload | null = await probeLocalEngine(localEngineUrl);
    setProbing(false);
    if (status) {
      setLocalEngineDetected(true, status);
      if (status.discovered_ggufs) setDiscoveredGgufs(status.discovered_ggufs);
    } else {
      setLocalEngineDetected(false, null);
      setProbeError(
        `No ARGUS Local Engine detected at ${localEngineUrl}. Launch ARGUS Desktop or deploy_dashboard.py --local to connect.`
      );
    }
  };

  const handleCopy = (key: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCmd(key);
    setTimeout(() => setCopiedCmd(null), 2000);
  };

  const handleBrowseGguf = async () => {
    if (browsingGguf) return;
    setImportError(null);
    setBrowsingGguf(true);
    try {
      const firstDiscovered = discoveredGgufs[0]?.path;
      const initDir = firstDiscovered
        ? firstDiscovered.replace(/[\\/][^\\/]+$/, '')
        : undefined;
      const selected = await pickLocalFileApi(initDir);
      if (selected) {
        setGgufPath(selected);
        if (selected.toLowerCase().includes('rft')) {
          setImportModelName('argus-m1-rft');
        } else {
          setImportModelName('argus-m1-sft');
        }
      }
    } catch (err: any) {
      setImportError(err?.message || 'Could not open native file dialog.');
    } finally {
      setBrowsingGguf(false);
    }
  };

  const handleStartOllama = async () => {
    setStartingOllama(true);
    setImportError(null);
    setImportMessage(null);
    try {
      await startOllamaApi();
      setImportMessage('Local Ollama daemon started and reachable on 127.0.0.1:11434.');
      const refreshed = await probeLocalEngine(localEngineUrl);
      if (refreshed) setLocalEngineDetected(true, refreshed);
      await refreshDiscovered();
    } catch (err: any) {
      setImportError(err?.message || 'Could not start Ollama automatically. Launch Ollama for Windows first.');
    } finally {
      setStartingOllama(false);
    }
  };

  const handleImportModel = async (pathOverride?: string, nameOverride?: string) => {
    const targetPath = (pathOverride ?? ggufPath).trim();
    const targetName = nameOverride ?? importModelName;
    if (!targetPath) {
      setImportError('Select or enter the local path to your Q4_K_M .gguf file first.');
      return;
    }
    setImportingModel(true);
    setImportError(null);
    setImportMessage(null);
    try {
      const res = await importLocalModelApi(targetPath, targetName);
      setImportMessage(
        `Registered ${res.model_name} in local Ollama (${res.template_source || 'qwen3.5 template'}).`
      );
      const refreshed = await probeLocalEngine(localEngineUrl);
      if (refreshed) setLocalEngineDetected(true, refreshed);
      await refreshDiscovered();
    } catch (err: any) {
      setImportError(err?.message || 'GGUF import failed.');
    } finally {
      setImportingModel(false);
    }
  };

  const handlePullModel = async (tagOverride?: string) => {
    const targetTag = (tagOverride ?? pullTag).trim();
    if (!targetTag) {
      setPullStatus(null);
      setImportMessage(null);
      setPullError('Enter an Ollama or Hugging Face tag (e.g. qwen3.5:4b or hf.co/<org>/argus-m1-sft-gguf:Q4_K_M), or use Browse .gguf offline.');
      return;
    }
    if (tagOverride) {
      setPullTag(tagOverride);
    }
    setPullError(null);
    setImportError(null);
    setImportMessage(null);
    try {
      const st = await pullOllamaModelApi(targetTag);
      setPullStatus(st);
    } catch (err: any) {
      setPullStatus(null);
      setPullError(err?.message || 'Could not start Ollama pull.');
    }
  };

  const isBuildReady = releases.desktop_build_status === 'READY';
  const launchLocalCmd = `.\\.venv\\Scripts\\python.exe deploy_dashboard.py --local`;

  return (
    <div className="w-full space-y-7 pb-12">
      {/* Header */}
      <section className="space-y-2 max-w-4xl">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-semibold text-peacock bg-peacock/10 rounded-full">
            <Package className="w-3.5 h-3.5" />
            <span>Versions & Desktop Releases Hub</span>
          </span>
          {isBuildReady ? (
            <span className="px-2.5 py-0.5 text-[11px] font-mono font-semibold bg-forest/15 text-forest border border-forest/30 rounded">
              Windows Desktop {releases.latest_version}: LIVE RELEASE READY
            </span>
          ) : (
            <span className="px-2 py-0.5 text-[11px] font-mono bg-saffron/15 text-saffron-dark border border-saffron/30 rounded">
              Desktop .exe Packaging: Pending Build
            </span>
          )}
        </div>
        <h1 className="font-headline text-3xl sm:text-4xl text-ink tracking-tight font-medium">
          ARGUS Desktop Agent & Version Releases
        </h1>
        <p className="text-[15px] text-ink-muted leading-relaxed">
          To uphold India DPDP Act 2023 Zero-Data-Egress guarantees, real AWS/Terraform scanning and local Qwen3.5-4B inference
          run strictly inside your private workstation (<code className="font-mono text-xs bg-paper px-1.5 py-0.5 rounded border border-ink-border">127.0.0.1:8742</code>),
          never on this public AWS showcase portal.
        </p>
      </section>

      {/* Hero Desktop Release Card */}
      <section className="bg-paper border border-ink-border rounded-2xl p-6 shadow-sm space-y-5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-ink-border/60 pb-5">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <Monitor className="w-5 h-5 text-peacock" />
              <h2 className="font-headline text-2xl font-medium text-ink">
                ARGUS Desktop ({releases.latest_version}) — Windows 10 / 11 (x64)
              </h2>
              {isBuildReady ? (
                <span className="px-2.5 py-0.5 text-[11px] font-mono font-semibold bg-forest/15 text-forest border border-forest/30 rounded-full flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" />
                  <span>Live Binary Ready</span>
                </span>
              ) : (
                <span className="px-2.5 py-0.5 text-[11px] font-mono font-semibold bg-saffron/15 text-saffron-dark border border-saffron/30 rounded-full">
                  Pending Build
                </span>
              )}
            </div>
            <p className="text-xs text-ink-muted max-w-2xl leading-relaxed">
              Self-contained Windows desktop agent bundling Python runtime, NetworkX + SciPy/PuLP MILP solvers, Fernet TokenVault Airlock,
              bundled <code className="font-mono">opa.exe</code>, HCL2 scanner, system tray launcher, and React console (zero Python/Docker prerequisites).
            </p>
          </div>

          <a
            href={releases.repo_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-peacock bg-peacock/10 border border-peacock/25 rounded-control hover:bg-peacock/15 transition-colors flex-shrink-0"
          >
            <span>Source Repository (GitHub)</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>

        {/* Artifact Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {releases.current_release.artifacts.map((art) => {
            const ready = Boolean(art.download_ready && art.download_url);
            return (
              <div
                key={art.id}
                className={`p-4 rounded-xl flex flex-col justify-between gap-4 ${
                  ready
                    ? 'bg-mist/40 border border-forest/35 shadow-xs'
                    : 'bg-mist/40 border border-dashed border-ink-border'
                }`}
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs font-bold text-ink">{art.name}</span>
                    <span
                      className={`px-2 py-0.5 text-[10px] font-mono font-semibold rounded ${
                        ready ? 'bg-forest/20 text-forest' : 'bg-saffron/20 text-ink'
                      }`}
                    >
                      {ready ? 'READY' : art.status}
                    </span>
                  </div>
                  <p className="text-xs text-ink-muted">
                    <strong>Target:</strong> {art.platform} • {art.packaging}
                  </p>
                  <p className="text-xs text-ink-muted">
                    <strong>Size:</strong> {art.size_display || art.estimated_size}
                  </p>
                  <p className="text-[11px] text-ink-muted leading-relaxed">{art.notes}</p>
                </div>

                <div className="space-y-2.5 pt-2 border-t border-ink-border/50">
                  <div className="p-2 bg-paper border border-ink-border/70 rounded text-[10.5px] font-mono text-ink-muted flex items-center justify-between gap-2">
                    <span className="truncate">
                      <strong className="text-ink">SHA-256:</strong> {art.sha256}
                    </span>
                    {ready && /^[a-f0-9]{64}$/i.test(art.sha256) && (
                      <button
                        type="button"
                        onClick={() => handleCopy(`sha-${art.id}`, art.sha256)}
                        className="px-2 py-0.5 bg-mist hover:bg-ink-border/40 text-ink rounded flex-shrink-0"
                      >
                        {copiedCmd === `sha-${art.id}` ? 'Copied' : 'Copy'}
                      </button>
                    )}
                  </div>

                  {ready && art.download_url ? (
                    <a
                      href={art.download_url}
                      download={art.name}
                      className="w-full py-2.5 px-3 rounded-control bg-peacock text-paper text-xs font-semibold flex items-center justify-center gap-2 hover:bg-peacock-hover transition-colors shadow-sm"
                    >
                      <Download className="w-4 h-4" />
                      <span>Download {art.id === 'win64-installer' ? 'Windows Installer (.exe)' : 'Portable Archive (.zip)'}</span>
                    </a>
                  ) : (
                    <button
                      type="button"
                      disabled
                      className="w-full py-2 px-3 rounded-control bg-ink-border/60 text-ink-muted text-xs font-semibold flex items-center justify-center gap-2 cursor-not-allowed"
                    >
                      <Clock className="w-3.5 h-3.5" />
                      <span>Binary Release Pending</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* 3-Step First-Launch Checklist & SmartScreen Guidance */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 pt-1">
          <div className="lg:col-span-7 p-4 bg-peacock/5 border border-peacock/20 rounded-xl space-y-2.5 text-xs">
            <div className="flex items-center gap-2 font-semibold text-peacock">
              <Sparkles className="w-4 h-4" />
              <span>3-Step Startup Quickstart After Download</span>
            </div>
            <ol className="space-y-1.5 text-ink-muted list-decimal pl-4 leading-relaxed">
              <li>
                <strong className="text-ink">Install & Launch:</strong> Run <code className="font-mono">ARGUS-Desktop-Setup-{releases.latest_version}-win64.exe</code> (installs per-user to <code className="font-mono">%LocalAppData%\ARGUS-Desktop</code> with zero Admin UAC prompt). The tray icon opens <code className="font-mono">http://127.0.0.1:8742</code> automatically.
              </li>
              <li>
                <strong className="text-ink">Verify Readiness & Model:</strong> Confirm <code className="font-mono">opa.exe</code> + Privacy Airlock show Ready, then load <code className="font-mono">argus-m1-sft</code> into local Ollama via 1-click <code className="font-mono">.gguf</code> picker or <code className="font-mono">ollama pull</code>.
              </li>
              <li>
                <strong className="text-ink">Scan Real Infrastructure:</strong> Click <strong className="text-ink">Scan Repo / AWS</strong> to clone a GitHub Terraform repo locally, browse a local <code className="font-mono">.tf</code> folder, or scan a read-only AWS CLI profile (<code className="font-mono">iam_guard</code> verified), then export <code className="font-mono">.patch</code> fixes & DPDP Audit ZIP.
              </li>
            </ol>
          </div>

          <div className="lg:col-span-5 p-4 bg-saffron/10 border border-saffron/30 rounded-xl space-y-2 text-xs">
            <div className="flex items-center gap-2 font-semibold text-saffron-dark">
              <Info className="w-4 h-4 flex-shrink-0" />
              <span>Windows SmartScreen & Integrity Note</span>
            </div>
            <p className="text-ink-muted leading-relaxed">
              This open-source hackathon/research build is not signed with a commercial Authenticode EV certificate.
              If Windows SmartScreen displays <em>&ldquo;Windows protected your PC&rdquo;</em>, click{' '}
              <strong className="text-ink">More info &rarr; Run anyway</strong>, and verify the exact SHA-256 above using:
            </p>
            <code className="block p-2 bg-ink text-paper rounded text-[10.5px] font-mono overflow-x-auto">
              Get-FileHash .\ARGUS-Desktop-Setup-{releases.latest_version}-win64.exe -Algorithm SHA256
            </code>
          </div>
        </div>
      </section>

      {/* Live Local Engine Hybrid Bridge Card */}
      <section className="bg-paper border border-ink-border rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-ink-border/60 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <Terminal className="w-5 h-5 text-forest" />
              <h2 className="font-headline text-xl font-medium text-ink">
                Hybrid Local Engine Bridge (<code className="font-mono text-base">127.0.0.1:8742</code>)
              </h2>
            </div>
            <p className="text-xs text-ink-muted mt-1">
              Whether launched from <code className="font-mono">ARGUS.exe</code> or Python source, this browser connects directly to your loopback engine with zero EC2 egress.
            </p>
          </div>

          <button
            type="button"
            onClick={handleProbeLocal}
            disabled={probing}
            className="px-4 py-2 text-xs font-semibold bg-peacock text-paper rounded-control hover:bg-peacock-hover transition-colors flex items-center gap-1.5 shadow-sm flex-shrink-0"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${probing ? 'animate-spin' : ''}`} />
            <span>{probing ? 'Probing 127.0.0.1:8742...' : 'Check Local Engine (127.0.0.1:8742)'}</span>
          </button>
        </div>

        {/* Source Fallback Launch Command Box */}
        <div className="p-3.5 bg-ink text-paper rounded-xl space-y-1.5">
          <div className="flex items-center justify-between gap-3">
            <code className="text-xs font-mono overflow-x-auto">{launchLocalCmd}</code>
            <button
              type="button"
              onClick={() => handleCopy('launch', launchLocalCmd)}
              className="px-2.5 py-1 text-[11px] font-mono bg-paper/10 hover:bg-paper/20 text-paper rounded flex items-center gap-1 flex-shrink-0"
            >
              <Copy className="w-3 h-3" />
              <span>{copiedCmd === 'launch' ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
          <p className="text-[11px] font-mono text-paper/70">
            Developer source mode (Windows / macOS / Linux): binds strictly to 127.0.0.1:8742
          </p>
        </div>

        {/* Probe Result */}
        {localEngineDetected && localStatus && (
          <div className="p-4 bg-forest/10 border border-forest/30 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-1 text-xs">
              <div className="flex items-center gap-2 text-forest font-bold">
                <CheckCircle2 className="w-4 h-4" />
                <span>Local Engine Connected at {localEngineUrl}</span>
              </div>
              <p className="text-ink-muted font-mono">
                OPA Rego: {localStatus.opa_ready ? 'Bundled Ready' : 'Fallback'} • Airlock: {localStatus.airlock_ready === false ? 'Unavailable' : 'Ready'} • Ollama:{' '}
                {localStatus.ollama?.running ? `Running (${localStatus.ollama.models.length} models)` : 'Offline (T0 Active)'} • M2: {localStatus.m2_status?.status}
              </p>
            </div>

            {runtimeTarget !== 'local' ? (
              <button
                type="button"
                onClick={() => {
                  setRuntimeTarget('local');
                  navigate('/');
                }}
                className="px-4 py-2 text-xs font-semibold bg-forest text-paper rounded-control hover:bg-forest/90 transition-colors flex-shrink-0"
              >
                Switch Dashboard to Local Engine
              </button>
            ) : (
              <button
                type="button"
                onClick={openOnboardingModal}
                className="px-4 py-2 text-xs font-semibold bg-forest text-paper rounded-control hover:bg-forest/90 transition-colors flex-shrink-0"
              >
                Open Scan & Readiness Wizard
              </button>
            )}
          </div>
        )}

        {probeError && (
          <div className="p-3 bg-mist/70 border border-ink-border rounded-control flex items-center gap-2 text-xs text-ink-muted">
            <AlertCircle className="w-4 h-4 text-saffron-dark flex-shrink-0" />
            <span>{probeError}</span>
          </div>
        )}
      </section>

      {/* Model Packs & Local Ollama Setup */}
      <section className="bg-paper border border-ink-border rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ink-border/60 pb-3">
          <div className="flex items-center gap-2">
            <Cpu className="w-5 h-5 text-peacock" />
            <h2 className="font-headline text-xl font-medium text-ink">
              Local Ollama M1 Model Packs (Qwen3.5-4B Q4_K_M GGUF)
            </h2>
          </div>
          <span className="text-xs font-mono text-forest font-semibold">
            Tier 0 Templates Work Immediately Without GGUF
          </span>
        </div>

        <p className="text-xs text-ink-muted leading-relaxed">
          Quantized 4B GGUF weights are <strong>2.59 GiB</strong> (exceeding GitHub Releases&apos; 2.0 GiB single-file limit), so they are distributed separately from the thin desktop installer via Ollama / Hugging Face registry or direct 1-click <code className="font-mono">.gguf</code> import inside the desktop app—without needing a 3.4 GB base model pull.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {releases.current_release.model_packs.map((mp) => {
            const isLoaded =
              localStatus?.ollama?.models?.some((m) => m.startsWith(mp.id)) ?? false;
            return (
              <div key={mp.id} className="p-4 bg-mist/40 border border-ink-border rounded-xl space-y-2.5">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold text-ink">{mp.name}</h3>
                  <span
                    className={`px-2 py-0.5 text-[10px] font-mono rounded font-semibold ${
                      isLoaded
                        ? 'bg-forest/15 text-forest'
                        : 'bg-peacock/10 text-peacock'
                    }`}
                  >
                    {isLoaded ? 'READY IN OLLAMA' : 'SEPARATE GGUF'}
                  </span>
                </div>
                <p className="text-xs text-ink-muted">
                  {mp.base_model} • {mp.size} •{' '}
                  <strong className="text-peacock">{mp.pass_at_1_oof || mp.pass_at_1_c_verifier}</strong>
                </p>
                <p className="text-[11px] text-ink-muted">{mp.notes}</p>
                <div className="p-2.5 bg-ink text-paper rounded text-[10.5px] font-mono overflow-x-auto flex items-center justify-between gap-2">
                  <span className="truncate">{mp.register_cmd}</span>
                  <button
                    type="button"
                    onClick={() => handleCopy(mp.id, mp.register_cmd)}
                    className="px-2 py-0.5 bg-paper/10 hover:bg-paper/20 rounded flex-shrink-0"
                  >
                    {copiedCmd === mp.id ? 'Copied' : 'Copy'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {localEngineDetected && runtimeTarget === 'local' && (
          <div className="p-4 bg-forest/5 border border-forest/25 rounded-xl space-y-4 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-ink">
                1-Click Local Model Onboarding (<code className="font-mono">127.0.0.1:8742</code> &rarr; Ollama)
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[10.5px] font-mono text-forest">
                  {localStatus?.ollama?.running
                    ? `Ollama v${localStatus.ollama.version || '?'} • SFT: ${localStatus.ollama.argus_sft_ready ? 'Ready' : 'Not loaded'} • RFT: ${localStatus.ollama.argus_rft_ready ? 'Ready' : 'Not loaded'}`
                    : 'Ollama offline — click Start Ollama or install Ollama for Windows'}
                </span>
                {!localStatus?.ollama?.running && localStatus?.ollama?.ollama_installed && (
                  <button
                    type="button"
                    disabled={startingOllama}
                    onClick={handleStartOllama}
                    className="px-2.5 py-1 bg-peacock text-paper rounded-control text-[11px] font-semibold hover:bg-peacock-hover disabled:opacity-50"
                  >
                    {startingOllama ? 'Starting...' : 'Start Ollama'}
                  </button>
                )}
              </div>
            </div>

            {localStatus?.ollama?.running && (localStatus.ollama.models?.length ?? 0) > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[10.5px] font-semibold text-ink-muted">Active in Ollama:</span>
                {localStatus.ollama.models.map((m) => (
                  <span
                    key={m}
                    className={`px-2 py-0.5 rounded font-mono text-[10px] border ${
                      m.includes('argus-m1')
                        ? 'bg-forest/15 text-forest border-forest/30 font-semibold'
                        : 'bg-paper text-ink-muted border-ink-border'
                    }`}
                  >
                    {m}
                  </span>
                ))}
              </div>
            )}

            {/* Auto-discovered GGUF list */}
            {discoveredGgufs.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-[11px] font-semibold text-ink-muted uppercase tracking-wider">
                  Discovered Local .gguf Weights on Disk
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {discoveredGgufs.map((g) => (
                    <div
                      key={g.path}
                      className="p-2.5 bg-paper border border-ink-border rounded-lg flex items-center justify-between gap-2"
                    >
                      <div className="min-w-0">
                        <p className="font-mono font-semibold text-ink truncate">{g.name}</p>
                        <p className="text-[10.5px] text-ink-muted truncate">
                          {g.size_gb} GB • {g.path}
                        </p>
                      </div>
                      <button
                        type="button"
                        disabled={importingModel}
                        onClick={() => handleImportModel(g.path, g.suggested_model_name)}
                        className="px-2.5 py-1 bg-forest text-paper rounded-control font-semibold hover:bg-forest/90 disabled:opacity-50 flex-shrink-0"
                      >
                        Import as {g.suggested_model_name}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* File Picker + Import */}
            <div className="space-y-1.5">
              <p className="text-[11px] font-semibold text-ink-muted uppercase tracking-wider">
                Browse Any Local .gguf File (Zero Base Download Required)
              </p>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="text"
                  value={ggufPath}
                  onChange={(e) => setGgufPath(e.target.value)}
                  placeholder="D:\ARGUS\Qwen3.5-4B.Q4_K_M.gguf"
                  className="flex-1 px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                />
                <button
                  type="button"
                  disabled={browsingGguf}
                  onClick={handleBrowseGguf}
                  className="px-3 py-1.5 bg-paper border border-ink-border hover:bg-mist disabled:opacity-60 text-ink rounded-control font-semibold flex items-center justify-center gap-1.5"
                >
                  <FolderSearch className="w-3.5 h-3.5 text-peacock" />
                  <span>{browsingGguf ? 'Opening...' : 'Browse .gguf...'}</span>
                </button>
                <select
                  value={importModelName}
                  onChange={(e) => setImportModelName(e.target.value)}
                  className="px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                >
                  <option value="argus-m1-sft">argus-m1-sft</option>
                  <option value="argus-m1-rft">argus-m1-rft</option>
                </select>
                <button
                  type="button"
                  onClick={() => handleImportModel()}
                  disabled={importingModel}
                  className="px-3.5 py-1.5 bg-peacock text-paper rounded-control font-semibold hover:bg-peacock-hover disabled:opacity-50"
                >
                  {importingModel ? 'Registering...' : 'Register in Ollama'}
                </button>
              </div>
            </div>

            {/* Pull via Ollama / Hugging Face */}
            <div className="space-y-2 pt-2 border-t border-forest/20">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] font-semibold text-ink-muted uppercase tracking-wider">
                  Or Pull / Verify Directly via Ollama Registry
                </p>
                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    disabled={Boolean(pullStatus?.active)}
                    onClick={() => handlePullModel('argus-m1-sft')}
                    className="px-2 py-0.5 text-[10px] font-mono bg-paper border border-forest/40 text-forest rounded hover:bg-forest/10 disabled:opacity-50"
                  >
                    Verify / Load argus-m1-sft
                  </button>
                  <button
                    type="button"
                    disabled={Boolean(pullStatus?.active)}
                    onClick={() => handlePullModel('qwen3.5:4b')}
                    className="px-2 py-0.5 text-[10px] font-mono bg-paper border border-ink-border text-ink rounded hover:bg-mist disabled:opacity-50"
                  >
                    Pull qwen3.5:4b
                  </button>
                </div>
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  type="text"
                  value={pullTag}
                  onChange={(e) => {
                    setPullTag(e.target.value);
                    if (pullError) setPullError(null);
                  }}
                  placeholder="hf.co/<org>/argus-m1-sft-gguf:Q4_K_M (optional; or use Browse .gguf offline)"
                  className="flex-1 px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                />
                <button
                  type="button"
                  onClick={() => handlePullModel()}
                  disabled={Boolean(pullStatus?.active)}
                  className="px-3.5 py-1.5 bg-forest text-paper rounded-control font-semibold hover:bg-forest/90 disabled:opacity-50"
                >
                  {pullStatus?.active ? `Pulling (${pullStatus.percent}%)...` : 'Pull via Ollama'}
                </button>
              </div>
              {pullStatus && pullStatus.status !== 'idle' && (
                <div className="p-2.5 bg-paper border border-ink-border rounded space-y-1">
                  <div className="flex justify-between font-mono text-[11px]">
                    <span className="text-ink truncate pr-2">{pullStatus.model}: {pullStatus.status}</span>
                    <span className="text-peacock font-semibold flex-shrink-0">{pullStatus.percent}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-mist rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all ${pullStatus.error ? 'bg-garnet' : 'bg-forest'}`}
                      style={{ width: `${Math.min(100, Math.max(0, pullStatus.percent))}%` }}
                    />
                  </div>
                  {pullStatus.error && <p className="text-garnet text-[11px] font-medium">{pullStatus.error}</p>}
                  {pullStatus.success && !pullStatus.error && (
                    <p className="text-forest text-[11px] font-medium">
                      Ready in local Ollama ({pullStatus.model}).
                    </p>
                  )}
                </div>
              )}
              {pullError && <p className="text-garnet font-medium">{pullError}</p>}
            </div>

            {importError && <p className="text-garnet font-medium">{importError}</p>}
            {importMessage && <p className="text-forest font-medium">{importMessage}</p>}
          </div>
        )}
      </section>

      {/* Version Changelog */}
      <section className="bg-paper border border-ink-border rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center gap-2 border-b border-ink-border/60 pb-3">
          <ShieldCheck className="w-5 h-5 text-peacock" />
          <h2 className="font-headline text-xl font-medium text-ink">Release History & Milestones</h2>
        </div>

        <div className="space-y-4">
          {releases.versions.map((ver) => (
            <div key={ver.version} className="p-4 bg-mist/40 border border-ink-border/80 rounded-xl space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-peacock">{ver.version}</span>
                  <span className="text-sm font-semibold text-ink">{ver.title}</span>
                </div>
                <div className="flex items-center gap-2 text-[11px] font-mono text-ink-muted">
                  <span>{ver.date}</span>
                  <span className="px-2 py-0.5 bg-paper border border-ink-border rounded">{ver.tag}</span>
                </div>
              </div>
              <ul className="space-y-1 text-xs text-ink-muted list-disc pl-5">
                {ver.highlights.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <FooterTitleBlock
        scanId={`release-${releases.latest_version}`}
        region="ap-south-1 (Mumbai) & Local Windows"
        scannedTime={isBuildReady ? 'Release Verified & Ready' : 'Pending Binary Build'}
        isOnDevice={runtimeTarget === 'local'}
      />
    </div>
  );
};

export default DownloadsPage;
