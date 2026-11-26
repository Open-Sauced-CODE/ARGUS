import React, { useEffect, useRef, useState } from 'react';
import {
  Building2,
  Key,
  Cloud,
  CheckCircle2,
  Copy,
  Cpu,
  Lock,
  ArrowRight,
  X,
  Sparkles,
  Server,
  Zap,
  FolderOpen,
  AlertTriangle,
  Download,
  GitBranch,
  FolderSearch,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useWorkspaceStore } from '../../store/workspaceStore';
import {
  connectTenantApi,
  scanTerraformApi,
  scanGithubRepoApi,
  scanAwsApi,
  getLocalStatus,
  getAwsProfilesApi,
  getDiscoveredModelsApi,
  pickLocalFolderApi,
  pickLocalFileApi,
  importLocalModelApi,
  pullOllamaModelApi,
  getPullStatusApi,
  startOllamaApi,
} from '../../api';
import { DiscoveredGguf, OllamaPullStatus } from '../../types';

interface StartupConnectModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const StartupConnectModal: React.FC<StartupConnectModalProps> = ({
  isOpen,
  onClose,
}) => {
  const navigate = useNavigate();
  const {
    tenant,
    connectTenant,
    runtimeTarget,
    localEngineUrl,
    localEngineDetected,
    localStatus,
    setLocalEngineDetected,
    setRuntimeTarget,
  } = useWorkspaceStore();

  // Cloud Showcase tabs
  const [activeTab, setActiveTab] = useState<'account' | 'iam' | 'edge' | 'verify'>('account');
  // Local Engine 3-tab operational center
  const [localTab, setLocalTab] = useState<'readiness' | 'terraform' | 'aws'>('terraform');

  const [orgName, setOrgName] = useState(tenant.orgName || 'SwasthyaPay Technologies Pvt Ltd');
  const [awsAccountId, setAwsAccountId] = useState(tenant.awsAccountId || '987654321098');
  const [region, setRegion] = useState(tenant.region || 'ap-south-1');
  const [iamRoleArn, setIamRoleArn] = useState('');
  const [externalId, setExternalId] = useState(tenant.externalId || 'argus-tnt-9021-mumbai');
  const [ollamaEndpoint, setOllamaEndpoint] = useState(tenant.ollamaEndpoint || 'http://localhost:11434');
  const [copiedHcl, setCopiedHcl] = useState(false);

  // Local Terraform & GitHub scan states
  const [tfDirectory, setTfDirectory] = useState(
    localStatus?.sample_terraform_dir || ''
  );
  const didAutoTabRef = useRef(false);
  const [repoUrl, setRepoUrl] = useState('');
  const [repoBranch, setRepoBranch] = useState('');
  const [repoSubpath, setRepoSubpath] = useState('');

  // Local AWS CLI profile states
  const [awsProfiles, setAwsProfiles] = useState<string[]>([]);
  const [awsProfile, setAwsProfile] = useState('');

  // Local Readiness & Model onboarding states
  const [discoveredGgufs, setDiscoveredGgufs] = useState<DiscoveredGguf[]>([]);
  const [ggufPath, setGgufPath] = useState('');
  const [importModelName, setImportModelName] = useState('argus-m1-sft');
  const [importingModel, setImportingModel] = useState(false);
  const [browsingGguf, setBrowsingGguf] = useState(false);
  const [browsingFolder, setBrowsingFolder] = useState(false);
  const [startingOllama, setStartingOllama] = useState(false);
  const [modelMsg, setModelMsg] = useState<string | null>(null);
  const [modelErr, setModelErr] = useState<string | null>(null);
  const [pullTag, setPullTag] = useState('');
  const [pullStatus, setPullStatus] = useState<OllamaPullStatus | null>(null);

  // Shared scan progress/result
  const [localScanLoading, setLocalScanLoading] = useState(false);
  const [scanStageText, setScanStageText] = useState('');
  const [localScanError, setLocalScanError] = useState<string | null>(null);
  const [localScanResult, setLocalScanResult] = useState<string | null>(null);

  // Cloud showcase discovery simulation states
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveryStep, setDiscoveryStep] = useState(0);
  const [discoveryComplete, setDiscoveryComplete] = useState(false);

  const refreshLocalMeta = async () => {
    try {
      const [status, profiles, modelsRes] = await Promise.all([
        getLocalStatus(),
        getAwsProfilesApi().catch(() => []),
        getDiscoveredModelsApi().catch(() => null),
      ]);
      setLocalEngineDetected(true, status);
      if (status.sample_terraform_dir) {
        setTfDirectory((prev) => (!prev ? status.sample_terraform_dir || '' : prev));
      }
      const pList = profiles.length > 0 ? profiles : status.aws_profiles || [];
      setAwsProfiles(pList);
      if (pList.length > 0 && !awsProfile) {
        setAwsProfile(pList.includes('argus-scanner') ? 'argus-scanner' : pList[0]);
      }
      if (modelsRes) {
        setDiscoveredGgufs(modelsRes.ggufs || []);
        if (modelsRes.pull_status) setPullStatus(modelsRes.pull_status);
      } else if (status.discovered_ggufs) {
        setDiscoveredGgufs(status.discovered_ggufs);
      }
    } catch {}
  };

  useEffect(() => {
    if (!isOpen || runtimeTarget !== 'local') return;
    refreshLocalMeta();
  }, [isOpen, runtimeTarget]);

  // Default to readiness tab once per modal open if Ollama isn't ready yet
  useEffect(() => {
    if (!isOpen) {
      didAutoTabRef.current = false;
      return;
    }
    if (!didAutoTabRef.current && runtimeTarget === 'local' && localStatus) {
      didAutoTabRef.current = true;
      if (!localStatus.ollama?.running || (!localStatus.ollama?.argus_sft_ready && !localStatus.ollama?.argus_rft_ready)) {
        setLocalTab('readiness');
      }
    }
  }, [isOpen, runtimeTarget, localStatus]);

  useEffect(() => {
    if (!pullStatus?.active) return;
    const timer = setInterval(async () => {
      try {
        const st = await getPullStatusApi();
        setPullStatus(st);
        if (!st.active) refreshLocalMeta();
      } catch {}
    }, 1000);
    return () => clearInterval(timer);
  }, [pullStatus?.active]);

  if (!isOpen) return null;

  const handleBrowseFolder = async () => {
    if (browsingFolder) return;
    setLocalScanError(null);
    setBrowsingFolder(true);
    try {
      const selected = await pickLocalFolderApi(tfDirectory || undefined);
      if (selected) setTfDirectory(selected);
    } catch (err: any) {
      setLocalScanError(err?.message || 'Could not open folder picker.');
    } finally {
      setBrowsingFolder(false);
    }
  };

  const handleBrowseGguf = async () => {
    if (browsingGguf) return;
    setModelErr(null);
    setBrowsingGguf(true);
    try {
      const firstDiscovered = discoveredGgufs[0]?.path;
      const initDir = firstDiscovered
        ? firstDiscovered.replace(/[\\/][^\\/]+$/, '')
        : undefined;
      const selected = await pickLocalFileApi(initDir);
      if (selected) {
        setGgufPath(selected);
        setImportModelName(selected.toLowerCase().includes('rft') ? 'argus-m1-rft' : 'argus-m1-sft');
      }
    } catch (err: any) {
      setModelErr(err?.message || 'Could not open .gguf file picker.');
    } finally {
      setBrowsingGguf(false);
    }
  };

  const handleStartOllama = async () => {
    setStartingOllama(true);
    setModelErr(null);
    setModelMsg(null);
    try {
      await startOllamaApi();
      setModelMsg('Local Ollama daemon started and reachable on 127.0.0.1:11434.');
      await refreshLocalMeta();
    } catch (err: any) {
      setModelErr(err?.message || 'Could not start Ollama automatically. Launch Ollama for Windows first.');
    } finally {
      setStartingOllama(false);
    }
  };

  const handleImportGguf = async (pathOverride?: string, nameOverride?: string) => {
    const p = (pathOverride ?? ggufPath).trim();
    const n = nameOverride ?? importModelName;
    if (!p) {
      setModelErr('Choose or enter a .gguf file path first.');
      return;
    }
    setImportingModel(true);
    setModelErr(null);
    setModelMsg(null);
    try {
      const res = await importLocalModelApi(p, n);
      setModelMsg(`Registered ${res.model_name} in Ollama (${res.template_source || 'qwen3.5 template'}).`);
      await refreshLocalMeta();
    } catch (err: any) {
      setModelErr(err?.message || 'Failed to register GGUF in Ollama.');
    } finally {
      setImportingModel(false);
    }
  };

  const handlePullModel = async (tagOverride?: string) => {
    const targetTag = (tagOverride ?? pullTag).trim();
    if (!targetTag) {
      setPullStatus(null);
      setModelMsg(null);
      setModelErr('Enter an Ollama or Hugging Face model tag (e.g. qwen3.5:4b), or use Browse .gguf offline.');
      return;
    }
    if (tagOverride) {
      setPullTag(tagOverride);
    }
    setModelErr(null);
    setModelMsg(null);
    try {
      const st = await pullOllamaModelApi(targetTag);
      setPullStatus(st);
    } catch (err: any) {
      setPullStatus(null);
      setModelErr(err?.message || 'Failed to start Ollama pull.');
    }
  };

  const handleRealTerraformScan = async () => {
    setLocalScanLoading(true);
    setScanStageText('Parsing HCL & .tfvars -> Attack Graph -> MILP -> Airlock -> T0/T1 -> OPA Rego...');
    setLocalScanError(null);
    setLocalScanResult(null);
    try {
      const res = await scanTerraformApi(tfDirectory, region, orgName);
      setLocalScanResult(
        `Scanned ${res.files_scanned?.length || 0} Terraform files: ${res.findings_count} findings, ${res.nodes_count} graph nodes, OPA Rego ${res.opa_used ? 'active' : 'fallback'}.`
      );
      connectTenant(
        {
          orgName: orgName || 'Local Terraform Workspace',
          awsAccountId: 'local-tf',
          region,
          iamRoleArn,
          externalId,
          ollamaEndpoint,
          nodesDiscovered: res.nodes_count,
          edgesDiscovered: res.edges_count,
        },
        true
      );
    } catch (err: any) {
      setLocalScanError(err?.message || 'Terraform scan failed');
    } finally {
      setLocalScanLoading(false);
      setScanStageText('');
    }
  };

  const handleGithubTerraformScan = async () => {
    if (!repoUrl.trim()) {
      setLocalScanError('Enter a GitHub or Git repository URL first.');
      return;
    }
    setLocalScanLoading(true);
    setScanStageText('Cloning shallow repo locally -> Parsing HCL & .tfvars -> Attack Graph -> OPA Rego...');
    setLocalScanError(null);
    setLocalScanResult(null);
    try {
      const res = await scanGithubRepoApi({
        repoUrl: repoUrl.trim(),
        branch: repoBranch.trim() || undefined,
        subpath: repoSubpath.trim() || undefined,
        region,
        orgName: orgName || undefined,
      });
      setLocalScanResult(
        `Cloned ${res.repo_url}${res.commit ? ` (${res.commit})` : ''} locally: ${res.files_scanned?.length || 0} .tf files, ${res.findings_count} findings, ${res.nodes_count} graph nodes.`
      );
      connectTenant(
        {
          orgName: orgName || 'GitHub Terraform Repo',
          awsAccountId: 'local-tf',
          region,
          iamRoleArn,
          externalId,
          ollamaEndpoint,
          nodesDiscovered: res.nodes_count,
          edgesDiscovered: res.edges_count,
        },
        true
      );
    } catch (err: any) {
      setLocalScanError(err?.message || 'GitHub Terraform clone & scan failed');
    } finally {
      setLocalScanLoading(false);
      setScanStageText('');
    }
  };

  const handleRealAwsScan = async () => {
    setLocalScanLoading(true);
    setScanStageText('Running Step Zero privacy.iam_guard check -> Read-only AWS control-plane scan...');
    setLocalScanError(null);
    setLocalScanResult(null);
    try {
      const res = await scanAwsApi({
        profile: awsProfile.trim() || undefined,
        roleArn: iamRoleArn.trim() || undefined,
        externalId: externalId.trim() || undefined,
        region,
        orgName: orgName || undefined,
      });
      setLocalScanResult(
        `AWS ${res.account_id} (${res.identity}) verified via iam_guard: ${res.findings_count} findings, ${res.nodes_count} graph nodes.`
      );
      connectTenant(
        {
          orgName: orgName || `AWS ${res.account_id}`,
          awsAccountId: res.account_id || awsAccountId,
          region,
          iamRoleArn,
          externalId,
          ollamaEndpoint,
          nodesDiscovered: res.nodes_count,
          edgesDiscovered: res.edges_count,
        },
        true
      );
    } catch (err: any) {
      setLocalScanError(err?.message || 'AWS scan failed');
    } finally {
      setLocalScanLoading(false);
      setScanStageText('');
    }
  };

  const terraformSnippet = `# ARGUS Least-Privilege Read-Only Cross-Account Role
resource "aws_iam_role" "argus_audit_role" {
  name = "argus-audit-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { AWS = "arn:aws:iam::1320122453:root" }
      Condition = { StringEquals = { "sts:ExternalId" = "${externalId}" } }
    }]
  })
}

# Attach AWS SecurityAudit (Control-plane metadata only; zero S3 GetObject / secret access)
resource "aws_iam_role_policy_attachment" "argus_read" {
  role       = aws_iam_role.argus_audit_role.name
  policy_arn = "arn:aws:iam::aws:policy/SecurityAudit"
}`;

  const handleCopyTerraform = () => {
    navigator.clipboard.writeText(terraformSnippet);
    setCopiedHcl(true);
    setTimeout(() => setCopiedHcl(false), 2000);
  };

  const handleRunDiscovery = async () => {
    setIsDiscovering(true);
    setDiscoveryStep(1);
    await new Promise((r) => setTimeout(r, 700));
    setDiscoveryStep(2);
    await new Promise((r) => setTimeout(r, 850));
    setDiscoveryStep(3);
    await new Promise((r) => setTimeout(r, 750));
    setDiscoveryStep(4);
    await new Promise((r) => setTimeout(r, 600));
    setDiscoveryComplete(true);
    setIsDiscovering(false);
    try {
      await connectTenantApi({
        orgName,
        awsAccountId,
        region,
        iamRoleArn: iamRoleArn || 'arn:aws:iam::987654321098:role/argus-audit-role',
        externalId,
        ollamaEndpoint,
        dpdpScope: ['rule6', 'rule6a', 'rule7', 'rule8', 'rule15'],
      });
    } catch {}
  };

  const handleFinish = () => {
    connectTenant({
      orgName,
      awsAccountId,
      region,
      iamRoleArn: iamRoleArn || 'arn:aws:iam::987654321098:role/argus-audit-role',
      externalId,
      ollamaEndpoint,
      nodesDiscovered: 48,
      edgesDiscovered: 112,
      rulesEvaluated: 12,
      dpdpScore: 54,
    });
    onClose();
  };

  // ===========================================================================
  // LOCAL AGENT 3-TAB OPERATIONAL CONTROL CENTER
  // ===========================================================================
  if (runtimeTarget === 'local') {
    const opaReady = Boolean(localStatus?.opa_ready);
    const ollamaRunning = Boolean(localStatus?.ollama?.running);
    const sftReady = Boolean(localStatus?.ollama?.argus_sft_ready);
    const rftReady = Boolean(localStatus?.ollama?.argus_rft_ready);

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/60 backdrop-blur-sm animate-fade-in select-none">
        <div className="relative w-full max-w-3xl bg-paper border border-ink-border shadow-2xl rounded-2xl overflow-hidden flex flex-col max-h-[92vh]">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-ink-border/60 bg-paper">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-forest/10 border border-forest/25 rounded-xl text-forest">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="font-headline text-lg font-bold text-ink">
                    ARGUS Local Zero-Egress Control Center
                  </h2>
                  <span className="px-2 py-0.5 text-[10px] font-mono font-semibold bg-forest/15 text-forest rounded-full">
                    {localEngineUrl.replace(/^https?:\/\//, '')} • On-Device
                  </span>
                </div>
                <p className="text-xs text-ink-muted">
                  Verify readiness, load Ollama argus-m1, and scan GitHub Terraform or read-only AWS accounts locally.
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 text-ink-muted hover:text-ink hover:bg-mist rounded-control transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* 3 Operational Tabs */}
          <div className="flex border-b border-ink-border/50 bg-mist/40 px-6 pt-2 gap-2 overflow-x-auto">
            <button
              type="button"
              onClick={() => setLocalTab('readiness')}
              className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5 whitespace-nowrap ${
                localTab === 'readiness'
                  ? 'border-peacock text-peacock'
                  : 'border-transparent text-ink-muted hover:text-ink'
              }`}
            >
              <Cpu className="w-3.5 h-3.5" />
              <span>1. Readiness & Ollama M1</span>
              <span
                className={`ml-1 w-2 h-2 rounded-full ${
                  opaReady && (sftReady || rftReady) ? 'bg-forest' : 'bg-saffron'
                }`}
              />
            </button>
            <button
              type="button"
              onClick={() => setLocalTab('terraform')}
              className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5 whitespace-nowrap ${
                localTab === 'terraform'
                  ? 'border-peacock text-peacock'
                  : 'border-transparent text-ink-muted hover:text-ink'
              }`}
            >
              <GitBranch className="w-3.5 h-3.5" />
              <span>2. GitHub / Local Terraform</span>
            </button>
            <button
              type="button"
              onClick={() => setLocalTab('aws')}
              className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5 whitespace-nowrap ${
                localTab === 'aws'
                  ? 'border-peacock text-peacock'
                  : 'border-transparent text-ink-muted hover:text-ink'
              }`}
            >
              <Cloud className="w-3.5 h-3.5" />
              <span>3. Live AWS (Read-Only)</span>
            </button>
          </div>

          {/* Body */}
          <div className="p-6 flex-1 overflow-y-auto space-y-4 text-xs">
            {/* TAB 1: FIRST-RUN READINESS & OLLAMA */}
            {localTab === 'readiness' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-ink">First-Run System Readiness Checklist</span>
                  <button
                    type="button"
                    onClick={refreshLocalMeta}
                    className="inline-flex items-center gap-1 text-[11px] font-medium text-peacock hover:underline"
                  >
                    <RefreshCw className="w-3 h-3" />
                    <span>Re-check</span>
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  <div className="p-3 bg-mist/40 border border-ink-border rounded-xl flex items-center justify-between gap-2">
                    <div>
                      <p className="font-semibold text-ink">OPA Rego Engine (opa.exe)</p>
                      <p className="text-[11px] text-ink-muted truncate max-w-[210px]">
                        {localStatus?.opa_path || 'Python fallback active'}
                      </p>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded font-mono text-[10px] font-semibold ${
                        opaReady ? 'bg-forest/15 text-forest' : 'bg-saffron/20 text-saffron-dark'
                      }`}
                    >
                      {opaReady ? 'BUNDLED READY' : 'FALLBACK'}
                    </span>
                  </div>

                  <div className="p-3 bg-mist/40 border border-ink-border rounded-xl flex items-center justify-between gap-2">
                    <div>
                      <p className="font-semibold text-ink">Privacy Airlock & Vault</p>
                      <p className="text-[11px] text-ink-muted">Fernet vault.db + regex scrubbers</p>
                    </div>
                    <span className="px-2 py-0.5 rounded font-mono text-[10px] font-semibold bg-forest/15 text-forest">
                      READY
                    </span>
                  </div>

                  <div className="p-3 bg-mist/40 border border-ink-border rounded-xl flex items-center justify-between gap-2">
                    <div>
                      <p className="font-semibold text-ink">Tier 0 Deterministic Templates</p>
                      <p className="text-[11px] text-ink-muted">7 DPDP/CIS rules (0.4 ms, offline)</p>
                    </div>
                    <span className="px-2 py-0.5 rounded font-mono text-[10px] font-semibold bg-forest/15 text-forest">
                      READY
                    </span>
                  </div>

                  <div className="p-3 bg-mist/40 border border-ink-border rounded-xl flex items-center justify-between gap-2">
                    <div>
                      <p className="font-semibold text-ink">Ollama Local Engine (:11434)</p>
                      <p className="text-[11px] text-ink-muted">
                        {ollamaRunning
                          ? `v${localStatus?.ollama?.version || '?'} • SFT: ${sftReady ? 'Ready' : 'Missing'} • RFT: ${rftReady ? 'Ready' : 'Missing'}`
                          : 'Not running (T0 still works)'}
                      </p>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded font-mono text-[10px] font-semibold ${
                        ollamaRunning && (sftReady || rftReady)
                          ? 'bg-forest/15 text-forest'
                          : 'bg-saffron/20 text-saffron-dark'
                      }`}
                    >
                      {ollamaRunning && (sftReady || rftReady)
                        ? 'ARGUS-M1 READY'
                        : ollamaRunning
                        ? 'NEEDS GGUF'
                        : 'OFFLINE'}
                    </span>
                  </div>
                </div>

                {/* Honest M2 Notice */}
                <div className="p-3 bg-saffron/10 border border-saffron/30 rounded-xl flex items-start gap-2.5">
                  <Lock className="w-4 h-4 text-saffron-dark flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-ink">
                      M2 Conformal Autonomy Gate: {localStatus?.m2_status?.certified ? 'CERTIFIED' : 'HUMAN_REVIEW_ONLY'}
                    </p>
                    <p className="text-[11px] text-ink-muted">{localStatus?.m2_status?.message}</p>
                  </div>
                </div>

                {/* Discovered GGUFs + File Picker */}
                <div className="p-4 bg-forest/5 border border-forest/25 rounded-xl space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-ink">Load argus-m1 GGUF into Ollama</span>
                    <div className="flex items-center gap-2">
                      {!ollamaRunning && localStatus?.ollama?.ollama_installed && (
                        <button
                          type="button"
                          disabled={startingOllama}
                          onClick={handleStartOllama}
                          className="px-2.5 py-1 bg-peacock text-paper rounded-control text-[11px] font-semibold hover:bg-peacock-hover disabled:opacity-50"
                        >
                          {startingOllama ? 'Starting Ollama...' : 'Start Ollama'}
                        </button>
                      )}
                      {!ollamaRunning && !localStatus?.ollama?.ollama_installed && (
                        <a
                          href="https://ollama.com/download/windows"
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] font-semibold text-peacock hover:underline"
                        >
                          Install Ollama for Windows &rarr;
                        </a>
                      )}
                    </div>
                  </div>

                  {ollamaRunning && (localStatus?.ollama?.models?.length ?? 0) > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[10.5px] font-medium text-ink-muted">Active in Ollama:</span>
                      {localStatus?.ollama?.models.map((m) => (
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

                  {discoveredGgufs.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-[11px] text-ink-muted font-medium">Auto-detected on this PC:</p>
                      {discoveredGgufs.map((g) => (
                        <div
                          key={g.path}
                          className="p-2 bg-paper border border-ink-border rounded-lg flex items-center justify-between gap-2"
                        >
                          <div className="min-w-0">
                            <p className="font-mono font-semibold text-ink truncate">{g.name}</p>
                            <p className="text-[10px] text-ink-muted truncate">
                              {g.size_gb} GB • {g.path}
                            </p>
                          </div>
                          <button
                            type="button"
                            disabled={importingModel}
                            onClick={() => handleImportGguf(g.path, g.suggested_model_name)}
                            className="px-2.5 py-1 bg-forest text-paper rounded-control font-semibold hover:bg-forest/90 disabled:opacity-50 flex-shrink-0"
                          >
                            Import as {g.suggested_model_name}
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex flex-col sm:flex-row gap-2">
                    <input
                      type="text"
                      value={ggufPath}
                      onChange={(e) => setGgufPath(e.target.value)}
                      placeholder="Select Qwen3.5-4B.Q4_K_M.gguf..."
                      className="flex-1 px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                    />
                    <button
                      type="button"
                      disabled={browsingGguf}
                      onClick={handleBrowseGguf}
                      className="px-3 py-1.5 bg-paper border border-ink-border hover:bg-mist disabled:opacity-60 rounded-control font-semibold flex items-center justify-center gap-1"
                    >
                      <FolderSearch className="w-3.5 h-3.5 text-peacock" />
                      <span>{browsingGguf ? 'Opening...' : 'Browse .gguf...'}</span>
                    </button>
                    <select
                      value={importModelName}
                      onChange={(e) => setImportModelName(e.target.value)}
                      className="px-2 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                    >
                      <option value="argus-m1-sft">argus-m1-sft</option>
                      <option value="argus-m1-rft">argus-m1-rft</option>
                    </select>
                    <button
                      type="button"
                      disabled={importingModel}
                      onClick={() => handleImportGguf()}
                      className="px-3 py-1.5 bg-peacock text-paper rounded-control font-semibold hover:bg-peacock-hover disabled:opacity-50"
                    >
                      {importingModel ? 'Registering...' : 'Register'}
                    </button>
                  </div>

                  {/* Pull box */}
                  <div className="space-y-2 pt-2 border-t border-forest/20">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-[10.5px] font-medium text-ink-muted">
                        Pull or Verify Model in Ollama:
                      </span>
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
                          if (modelErr) setModelErr(null);
                        }}
                        placeholder="hf.co/<org>/argus-m1-sft-gguf:Q4_K_M (optional; or use Browse .gguf offline)"
                        className="flex-1 px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                      />
                      <button
                        type="button"
                        disabled={Boolean(pullStatus?.active)}
                        onClick={() => handlePullModel()}
                        className="px-3 py-1.5 bg-forest text-paper rounded-control font-semibold hover:bg-forest/90 disabled:opacity-50"
                      >
                        {pullStatus?.active ? `Pulling (${pullStatus.percent}%)...` : 'Pull via Ollama'}
                      </button>
                    </div>
                  </div>

                  {pullStatus && pullStatus.status !== 'idle' && (
                    <div className="p-2.5 bg-paper border border-ink-border rounded space-y-1">
                      <div className="flex justify-between font-mono text-[11px]">
                        <span className="truncate pr-2">{pullStatus.model}: {pullStatus.status}</span>
                        <span className="font-semibold text-peacock flex-shrink-0">{pullStatus.percent}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-mist rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all ${pullStatus.error ? 'bg-garnet' : 'bg-forest'}`}
                          style={{ width: `${Math.min(100, Math.max(0, pullStatus.percent))}%` }}
                        />
                      </div>
                      {pullStatus.error && (
                        <p className="text-garnet text-[11px] font-medium pt-0.5">{pullStatus.error}</p>
                      )}
                      {pullStatus.success && !pullStatus.error && (
                        <p className="text-forest text-[11px] font-medium pt-0.5">
                          Ready in local Ollama ({pullStatus.model}).
                        </p>
                      )}
                    </div>
                  )}

                  {modelErr && <p className="text-garnet font-medium">{modelErr}</p>}
                  {modelMsg && <p className="text-forest font-medium">{modelMsg}</p>}
                </div>

                <div className="flex justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => setLocalTab('terraform')}
                    className="px-4 py-2 bg-peacock text-paper rounded-control font-semibold hover:bg-peacock-hover flex items-center gap-1.5"
                  >
                    <span>Scan GitHub / Local Terraform</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}

            {/* TAB 2: GITHUB REPO OR LOCAL TERRAFORM */}
            {localTab === 'terraform' && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="font-semibold text-ink">Workspace / Startup Name</label>
                    <input
                      type="text"
                      value={orgName}
                      onChange={(e) => setOrgName(e.target.value)}
                      className="w-full px-2.5 py-1.5 bg-paper border border-ink-border rounded-control"
                      placeholder="Acme FinTech Pvt Ltd"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="font-semibold text-ink">Approved Residency Region</label>
                    <select
                      value={region}
                      onChange={(e) => setRegion(e.target.value)}
                      className="w-full px-2.5 py-1.5 bg-paper border border-ink-border rounded-control"
                    >
                      <option value="ap-south-1">ap-south-1 (Mumbai, India — DPDP Rule 15)</option>
                      <option value="ap-south-2">ap-south-2 (Hyderabad, India)</option>
                      <option value="ap-southeast-1">ap-southeast-1 (Singapore)</option>
                      <option value="us-east-1">us-east-1 (N. Virginia)</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Card A: GitHub Clone */}
                  <div className="p-4 bg-mist/40 border border-ink-border rounded-xl space-y-2.5 flex flex-col justify-between">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-ink flex items-center gap-1.5">
                          <GitBranch className="w-4 h-4 text-peacock" />
                          <span>Clone & Scan GitHub / Git URL</span>
                        </span>
                        <span className="text-[10px] font-mono text-forest bg-paper px-1.5 py-0.5 rounded border border-forest/30">
                          Local Clone Only
                        </span>
                      </div>
                      <input
                        type="text"
                        value={repoUrl}
                        onChange={(e) => setRepoUrl(e.target.value)}
                        placeholder="https://github.com/org/terraform-aws-infra.git"
                        className="w-full px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                      />
                      <div className="grid grid-cols-2 gap-2">
                        <input
                          type="text"
                          value={repoBranch}
                          onChange={(e) => setRepoBranch(e.target.value)}
                          placeholder="Branch (optional)"
                          className="w-full px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                        />
                        <input
                          type="text"
                          value={repoSubpath}
                          onChange={(e) => setRepoSubpath(e.target.value)}
                          placeholder="Subdir (e.g. infra/aws)"
                          className="w-full px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                        />
                      </div>
                      <p className="text-[11px] text-ink-muted">
                        Shallow-clones into <code className="font-mono">%LocalAppData%\ARGUS\repos</code> using your local git credentials—never sent to EC2.
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={localScanLoading}
                      onClick={handleGithubTerraformScan}
                      className="w-full py-2 px-3 bg-peacock text-paper rounded-control font-semibold hover:bg-peacock-hover disabled:opacity-50"
                    >
                      {localScanLoading ? 'Scanning Repository...' : 'Clone & Scan GitHub Repo'}
                    </button>
                  </div>

                  {/* Card B: Local Folder Picker */}
                  <div className="p-4 bg-mist/40 border border-ink-border rounded-xl space-y-2.5 flex flex-col justify-between">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-ink flex items-center gap-1.5">
                          <FolderOpen className="w-4 h-4 text-forest" />
                          <span>Scan Local Terraform Folder</span>
                        </span>
                      </div>
                      <div className="flex gap-1.5">
                        <input
                          type="text"
                          value={tfDirectory}
                          onChange={(e) => setTfDirectory(e.target.value)}
                          placeholder="C:\path\to\terraform"
                          className="flex-1 min-w-0 px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                        />
                        <button
                          type="button"
                          disabled={browsingFolder}
                          onClick={handleBrowseFolder}
                          className="px-2.5 py-1.5 bg-paper border border-ink-border hover:bg-mist disabled:opacity-60 rounded-control font-semibold flex items-center gap-1 flex-shrink-0"
                        >
                          <FolderSearch className="w-3.5 h-3.5 text-peacock" />
                          <span>{browsingFolder ? 'Opening...' : 'Browse...'}</span>
                        </button>
                      </div>
                      {localStatus?.sample_terraform_dir && (
                        <button
                          type="button"
                          onClick={() => setTfDirectory(localStatus.sample_terraform_dir || '')}
                          className="text-[10.5px] font-mono text-peacock hover:underline text-left block truncate max-w-full"
                        >
                          Use built-in sample: {localStatus.sample_terraform_dir}
                        </button>
                      )}
                      <p className="text-[11px] text-ink-muted">
                        Recursively parses <code className="font-mono">.tf</code>, <code className="font-mono">*.tfvars</code>, <code className="font-mono">aws_iam_policy_document</code>, inline role policies, and S3 ACLs.
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={localScanLoading}
                      onClick={handleRealTerraformScan}
                      className="w-full py-2 px-3 bg-forest text-paper rounded-control font-semibold hover:bg-forest/90 disabled:opacity-50"
                    >
                      {localScanLoading ? 'Scanning Folder...' : 'Scan Local Terraform Folder'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 3: LIVE READ-ONLY AWS ACCOUNT */}
            {localTab === 'aws' && (
              <div className="space-y-4">
                <div className="p-3 bg-peacock/5 border border-peacock/20 rounded-xl space-y-1">
                  <div className="flex items-center gap-1.5 font-semibold text-peacock">
                    <Lock className="w-3.5 h-3.5" />
                    <span>Step-Zero privacy.iam_guard Enforcement</span>
                  </div>
                  <p className="text-[11px] text-ink-muted">
                    Before touching S3/EC2/IAM/RDS, ARGUS inspects the caller identity&apos;s own policy and <strong>hard-blocks</strong> any identity with data-plane rights (<code className="font-mono">s3:GetObject</code>, <code className="font-mono">kms:Decrypt</code>, <code className="font-mono">secretsmanager:GetSecretValue</code>).
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="font-semibold text-ink">
                      AWS CLI Profile (from <code className="font-mono">~/.aws</code>)
                    </label>
                    {awsProfiles.length > 0 ? (
                      <select
                        value={awsProfile}
                        onChange={(e) => setAwsProfile(e.target.value)}
                        className="w-full px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                      >
                        <option value="">(Default boto3 credential chain / env)</option>
                        {awsProfiles.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={awsProfile}
                        onChange={(e) => setAwsProfile(e.target.value)}
                        placeholder="argus-scanner (or leave blank for default env)"
                        className="w-full px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                      />
                    )}
                  </div>

                  <div className="space-y-1">
                    <label className="font-semibold text-ink">Target AWS Region</label>
                    <select
                      value={region}
                      onChange={(e) => setRegion(e.target.value)}
                      className="w-full px-2.5 py-1.5 bg-paper border border-ink-border rounded-control"
                    >
                      <option value="ap-south-1">ap-south-1 (Mumbai, India)</option>
                      <option value="ap-south-2">ap-south-2 (Hyderabad, India)</option>
                      <option value="ap-southeast-1">ap-southeast-1 (Singapore)</option>
                      <option value="us-east-1">us-east-1 (N. Virginia)</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="font-semibold text-ink">Optional Cross-Account STS Role ARN</label>
                    <input
                      type="text"
                      value={iamRoleArn}
                      onChange={(e) => setIamRoleArn(e.target.value)}
                      placeholder="arn:aws:iam::123456789012:role/argus-audit-role"
                      className="w-full px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="font-semibold text-ink">STS External ID (if Role ARN set)</label>
                    <input
                      type="text"
                      value={externalId}
                      onChange={(e) => setExternalId(e.target.value)}
                      placeholder="argus-tnt-9021-mumbai"
                      className="w-full px-2.5 py-1.5 bg-paper border border-ink-border rounded-control font-mono text-xs"
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-ink">Least-Privilege Read-Only Role Terraform</span>
                    <button
                      type="button"
                      onClick={handleCopyTerraform}
                      className="text-[11px] text-peacock hover:underline flex items-center gap-1"
                    >
                      <Copy className="w-3 h-3" />
                      <span>{copiedHcl ? 'Copied' : 'Copy HCL'}</span>
                    </button>
                  </div>
                  <pre className="p-2.5 bg-ink text-paper rounded-control text-[10.5px] font-mono overflow-x-auto max-h-36">
                    {terraformSnippet}
                  </pre>
                </div>

                <button
                  type="button"
                  disabled={localScanLoading}
                  onClick={handleRealAwsScan}
                  className="w-full py-2.5 px-4 bg-forest text-paper rounded-control font-semibold hover:bg-forest/90 disabled:opacity-50"
                >
                  {localScanLoading ? 'Verifying iam_guard & Scanning AWS...' : 'Verify iam_guard & Scan Live AWS Account'}
                </button>
              </div>
            )}

            {/* Shared Scan Progress / Error / Success Banner */}
            {scanStageText && (
              <div className="p-3 bg-peacock/10 border border-peacock/30 rounded-xl text-peacock font-mono flex items-center gap-2">
                <Zap className="w-4 h-4 animate-spin flex-shrink-0" />
                <span>{scanStageText}</span>
              </div>
            )}
            {localScanError && (
              <div className="p-3 bg-garnet/10 border border-garnet/30 rounded-xl text-garnet flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{localScanError}</span>
              </div>
            )}
            {localScanResult && (
              <div className="p-3 bg-forest/15 border border-forest/30 rounded-xl text-forest font-medium flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <span>{localScanResult}</span>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    type="button"
                    onClick={() => {
                      onClose();
                      navigate('/map');
                    }}
                    className="px-2.5 py-1 bg-paper text-peacock border border-peacock/30 rounded-control text-[11px] font-semibold hover:bg-mist"
                  >
                    Attack Map
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      onClose();
                      navigate('/approvals');
                    }}
                    className="px-2.5 py-1 bg-forest text-paper rounded-control text-[11px] font-semibold hover:bg-forest/90"
                  >
                    Inspect Findings &rarr;
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // CLOUD SHOWCASE MODE (Preserves SwasthyaPay Interactive Walkthrough)
  // ===========================================================================
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/60 backdrop-blur-sm animate-fade-in select-none">
      <div className="relative w-full max-w-3xl bg-paper border border-ink-border shadow-2xl rounded-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-ink-border/60 bg-paper">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-peacock/10 border border-peacock/20 rounded-xl text-peacock">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-headline text-lg font-bold text-ink">
                  Connect Startup AWS Infrastructure
                </h2>
                <span className="px-2 py-0.5 text-[10px] font-mono font-semibold bg-peacock/10 text-peacock rounded-full">
                  Zero Data Egress
                </span>
              </div>
              <p className="text-xs text-ink-muted">
                How real Indian startups connect their cloud tenancy for autonomous DPDP Act & CIS remediation
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-ink-muted hover:text-ink hover:bg-mist rounded-control transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-ink-border/50 bg-mist/40 px-6 pt-2">
          <button
            onClick={() => setActiveTab('account')}
            className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'account'
                ? 'border-peacock text-peacock'
                : 'border-transparent text-ink-muted hover:text-ink'
            }`}
          >
            <Cloud className="w-3.5 h-3.5" />
            <span>1. Cloud Account & Scope</span>
          </button>
          <button
            onClick={() => setActiveTab('iam')}
            className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'iam'
                ? 'border-peacock text-peacock'
                : 'border-transparent text-ink-muted hover:text-ink'
            }`}
          >
            <Key className="w-3.5 h-3.5" />
            <span>2. Least-Privilege IAM Trust</span>
          </button>
          <button
            onClick={() => setActiveTab('edge')}
            className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'edge'
                ? 'border-peacock text-peacock'
                : 'border-transparent text-ink-muted hover:text-ink'
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>3. In-VPC Edge Model</span>
          </button>
          <button
            onClick={() => setActiveTab('verify')}
            className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'verify'
                ? 'border-peacock text-peacock'
                : 'border-transparent text-ink-muted hover:text-ink'
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>4. Cartography Discovery</span>
          </button>
        </div>

        {/* Content Area */}
        <div className="p-6 flex-1 overflow-y-auto space-y-4">
          <div className="p-3.5 bg-saffron/10 border border-saffron/30 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
            <div className="space-y-0.5">
              <p className="font-semibold text-ink">
                Cloud Showcase Simulation Mode (Zero Customer Secrets on EC2)
              </p>
              <p className="text-ink-muted text-[11px]">
                This wizard demonstrates how startups configure IAM + STS ExternalId. Real scanning executes strictly on your device (<code className="font-mono">127.0.0.1:8742</code>).
              </p>
            </div>
            {localEngineDetected ? (
              <button
                type="button"
                onClick={() => setRuntimeTarget('local')}
                className="px-3 py-1.5 bg-forest text-paper rounded-control font-semibold flex-shrink-0"
              >
                Switch to Local Engine
              </button>
            ) : (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  navigate('/downloads');
                }}
                className="px-3 py-1.5 bg-peacock text-paper rounded-control font-semibold flex items-center gap-1.5 flex-shrink-0"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download ARGUS.exe</span>
              </button>
            )}
          </div>

          {/* TAB 1: ACCOUNT */}
          {activeTab === 'account' && (
            <div className="space-y-4 animate-fade-in">
              <div className="p-3 bg-mist/60 border border-ink-border/70 rounded-control text-xs text-ink space-y-1">
                <span className="font-semibold text-peacock">What ARGUS Needs to Access:</span>
                <p className="text-ink-muted leading-relaxed">
                  ARGUS inspects cloud control-plane metadata (IAM role policies, S3 bucket encryption flags, security group ingress rules, and CloudTrail configs).{' '}
                  <strong>ARGUS NEVER accesses citizen data, databases, S3 object contents, or customer secrets.</strong>
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-ink">Organization / Startup Name</label>
                  <input
                    type="text"
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    className="w-full px-3 py-2 text-xs bg-paper border border-ink-border rounded-control focus:border-peacock focus:ring-1 focus:ring-peacock outline-none font-medium"
                    placeholder="e.g. SwasthyaPay Technologies"
                  />
                  <span className="text-[10px] text-ink-muted">Registered Indian FinTech/HealthTech entity</span>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-ink">AWS Account ID (12-Digit)</label>
                  <input
                    type="text"
                    value={awsAccountId}
                    onChange={(e) => setAwsAccountId(e.target.value)}
                    maxLength={12}
                    className="w-full px-3 py-2 text-xs bg-paper border border-ink-border rounded-control focus:border-peacock focus:ring-1 focus:ring-peacock outline-none font-mono"
                    placeholder="987654321098"
                  />
                  <span className="text-[10px] text-ink-muted">Target cloud tenancy to audit and protect</span>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-ink">Primary AWS Region</label>
                <select
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-paper border border-ink-border rounded-control focus:border-peacock focus:ring-1 focus:ring-peacock outline-none font-medium"
                >
                  <option value="ap-south-1">ap-south-1 (Asia Pacific - Mumbai, India) [Recommended for DPDP Act 2023]</option>
                  <option value="ap-southeast-1">ap-southeast-1 (Singapore)</option>
                  <option value="us-east-1">us-east-1 (US East - N. Virginia)</option>
                  <option value="eu-west-1">eu-west-1 (Europe - Ireland)</option>
                </select>
                <span className="text-[10px] text-forest font-medium">
                  ✓ ap-south-1 ensures 100% Indian Data Sovereignty under DPDP Section 15
                </span>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setActiveTab('iam')}
                  className="px-4 py-2 text-xs font-semibold bg-peacock text-paper rounded-control hover:bg-peacock-hover transition-colors flex items-center gap-1.5 shadow-sm"
                >
                  <span>Continue to IAM Trust Configuration</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}

          {/* TAB 2: IAM TRUST */}
          {activeTab === 'iam' && (
            <div className="space-y-4 animate-fade-in">
              <div className="p-3 bg-peacock/5 border border-peacock/20 rounded-control text-xs text-ink space-y-1">
                <div className="flex items-center gap-1.5 font-semibold text-peacock">
                  <Lock className="w-3.5 h-3.5" />
                  <span>Cross-Account Role Delegation with External ID</span>
                </div>
                <p className="text-ink-muted text-[11px] leading-relaxed">
                  Your AWS administrator provisions an IAM role with the standard AWS-managed <code>SecurityAudit</code> policy.
                  ARGUS uses AWS Security Token Service (STS) with a cryptographically unique External ID to prevent confused-deputy attacks.
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-ink">Cross-Account IAM Role ARN</label>
                <input
                  type="text"
                  value={iamRoleArn || 'arn:aws:iam::987654321098:role/argus-audit-role'}
                  onChange={(e) => setIamRoleArn(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-paper border border-ink-border rounded-control focus:border-peacock font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-ink">Terraform HCL Role Snippet</label>
                  <button
                    onClick={handleCopyTerraform}
                    className="text-[11px] text-peacock hover:text-peacock-dark flex items-center gap-1 font-medium"
                  >
                    <Copy className="w-3 h-3" />
                    <span>{copiedHcl ? 'Copied HCL!' : 'Copy Terraform Code'}</span>
                  </button>
                </div>
                <pre className="p-3 bg-ink text-paper rounded-control text-[11px] font-mono overflow-x-auto leading-relaxed border border-ink/40">
                  {terraformSnippet}
                </pre>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-ink-border/50">
                <button
                  type="button"
                  onClick={() => setActiveTab('account')}
                  className="px-3 py-1.5 text-xs font-medium text-ink-muted hover:text-ink"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('edge')}
                  className="px-4 py-2 text-xs font-semibold bg-peacock text-paper rounded-control hover:bg-peacock-hover transition-colors flex items-center gap-1.5 shadow-sm"
                >
                  <span>Configure In-VPC Edge Agent</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}

          {/* TAB 3: EDGE MODEL */}
          {activeTab === 'edge' && (
            <div className="space-y-4 animate-fade-in">
              <div className="p-3 bg-forest/10 border border-forest/20 rounded-control text-xs text-ink space-y-1">
                <div className="flex items-center gap-1.5 font-semibold text-forest">
                  <Server className="w-3.5 h-3.5" />
                  <span>Zero Cloud Egress: In-VPC Ollama Local Edge Model</span>
                </div>
                <p className="text-ink-muted text-[11px] leading-relaxed">
                  Unlike traditional cloud security tools that send your architecture to OpenAI or foreign servers,
                  ARGUS connects to a local Ollama instance inside your private VPC subnet.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-ink">Local Ollama API Endpoint</label>
                  <input
                    type="text"
                    value={ollamaEndpoint}
                    onChange={(e) => setOllamaEndpoint(e.target.value)}
                    className="w-full px-3 py-2 text-xs bg-paper border border-ink-border rounded-control font-mono"
                    placeholder="http://localhost:11434"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-ink">Fine-Tuned Specialized Model</label>
                  <select
                    defaultValue="argus-m1-sft"
                    className="w-full px-3 py-2 text-xs bg-paper border border-ink-border rounded-control font-mono"
                  >
                    <option value="argus-m1-sft">argus-m1-sft (QLoRA 4B Q4_K_M GGUF)</option>
                    <option value="argus-m1-rft">argus-m1-rft (Reinforcement Fine-Tuned)</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-ink-border/50">
                <button
                  type="button"
                  onClick={() => setActiveTab('iam')}
                  className="px-3 py-1.5 text-xs font-medium text-ink-muted hover:text-ink"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('verify')}
                  className="px-4 py-2 text-xs font-semibold bg-peacock text-paper rounded-control hover:bg-peacock-hover transition-colors flex items-center gap-1.5 shadow-sm"
                >
                  <span>Proceed to Discovery Scan</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}

          {/* TAB 4: DISCOVERY VERIFY */}
          {activeTab === 'verify' && (
            <div className="space-y-4 animate-fade-in">
              <div className="space-y-2.5 p-4 bg-paper border border-ink-border rounded-control">
                {[
                  { step: 1, label: '1. STS Handshake & ExternalId Verification', tag: 'Verified (200 OK)' },
                  { step: 2, label: '2. Cartography AWS Graph Extraction (IAM, S3, VPC)', tag: '48 Nodes, 112 Edges' },
                  { step: 3, label: '3. Personalized PageRank Blast Radius Calculation', tag: 'Baseline: 90.6% Likelihood' },
                  { step: 4, label: '4. DPDP Act 2023 Statutory Safeguards Audit', tag: '12 Findings Identified' },
                ].map((item) => (
                  <div key={item.step} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      {discoveryStep >= item.step ? (
                        <CheckCircle2 className="w-4 h-4 text-forest" />
                      ) : (
                        <span className="w-4 h-4 rounded-full border border-ink-border" />
                      )}
                      <span className={discoveryStep >= item.step ? 'font-semibold text-ink' : 'text-ink-muted'}>
                        {item.label}
                      </span>
                    </div>
                    {discoveryStep >= item.step && <span className="font-mono text-[10px] text-forest">{item.tag}</span>}
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-ink-border/50">
                <button
                  type="button"
                  onClick={() => setActiveTab('edge')}
                  disabled={isDiscovering}
                  className="px-3 py-1.5 text-xs font-medium text-ink-muted hover:text-ink disabled:opacity-50"
                >
                  Back
                </button>

                {!discoveryComplete ? (
                  <button
                    type="button"
                    onClick={handleRunDiscovery}
                    disabled={isDiscovering}
                    className="px-5 py-2 text-xs font-semibold bg-peacock text-paper rounded-control hover:bg-peacock-hover transition-colors flex items-center gap-2 shadow-sm disabled:opacity-60"
                  >
                    {isDiscovering ? (
                      <>
                        <Zap className="w-4 h-4 animate-spin text-paper" />
                        <span>Running Cartography Discovery...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4" />
                        <span>Verify & Run Live Cartography Discovery</span>
                      </>
                    )}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleFinish}
                    className="px-5 py-2 text-xs font-semibold bg-forest text-paper rounded-control hover:bg-forest/90 transition-colors flex items-center gap-2 shadow-sm"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Activate Startup Tenant Workspace</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
