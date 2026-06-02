import { useEffect, useState } from 'react';
import {
  generateResume,
  generateResumeFromJD,
  getBaseResume,
  saveBaseResume,
} from '../services/api';

/**
 * Two modes:
 *   - 'json'  : paste pre-structured ChatGPT JSON, render DOCX (legacy flow)
 *   - 'jd'    : paste raw JD; backend LLM tailors the stored base résumé,
 *               optionally preview the structured JSON, then download.
 */
export function ResumeTab({ onApplicationLogged }) {
  const [mode, setMode] = useState('jd');

  // shared state (used by both modes for preview + generate)
  const [parsed, setParsed] = useState(null);
  const [parseError, setParseError] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [genError, setGenError] = useState(null);

  // JSON-mode state
  const [raw, setRaw] = useState('');

  // JD-mode state
  const [jd, setJd] = useState('');
  const [hintCompany, setHintCompany] = useState('');
  const [hintTitle, setHintTitle] = useState('');
  const [previewing, setPreviewing] = useState(false);

  // Base résumé settings (collapsible — shown on first run with no base)
  const [baseResume, setBaseResume] = useState(null);
  const [baseText, setBaseText] = useState('');
  const [showBaseEditor, setShowBaseEditor] = useState(false);
  const [savingBase, setSavingBase] = useState(false);
  const [baseSaveError, setBaseSaveError] = useState(null);

  useEffect(() => {
    getBaseResume()
      .then((row) => {
        setBaseResume(row);
        setBaseText(row?.raw_text || '');
        if (!row) setShowBaseEditor(true);
      })
      .catch(() => {});
  }, []);

  const resetResult = () => { setResult(null); setGenError(null); };

  // ── JSON mode ────────────────────────────────────────────
  const handlePaste = (e) => {
    const text = e.target.value;
    setRaw(text);
    resetResult();
    if (!text.trim()) { setParsed(null); setParseError(null); return; }
    try {
      const json = JSON.parse(text);
      if (!json.target_company) throw new Error('Missing target_company');
      if (!json.job_title) throw new Error('Missing job_title');
      setParsed(json);
      setParseError(null);
    } catch (err) {
      setParsed(null);
      setParseError(err.message);
    }
  };

  // ── JD mode ──────────────────────────────────────────────
  const handlePreviewFromJD = async () => {
    if (!jd.trim()) return;
    setPreviewing(true);
    setParseError(null);
    resetResult();
    try {
      const { tailored } = await generateResumeFromJD(
        {
          job_description: jd,
          target_company: hintCompany || undefined,
          job_title: hintTitle || undefined,
        },
        { preview: true },
      );
      setParsed(tailored);
    } catch (err) {
      setParsed(null);
      setParseError(err.message);
    } finally {
      setPreviewing(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setGenError(null);
    setResult(null);
    try {
      let res;
      if (mode === 'json') {
        if (!parsed) return;
        res = await generateResume(parsed);
      } else {
        // JD mode: if user previewed and possibly edited the JSON they can
        // still send the edited `parsed` blob through the legacy endpoint
        // (skips the LLM round-trip). Otherwise we re-call the JD endpoint.
        if (parsed) {
          res = await generateResume(parsed);
        } else {
          res = await generateResumeFromJD({
            job_description: jd,
            target_company: hintCompany || undefined,
            job_title: hintTitle || undefined,
          });
        }
      }
      setResult(res);
      onApplicationLogged?.();
    } catch (err) {
      setGenError(err.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleClear = () => {
    setRaw(''); setJd(''); setHintCompany(''); setHintTitle('');
    setParsed(null); setParseError(null);
    setResult(null); setGenError(null);
  };

  const handleSaveBase = async () => {
    setSavingBase(true);
    setBaseSaveError(null);
    try {
      const row = await saveBaseResume({ raw_text: baseText });
      setBaseResume(row);
      setShowBaseEditor(false);
    } catch (err) {
      setBaseSaveError(err.message);
    } finally {
      setSavingBase(false);
    }
  };

  const sections = ['summary', 'skills', 'experience', 'certifications', 'education']
    .filter((s) => parsed?.[s]);

  const canGenerate =
    !generating &&
    (mode === 'json' ? !!parsed : (!!parsed || jd.trim().length >= 20));

  return (
    <div className="resume-tab">
      <div className="resume-page">

        {/* ── Page Header ── */}
        <div className="resume-page-header">
          <h2 className="resume-tab-title">Resume Generator</h2>
          <p className="resume-tab-sub">
            Tailor a résumé to a specific job. Use <b>From Job Description</b> to let
            the backend LLM rewrite your stored base résumé, or <b>From JSON</b> to
            paste a pre-structured ChatGPT response.
          </p>
        </div>

        {/* ── Mode switcher ── */}
        <div className="resume-mode-switcher" role="tablist">
          <button
            role="tab"
            aria-selected={mode === 'jd'}
            className={`btn ${mode === 'jd' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => { setMode('jd'); setParsed(null); setParseError(null); }}
          >
            From Job Description
          </button>
          <button
            role="tab"
            aria-selected={mode === 'json'}
            className={`btn ${mode === 'json' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => { setMode('json'); setParsed(null); setParseError(null); }}
          >
            From JSON
          </button>
        </div>

        {/* ── Base-résumé editor (only when needed) ── */}
        <div className="resume-base-card">
          <div className="resume-card-header">
            <span className="resume-section-label">Base résumé (master copy)</span>
            <button className="btn-link" onClick={() => setShowBaseEditor(!showBaseEditor)}>
              {showBaseEditor ? 'Hide' : (baseResume ? 'Edit' : 'Upload')}
            </button>
          </div>
          {baseResume && !showBaseEditor && (
            <p className="resume-tab-sub">
              {baseResume.raw_text.slice(0, 160).replace(/\s+/g, ' ')}…
            </p>
          )}
          {showBaseEditor && (
            <>
              <textarea
                className="resume-paste-area"
                value={baseText}
                onChange={(e) => setBaseText(e.target.value)}
                placeholder="Paste the plain-text version of your master résumé. The LLM uses this verbatim when tailoring."
                spellCheck={false}
              />
              <div className="resume-action-bar">
                <button
                  className="btn btn-primary"
                  onClick={handleSaveBase}
                  disabled={!baseText.trim() || savingBase}
                >
                  {savingBase ? 'Saving…' : 'Save base résumé'}
                </button>
                {baseSaveError && (
                  <span className="resume-gen-error">✗ {baseSaveError}</span>
                )}
              </div>
            </>
          )}
        </div>

        {/* ── Input ── */}
        {mode === 'jd' ? (
          <div className="resume-input-card">
            <div className="resume-card-header">
              <span className="resume-section-label">Job description</span>
              {(jd || raw) && <button className="btn-link" onClick={handleClear}>Clear</button>}
            </div>
            <textarea
              className="resume-paste-area"
              value={jd}
              onChange={(e) => { setJd(e.target.value); setParsed(null); resetResult(); }}
              placeholder="Paste the full job description here. The backend LLM will tailor your stored base résumé against it."
              spellCheck={false}
            />
            <div className="resume-jd-hints">
              <input
                type="text"
                placeholder="Company name (optional override)"
                value={hintCompany}
                onChange={(e) => setHintCompany(e.target.value)}
              />
              <input
                type="text"
                placeholder="Job title (optional override)"
                value={hintTitle}
                onChange={(e) => setHintTitle(e.target.value)}
              />
            </div>
            <div className="resume-action-bar">
              <button
                className="btn btn-secondary"
                onClick={handlePreviewFromJD}
                disabled={jd.trim().length < 20 || previewing || !baseResume}
                title={!baseResume ? 'Upload a base résumé first' : ''}
              >
                {previewing ? 'Tailoring…' : 'Preview tailored JSON'}
              </button>
            </div>
            {parseError && (
              <div className="resume-parse-error">✗ {parseError}</div>
            )}
          </div>
        ) : (
          <div className="resume-input-card">
            <div className="resume-card-header">
              <span className="resume-section-label">JSON Input</span>
              {raw && <button className="btn-link" onClick={handleClear}>Clear</button>}
            </div>
            <textarea
              className="resume-paste-area"
              value={raw}
              onChange={handlePaste}
              placeholder={`{\n  "target_company": "Acme Corp",\n  "job_title": "Senior Software Engineer",\n  "job_description": "We are looking for...",\n  "summary": { ... },\n  "skills": [ ... ],\n  ...\n}`}
              spellCheck={false}
            />
            {parseError && (
              <div className="resume-parse-error">✗ Invalid JSON — {parseError}</div>
            )}
          </div>
        )}

        {/* ── Preview (shared) ── */}
        {parsed && !parseError && (
          <div className="resume-preview">
            <div className="resume-preview-pills">
              <span className="preview-pill company">{parsed.target_company}</span>
              <span className="preview-pill role">{parsed.job_title}</span>
              {parsed.job_description && (
                <span className="preview-pill jd">JD ✓</span>
              )}
              {sections.map((s) => (
                <span key={s} className="preview-pill section">{s}</span>
              ))}
            </div>
          </div>
        )}

        {/* ── Generate Action ── */}
        <div className="resume-action-bar">
          <button
            className="btn btn-primary resume-generate-btn"
            onClick={handleGenerate}
            disabled={!canGenerate}
          >
            {generating ? (
              <><span className="spinner" style={{ width: 13, height: 13 }} />Generating…</>
            ) : (
              '⟡ Generate & Download'
            )}
          </button>
          {!canGenerate && !generating && (
            <span className="resume-action-hint">
              {mode === 'json'
                ? 'Paste valid JSON above to enable'
                : (baseResume
                    ? 'Paste a job description (≥20 chars) to enable'
                    : 'Upload a base résumé first')}
            </span>
          )}
        </div>

        {genError && <div className="resume-gen-error">✗ {genError}</div>}

        {/* ── Result ── */}
        {result && (
          <div className="resume-result">
            <div className="result-header">
              <span className="result-icon">✓</span>
              <span className="result-title">Resume Generated</span>
            </div>
            <div className="result-body">
              <div className="result-row">
                <span className="result-label">File</span>
                <span className="result-val">{result.filename}</span>
              </div>
              <div className="result-row">
                <span className="result-label">App ID</span>
                <span className="result-val result-id">{result.applicationId}</span>
              </div>
            </div>
            {result.duplicateWarning && (
              <div className="result-warning">
                ⚠ Duplicate detected — application already exists for this company + role today
              </div>
            )}
            <div className="result-hint">Application logged — check the Tracker tab</div>
          </div>
        )}

      </div>
    </div>
  );
}
