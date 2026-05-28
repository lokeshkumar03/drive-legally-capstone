import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  UploadCloud, FileText, Search, ShieldCheck, AlertTriangle, Download, Scale, Activity,
  Gavel, ShieldAlert, Car, Sparkles, Route, BadgeCheck, ScanLine, Radar, FileSearch,
  CheckCircle2, XCircle, Clock3, MapPin, Fingerprint, Terminal, BookOpen, ClipboardCheck,
  Gauge, Bot, LockKeyhole, ChevronRight, CircleDot, Zap, HelpCircle
} from 'lucide-react';
import { verifyChallan, askLegalQuestion, reportUrl } from './services/api';
import './styles.css';

const STATES = [
  { value: 'AP', label: 'Andhra Pradesh' },
  { value: 'TS', label: 'Telangana' },
  { value: 'KA', label: 'Karnataka' },
  { value: 'GJ', label: 'Gujarat' },
];

const USER_TYPES = [
  'Vehicle Owner',
  'Legal Professional',
  'Traffic Officer',
  'Transport Department User',
  'Research / Academic User'
];

const TABS = ['report', 'ocr', 'validation', 'legal', 'safety', 'logs'];

function cx(...parts) { return parts.filter(Boolean).join(' '); }
function isPass(result) { return /valid|provided|pass/i.test(result?.final_status || '') || result?.judge_result?.verdict === 'PASS'; }
function needsReview(result) { return /review|caution/i.test(result?.final_status || '') || result?.judge_result?.verdict === 'CAUTION'; }
function hasDiscrepancy(result) { return /mismatch|invalid|fail|discrepancy/i.test(`${result?.final_status || ''} ${result?.vehicle_match_status || ''} ${result?.judge_result?.verdict || ''}`); }

function normalizeLogType(log = '') {
  if (/fail|error|mismatch|could not|not extracted/i.test(log)) return 'error';
  if (/warning|review|human|guardrail|judge/i.test(log)) return 'warn';
  if (/completed|matched|success|pass|retrieved|generated/i.test(log)) return 'success';
  if (/rag|legal|source|context/i.test(log)) return 'rag';
  return 'info';
}

function LogoMark() {
  return (
    <div className="brand-logo" aria-label="Drive Legally logo">
      <ShieldCheck size={22} className="brand-logo-shield" />
      <Route size={20} className="brand-logo-road" />
      <span className="brand-logo-dot" />
    </div>
  );
}

function Header() {
  return (
    <header className="app-header">
      <div className="brand-wrap">
        <LogoMark />
        <div>
          <div className="brand-title-row">
            <h1>Drive Legally</h1>
            <span className="ai-badge"><Sparkles size={13} /> AI Powered</span>
          </div>
          <p>AI Assistant for Traffic Challan Verification and Legal Guidance</p>
        </div>
      </div>
      <div className="header-actions">
        <span className="trust-chip"><LockKeyhole size={15} /> Guardrails enabled</span>
        <span className="trust-chip amber"><Scale size={15} /> Legal RAG</span>
      </div>
    </header>
  );
}

function HeroBanner() {
  return (
    <section className="hero-banner">
      <div className="hero-copy">
        <span className="eyebrow"><Radar size={15} /> AI Legal Verification Cockpit</span>
        <h2>Verify challans with evidence, state-wise legal context, and responsible AI evaluation.</h2>
        <p>
          Upload your challan and vehicle evidence. Drive Legally identifies the latest offence,
          validates the vehicle, retrieves applicable legal rules, applies guardrails, and generates a structured report.
        </p>
      </div>
      <div className="hero-stats">
        <div><strong>9</strong><span>Agentic Components</span></div>
        <div><strong>3</strong><span>State Rule Sets</span></div>
        <div><strong>PDF</strong><span>Report Output</span></div>
      </div>
    </section>
  );
}

function Field({ label, children, wide }) {
  return <label className={cx('field', wide && 'wide')}><span>{label}</span>{children}</label>;
}

function UploadZone({ label, helper, file, setFile, accept, icon }) {
  return (
    <label className={cx('upload-zone', file && 'has-file')}>
      <input type="file" accept={accept} onChange={(e) => setFile(e.target.files?.[0] || null)} />
      <div className="upload-icon">{icon || <UploadCloud size={24} />}</div>
      <div>
        <b>{file ? file.name : label}</b>
        <p>{file ? 'File ready for AI verification' : helper}</p>
      </div>
      <span className="upload-action">Browse</span>
    </label>
  );
}

function ScannerBadge({ children, tone = 'neutral', icon }) {
  return <span className={cx('scanner-badge', tone)}>{icon}{children}</span>;
}

function LiveAIScanner({ result, loading, mode }) {
  const state = useMemo(() => {
    if (loading) return { title: 'Scanning Context...', tone: 'scan', icon: <ScanLine size={18} /> };
    if (!result) return { title: 'Ready for Verification', tone: 'idle', icon: <CircleDot size={18} /> };
    if (hasDiscrepancy(result)) return { title: 'Discrepancy Flags Detected', tone: 'danger', icon: <XCircle size={18} /> };
    if (needsReview(result)) return { title: 'Needs Human Review', tone: 'review', icon: <AlertTriangle size={18} /> };
    return { title: 'Vehicle Verified', tone: 'verified', icon: <CheckCircle2 size={18} /> };
  }, [result, loading]);

  const judgeScore = result?.judge_result?.total_score ?? 0;
  const confidence = result?.confidence_score ?? 0;

  return (
    <aside className={cx('scanner-card', state.tone)}>
      <div className="scanner-top">
        <span>Live AI Verification Scanner</span>
        <ScannerBadge tone={state.tone} icon={state.icon}>{state.title}</ScannerBadge>
      </div>
      <div className="scanner-visual">
        <div className="radar-grid" />
        <div className="legal-shield">
          <ShieldCheck size={178} />
          <div className="car-outline">
            <Car size={94} />
          </div>
          <div className={cx('scan-line', loading && 'running')} />
          <div className="bounding-box"><span /><span /><span /><span /></div>
        </div>
      </div>
      <div className="scanner-badges">
        <ScannerBadge tone={result?.vehicle_match_status?.toLowerCase().includes('matches') ? 'verified' : 'neutral'} icon={<Car size={13} />}>{result?.vehicle_match_status?.toLowerCase().includes('matches') ? 'Vehicle Match' : 'Vehicle Check'}</ScannerBadge>
        <ScannerBadge tone="neutral" icon={<BookOpen size={13} />}>{mode === 'question' ? 'Legal Query' : 'Evidence Scan'}</ScannerBadge>
        <ScannerBadge tone={judgeScore >= 24 ? 'verified' : judgeScore ? 'review' : 'neutral'} icon={<Gavel size={13} />}>Judge {judgeScore}/30</ScannerBadge>
        <ScannerBadge tone={confidence >= 80 ? 'verified' : confidence ? 'review' : 'neutral'} icon={<Gauge size={13} />}>Confidence {confidence}%</ScannerBadge>
      </div>
      <div className="verification-chain">
        {['Evidence Scanned', 'Vehicle Matched', 'Legal Context', 'Guardrails', 'LLM Judge', 'PDF Report'].map((item, idx) => (
          <div key={item} className={cx('chain-step', result && 'done', loading && idx < 3 && 'active')}>
            <span>{idx + 1}</span><p>{item}</p>
          </div>
        ))}
      </div>
    </aside>
  );
}

function MetricCard({ label, value, icon, tone = 'info', helper }) {
  return (
    <div className={cx('metric-card', tone)}>
      <div className="metric-icon">{icon}</div>
      <div>
        <small>{label}</small>
        <strong>{value || '-'}</strong>
        {helper && <p>{helper}</p>}
      </div>
    </div>
  );
}

function formatBrief(text = '') {
  const clean = String(text || '').replace(/Text from source:/gi, '').replace(/Source \d+,?/gi, '').replace(/\s+/g, ' ').trim();
  return clean.length > 520 ? clean.slice(0, 520).replace(/\s+\S*$/, '') + '…' : clean;
}

function LegalSources({ result }) {
  const groups = result?.legal_reference_groups || result?.grouped_legal_references || {};
  if (groups && Object.keys(groups).length) {
    return (
      <div className="legal-groups">
        {Object.entries(groups).map(([act, refs]) => (
          <details className="legal-act" key={act} open>
            <summary><Scale size={16} /> {act}</summary>
            <div className="legal-ref-list">
              {(refs || []).map((ref, idx) => <div className="legal-ref" key={idx}>{typeof ref === 'string' ? formatBrief(ref) : formatBrief(ref.definition || ref.text || ref.summary || JSON.stringify(ref))}</div>)}
            </div>
          </details>
        ))}
      </div>
    );
  }
  const refs = result?.brief_legal_references || [];
  if (refs.length) {
    return <div className="legal-groups"><details className="legal-act" open><summary><Scale size={16} /> Retrieved Legal References</summary>{refs.slice(0, 5).map((ref, idx) => <div className="legal-ref" key={idx}>{formatBrief(ref)}</div>)}</details></div>;
  }
  const display = (result?.retrieved_sections || []).slice(0, 5);
  if (!display.length) return <p className="muted empty-state">No legal references retrieved.</p>;
  return (
    <div className="legal-groups">
      <details className="legal-act" open>
        <summary><Scale size={16} /> Retrieved Legal Context</summary>
        {display.map((item, idx) => <div className="legal-ref" key={idx}><b>{item.section || `Reference ${idx + 1}`}</b><p>{formatBrief(item.summary)}</p></div>)}
      </details>
    </div>
  );
}

function ExecutionLog({ logs = [] }) {
  if (!logs?.length) return <div className="terminal"><div className="terminal-line muted">No execution log available.</div></div>;
  return (
    <div className="terminal">
      <div className="terminal-toolbar"><span /><span /><span /><b>agent-trace.log</b></div>
      {logs.map((log, idx) => {
        const type = normalizeLogType(log);
        return <div className={cx('terminal-line', type)} key={idx}><span className="line-no">{String(idx + 1).padStart(2, '0')}</span><span className="tag">[{type.toUpperCase()}]</span><span>{log}</span></div>;
      })}
    </div>
  );
}

function SafetyPanel({ result }) {
  const guardrail = result?.guardrail_result || {};
  const judge = result?.judge_result || {};
  const warnings = guardrail.warnings || [];
  const actions = guardrail.actions || [];
  const scoreRows = [
    ['Grounding', judge.grounding_score],
    ['Citation', judge.citation_score],
    ['State Relevance', judge.state_relevance_score],
    ['Hallucination Risk', judge.hallucination_risk_score],
    ['Clarity', judge.clarity_score],
    ['Safety', judge.safety_score],
  ];
  return (
    <div className="safety-grid">
      <div className="safety-card">
        <div className="section-heading"><ShieldAlert size={18} /><h3>Guardrails Validation</h3></div>
        <div className={cx('status-pill', guardrail.passed === false ? 'danger' : 'pass')}>{guardrail.passed === false ? 'Warnings Found' : 'Passed'}</div>
        <h4>Actions Applied</h4>
        {actions.length ? actions.map((a, idx) => <div className="notice pass" key={idx}>{idx + 1}. {a}</div>) : <p className="muted">No guardrail action applied.</p>}
        <h4>Warnings</h4>
        {warnings.length ? warnings.map((w, idx) => <div className="notice warn" key={idx}>{idx + 1}. {w}</div>) : <div className="notice pass">No guardrail warning detected.</div>}
      </div>
      <div className="safety-card">
        <div className="section-heading"><Gavel size={18} /><h3>LLM-as-a-Judge</h3></div>
        <div className={cx('judge-verdict', judge.verdict === 'PASS' ? 'pass' : judge.verdict === 'FAIL' ? 'danger' : 'warn')}>
          <strong>{judge.total_score ?? 0}/30</strong><span>{judge.verdict || 'Not evaluated'}</span>
        </div>
        <div className="judge-bars">
          {scoreRows.map(([label, value]) => <div className="judge-bar" key={label}><span>{label}</span><div><i style={{ width: `${((value || 0) / 5) * 100}%` }} /></div><b>{value ?? 0}/5</b></div>)}
        </div>
        <p className="judge-reason"><b>Reason:</b> {judge.reason || '-'}</p>
      </div>
    </div>
  );
}

function KV({ label, value, tone }) { return <div className={cx('kv-card', tone)}><span>{label}</span><b>{value || '-'}</b></div>; }

function ResultDashboard({ result }) {
  const [tab, setTab] = useState('report');
  if (!result) return null;
  const issueCount = result.validation_issues?.length || 0;
  const vehicleOk = result.vehicle_match_status?.toLowerCase().includes('matches') || result.vehicle_validation_result?.toLowerCase().includes('matches');
  const statusTone = hasDiscrepancy(result) ? 'danger' : needsReview(result) ? 'warn' : isPass(result) ? 'pass' : 'info';

  return (
    <section className="results-shell">
      <div className="metric-grid">
        <MetricCard label="Final Status" value={result.final_status} icon={<ShieldCheck />} tone={statusTone} helper={needsReview(result) ? 'Review recommended before action' : 'AI verification status'} />
        <MetricCard label="Confidence Score" value={`${result.confidence_score || 0}/100`} icon={<Activity />} tone={(result.confidence_score || 0) >= 80 ? 'pass' : 'warn'} />
        <MetricCard label="Judge Score" value={`${result.judge_result?.total_score || 0}/30`} icon={<Gavel />} tone={result.judge_result?.verdict === 'PASS' ? 'pass' : result.judge_result?.verdict === 'FAIL' ? 'danger' : 'warn'} />
        <MetricCard label="Vehicle Match" value={vehicleOk ? 'Verified' : 'Check Required'} icon={<Car />} tone={vehicleOk ? 'pass' : 'warn'} />
        <MetricCard label="Issues" value={issueCount} icon={<AlertTriangle />} tone={issueCount ? 'danger' : 'pass'} />
      </div>
      <div className="risk-strip">
        <span>Risk Meter</span><div><i style={{ width: `${Math.max(4, Math.min(100, result.confidence_score || 0))}%` }} /></div><b>{statusTone === 'pass' ? 'Low' : statusTone === 'warn' ? 'Medium' : 'High'}</b>
      </div>
      <div className="tabs">
        {TABS.map(t => <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t}</button>)}
      </div>
      <div className="tab-panel">
        {tab === 'report' && <>
          <div className="report-card"><pre>{result.final_report}</pre></div>
          {result.report_pdf_url && <a className="download" href={reportUrl(result.report_pdf_url)} target="_blank" rel="noreferrer"><Download size={18} /> Download Legal Verification Report</a>}
        </>}
        {tab === 'ocr' && <div className="structured-grid">
          <KV label="Vehicle Number from Challan" value={result.vehicle_number} />
          <KV label="Vehicle Number from Front Image" value={result.vehicle_number_from_vehicle_image} />
          <KV label="Vehicle Type" value={result.vehicle_type || 'Unknown'} />
          <KV label="Latest Offence" value={result.latest_offence || result.offence} />
          <KV label="Latest Offence Location" value={result.latest_offence_location || result.place_of_violation} />
          <KV label="Latest Date & Time" value={result.latest_offence_datetime || result.date_time} />
          <KV label="Latest Fine Amount" value={`₹${result.latest_fine_amount || result.fine_amount || 0}`} />
          <KV label="Expected Fine" value={result.expected_fine_text || (result.expected_fine ? `₹${result.expected_fine}` : '-')} />
          <KV label="Evidence Timestamp" value={result.evidence_timestamp} />
          <KV label="Multiple Offences Detected" value={result.multiple_offences ? 'Yes' : 'No'} tone={result.multiple_offences ? 'warn' : 'pass'} />
          <KV label="Extraction Confidence" value={`${result.ocr_confidence || 0}%`} />
          <KV label="Evidence Quality" value={result.image_quality} />
        </div>}
        {tab === 'validation' && <div className="issue-grid">
          {issueCount ? result.validation_issues.map((i, idx) => <div className="issue-card" key={idx}><AlertTriangle size={18} /><div><b>Issue {idx + 1}</b><p>{i}</p></div></div>) : <div className="notice pass"><CheckCircle2 size={16} /> No major validation issue detected.</div>}
        </div>}
        {tab === 'legal' && <div className="legal-layout"><div className="legal-analysis"><h3>Legal Analysis</h3><p>{result.legal_analysis || result.legal_answer || 'No legal analysis available.'}</p></div><LegalSources result={result} /></div>}
        {tab === 'safety' && <SafetyPanel result={result} />}
        {tab === 'logs' && <ExecutionLog logs={result.execution_log} />}
      </div>
    </section>
  );
}

function VerificationWorkspace({ mode, setMode }) {
  const [form, setForm] = useState({ user_type: 'Vehicle Owner', selected_state: 'TS', user_name: '', input_vehicle_number: '' });
  const [challanFile, setChallanFile] = useState(null);
  const [vehicleFile, setVehicleFile] = useState(null);
  const [questionForm, setQuestionForm] = useState({ user_type: 'Vehicle Owner', selected_state: 'TS', user_name: '', question: 'What is the fine for not wearing helmet?' });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  async function submitVerify(e) {
    e.preventDefault(); setLoading(true); setError(''); setResult(null);
    try {
      const data = await verifyChallan({ ...form, challan_file: challanFile, vehicle_front_file: vehicleFile });
      setResult(data);
    } catch (err) { setError(err.message || String(err)); } finally { setLoading(false); }
  }

  async function submitQuestion(e) {
    e.preventDefault(); setLoading(true); setError(''); setResult(null);
    try {
      const data = await askLegalQuestion(questionForm);
      setResult(data);
    } catch (err) { setError(err.message || String(err)); } finally { setLoading(false); }
  }

  return (
    <>
      <section className="workspace">
        <div className="input-panel">
          <div className="mode-tabs">
            <button className={mode === 'verify' ? 'active' : ''} onClick={() => setMode('verify')}><FileText size={17} /> Verify Challan</button>
            <button className={mode === 'question' ? 'active' : ''} onClick={() => setMode('question')}><Search size={17} /> Ask Traffic Law Assistant</button>
          </div>
          {mode === 'verify' ? (
            <form onSubmit={submitVerify} className="input-form">
              <div className="form-grid">
                <Field label="User Type"><select value={form.user_type} onChange={e => setForm({ ...form, user_type: e.target.value })}>{USER_TYPES.map(u => <option key={u}>{u}</option>)}</select></Field>
                <Field label="State"><select value={form.selected_state} onChange={e => setForm({ ...form, selected_state: e.target.value })}>{STATES.map(s => <option value={s.value} key={s.value}>{s.label}</option>)}</select></Field>
                <Field label="Name optional"><input placeholder="Enter name" value={form.user_name} onChange={e => setForm({ ...form, user_name: e.target.value })} /></Field>
                <Field label="Vehicle Number optional"><input placeholder="e.g., TS07GU2016" value={form.input_vehicle_number} onChange={e => setForm({ ...form, input_vehicle_number: e.target.value })} /></Field>
                <div className="wide upload-grid">
                  <UploadZone label="Upload Challan PDF/Image" helper="Drag and drop challan screenshot, PDF, PNG, or JPG" file={challanFile} setFile={setChallanFile} accept="image/*,.pdf" icon={<FileSearch size={24} />} />
                  <UploadZone label="Upload Vehicle Front Image" helper="Used for number plate and evidence matching" file={vehicleFile} setFile={setVehicleFile} accept="image/*" icon={<Car size={24} />} />
                </div>
              </div>
              <button disabled={loading || !challanFile} className="primary"><Zap size={18} /> {loading ? 'Running AI Verification...' : 'Run AI Verification'}</button>
              <p className="helper-line"><HelpCircle size={14} /> State rules are prioritized when a matching state penalty is retrieved.</p>
            </form>
          ) : (
            <form onSubmit={submitQuestion} className="input-form">
              <div className="form-grid">
                <Field label="User Type"><select value={questionForm.user_type} onChange={e => setQuestionForm({ ...questionForm, user_type: e.target.value })}>{USER_TYPES.map(u => <option key={u}>{u}</option>)}</select></Field>
                <Field label="State"><select value={questionForm.selected_state} onChange={e => setQuestionForm({ ...questionForm, selected_state: e.target.value })}>{STATES.map(s => <option value={s.value} key={s.value}>{s.label}</option>)}</select></Field>
                <Field label="Name optional" wide><input placeholder="Enter name" value={questionForm.user_name} onChange={e => setQuestionForm({ ...questionForm, user_name: e.target.value })} /></Field>
                <Field label="Traffic law question" wide><textarea value={questionForm.question} onChange={e => setQuestionForm({ ...questionForm, question: e.target.value })} placeholder="Ask: What is the fine for wrong parking in Telangana?" /></Field>
              </div>
              <button disabled={loading || !questionForm.question} className="primary"><Bot size={18} /> {loading ? 'Retrieving Legal Context...' : 'Ask Traffic Law Assistant'}</button>
            </form>
          )}
          {error && <div className="error-box"><XCircle size={18} /> {error}</div>}
        </div>
        <LiveAIScanner result={result} loading={loading} mode={mode} />
      </section>
      <ResultDashboard result={result} />
    </>
  );
}

function App() {
  const [mode, setMode] = useState('verify');
  return (
    <main>
      <Header />
      <HeroBanner />
      <VerificationWorkspace mode={mode} setMode={setMode} />
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
