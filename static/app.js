const DOM = {
    healthDropZone: document.getElementById('healthDropZone'),
    policyDropZone: document.getElementById('policyDropZone'),
    healthInput: document.getElementById('healthInput'),
    policyInput: document.getElementById('policyInput'),
    healthFileName: document.getElementById('healthFileName'),
    policyFileName: document.getElementById('policyFileName'),
    analyzeBtn: document.getElementById('analyzeBtn'),
    uploadStatus: document.getElementById('uploadStatus'),
    heroSection: document.getElementById('heroSection'),
    landingView: document.getElementById('landingView'),
    resultsSection: document.getElementById('resultsSection'),
    resultsContent: document.getElementById('resultsContent'),
    disclaimerText: document.getElementById('disclaimerText'),
    endSessionBtn: document.getElementById('endSessionBtn'),
    progressOverlay: document.getElementById('progressOverlay'),
    progressTitle: document.getElementById('progressTitle'),
    progressSubtitle: document.getElementById('progressSubtitle'),
    errorToast: document.getElementById('errorToast'),
    errorMessage: document.getElementById('errorMessage'),
    reportTimestamp: document.getElementById('reportTimestamp'),
    // Token Tracker
    tokenTracker: document.getElementById('tokenTracker'),
    promptTokens: document.getElementById('promptTokens'),
    completionTokens: document.getElementById('completionTokens'),
    totalTokens: document.getElementById('totalTokens'),
    // Advisor Lead
    advisorBtn: document.getElementById('advisorBtn'),
    advisorModal: document.getElementById('advisorModal'),
    advisorForm: document.getElementById('advisorForm'),
};

let sessionId = null;
let healthFile = null;
let policyFile = null;

// Production-grade State Management
const UIState = {
    setLoading(title, subtitle) {
        DOM.progressTitle.textContent = title;
        DOM.progressSubtitle.textContent = subtitle;
        DOM.progressOverlay.classList.remove('hidden');
    },
    hideLoading() {
        DOM.progressOverlay.classList.add('hidden');
    },
    showToast(msg, type = 'error') {
        const container = document.getElementById('toastContainer');
        if (!container) return;
        
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const icon = type === 'error' ? '✕' : type === 'success' ? '✓' : '⚠';
        
        toast.innerHTML = `
            <div class="toast-icon">${icon}</div>
            <div class="toast-msg">${msg}</div>
        `;
        
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 400);
        }, 4000);
    },
    showError(msg) {
        this.showToast(msg, 'error');
        // Keep legacy for existing HTML if needed
        if (DOM.errorMessage && DOM.errorToast) {
            DOM.errorMessage.textContent = msg;
            DOM.errorToast.classList.remove('hidden');
            setTimeout(() => DOM.errorToast.classList.add('hidden'), 5000);
        }
    },
    showSuccess(msg) { this.showToast(msg, 'success'); },
    showWarning(msg) { this.showToast(msg, 'warning'); },
    showSection(sectionId) {
        [DOM.heroSection, DOM.resultsSection].forEach(s => {
            if (s) s.classList.add('hidden');
        });
        const target = document.getElementById(sectionId);
        if (target) target.classList.remove('hidden');
        window.scrollTo(0, 0);
    }
};

// --- Error Translation Layer: Maps technical errors to user-friendly messages ---
function translateError(rawMsg) {
    if (!rawMsg) return 'An unexpected error occurred. Please try again.';
    const msg = rawMsg.toLowerCase();
    if (msg.includes('session expired') || msg.includes('session not found') || msg.includes('backend restarted'))
        return 'Your session has expired. Please refresh the page to start a new session.';
    if (msg.includes('both') && msg.includes('upload') || msg.includes('medical report and insurance'))
        return 'Please upload both your medical report and insurance policy before running the analysis.';
    if (msg.includes('file too large') || msg.includes('maximum') && msg.includes('5mb'))
        return 'This file is too large. Maximum allowed size is 5MB. Please compress your document and try again.';
    if (msg.includes('invalid file format') || msg.includes('valid pdf'))
        return 'Invalid document format. Please upload a valid PDF document.';
    if (msg.includes('password-protected') || msg.includes('corrupted'))
        return 'Could not read the PDF. Please ensure it is not password-protected or corrupted.';
    if (msg.includes('timed out') || msg.includes('timeout') || msg.includes('high load'))
        return 'The request timed out. The system is under high load. Please try again in a moment.';
    if (msg.includes('intelligence engine') || msg.includes('starting up') || msg.includes('connect'))
        return 'The Intelligence Engine is unavailable. Please wait a moment and try again.';
    if (msg.includes('scanner') || msg.includes('ocr'))
        return 'Document scanner is temporarily unavailable. Please try again in a moment.';
    if (msg.includes('text is too short') || msg.includes('too short to be a valid'))
        return 'The document could not be read properly. Please ensure your PDF contains readable text.';
    if (msg.includes('could not read') || msg.includes('readable text'))
        return 'The uploaded documents could not be processed. Please ensure they contain readable text.';
    if (msg.includes('something went wrong') || msg.includes('internal error'))
        return 'Something went wrong on our end. Please try again.';
    // Return a cleaned version of the raw message as final fallback
    return rawMsg.length > 120 ? rawMsg.substring(0, 120) + '...' : rawMsg;
}

// Initialize Session (with retry)
(async function init() {
    const MAX_RETRIES = 3;
    let attempt = 0;
    let success = false;

    while (attempt < MAX_RETRIES && !success) {
        try {
            const res = await fetch('/session/start', { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            sessionId = data.session_id;
            success = true;
        } catch (e) {
            attempt++;
            if (attempt < MAX_RETRIES) {
                await new Promise(r => setTimeout(r, 1000 * attempt));
            }
        }
    }

    if (!success) {
        // Show persistent banner — toast alone is not enough for this critical failure  
        const banner = document.createElement('div');
        banner.id = 'sessionFailBanner';
        banner.style.cssText = 'position:fixed;top:0;left:0;width:100%;background:#c0392b;color:#fff;text-align:center;padding:14px 20px;z-index:9999;font-weight:600;font-size:0.95rem;';
        banner.textContent = '⚠ Service Unavailable — Could not establish a secure session. Please refresh the page or try again later.';
        document.body.prepend(banner);
        UIState.showError('Security Handshake Failed. Please refresh the page.');
    }
})();

function setupDropZone(zone, input, labelEl, type) {
    if (!zone || !input) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(e => {
        zone.addEventListener(e, evt => {
            evt.preventDefault();
            evt.stopPropagation();
        });
    });

    zone.addEventListener('dragenter', () => zone.classList.add('dragover'));
    zone.addEventListener('dragover', () => zone.classList.add('dragover'));
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', () => zone.classList.remove('dragover'));

    zone.addEventListener('drop', e => {
        const files = e.dataTransfer.files;
        if (files.length) handleFileSelect(files[0], labelEl, type, zone);
    });

    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', e => {
        if (e.target.files.length) handleFileSelect(e.target.files[0], labelEl, type, zone);
    });
}

setupDropZone(DOM.healthDropZone, DOM.healthInput, DOM.healthFileName, 'health');
setupDropZone(DOM.policyDropZone, DOM.policyInput, DOM.policyFileName, 'policy');

function handleFileSelect(file, labelEl, type, zone) {
    if (file.type !== 'application/pdf') {
        UIState.showError('Invalid Format: Only medical/insurance PDFs are allowed.');
        return;
    }

    if (file.size > 5 * 1024 * 1024) {
        UIState.showError('File Too Large: Maximum allowed size is 5MB.');
        return;
    }

    if (type === 'health') {
        if (policyFile && file.name === policyFile.name && file.size === policyFile.size) {
            UIState.showError('Duplicate File: You are attempting to upload the same file for both Health and Policy.');
            return;
        }
        healthFile = file;
        UIState.showSuccess('Medical Report verified.');
    } else {
        if (healthFile && file.name === healthFile.name && file.size === healthFile.size) {
            UIState.showError('Duplicate File: You are attempting to upload the same file for both Health and Policy.');
            return;
        }
        policyFile = file;
        UIState.showSuccess('Insurance Policy verified.');
    }

    labelEl.textContent = file.name;
    if (zone) zone.classList.add('selected');

    if (healthFile && policyFile) {
        DOM.analyzeBtn.disabled = false;
        DOM.analyzeBtn.classList.remove('disabled');
    }
}

DOM.analyzeBtn.addEventListener('click', async () => {
    if (!healthFile || !policyFile) {
        UIState.showError('Please select both your medical report and insurance policy before continuing.');
        return;
    }
    if (!sessionId) {
        UIState.showError('Session is not active. Please refresh the page.');
        return;
    }
    
    try {
        UIState.setLoading("Document Secure Upload", "Encrypting and transmitting medical records...");
        
        await Promise.all([
            upload(healthFile, 'health'),
            upload(policyFile, 'policy')
        ]);
        
        triggerAnalysis();
        
    } catch (e) {
        UIState.hideLoading();
        UIState.showError(translateError(e.message));
    }
});

// ── Token Tracker Helpers ──────────────────────────────────────────────────
function animateTokenValue(el, value) {
    if (!el) return;
    el.textContent = value.toLocaleString();
    el.classList.remove('pop-update');
    // Force reflow to restart animation
    void el.offsetWidth;
    el.classList.add('pop-update');
    el.addEventListener('animationend', () => el.classList.remove('pop-update'), { once: true });
}

function showTokenTracker() {
    if (!DOM.tokenTracker) return;
    DOM.tokenTracker.classList.remove('hidden');
}

function resetTokenTracker() {
    if (!DOM.tokenTracker) return;
    DOM.tokenTracker.classList.add('hidden');
    if (DOM.promptTokens)     DOM.promptTokens.textContent     = '0';
    if (DOM.completionTokens) DOM.completionTokens.textContent = '0';
    if (DOM.totalTokens)      DOM.totalTokens.textContent      = '0';
}
// ──────────────────────────────────────────────────────────────────────────

function triggerAnalysis() {
    UIState.setLoading("Establishing Connection", "Connecting to Live Intelligence Engine...");
    showTokenTracker();
    
    // Reset Token UI
    animateTokenValue(DOM.promptTokens, 0);
    animateTokenValue(DOM.completionTokens, 0);
    animateTokenValue(DOM.totalTokens, 0);

    const es = new EventSource(`/analyze/stream/${sessionId}`);

    es.addEventListener('queue', (e) => {
        const data = JSON.parse(e.data);
        UIState.hideLoading();
        document.getElementById('queueOverlay')?.classList.remove('hidden');
        document.getElementById('queuePosition') && (document.getElementById('queuePosition').innerText = `${data.position} / ${data.total}`);
        document.getElementById('queueWait') && (document.getElementById('queueWait').innerText = `~${data.wait_estimate} minutes`);
    });

    es.addEventListener('step', (e) => {
        const data = JSON.parse(e.data);
        document.getElementById('queueOverlay')?.classList.add('hidden');
        UIState.hideLoading();

        if (DOM.resultsSection.classList.contains('hidden')) {
            renderSkeletons(data.message);
        } else {
            const sm = document.getElementById('skeletonMessage');
            if (sm) sm.innerText = data.message;
        }
    });

    // ── Token event: update the floating tracker ──
    es.addEventListener('token', (e) => {
        const t = JSON.parse(e.data);
        animateTokenValue(DOM.promptTokens,     t.prompt     ?? 0);
        animateTokenValue(DOM.completionTokens, t.completion ?? 0);
        animateTokenValue(DOM.totalTokens,      t.total      ?? 0);
    });

    es.addEventListener('retry', (e) => {
        const data = JSON.parse(e.data);
        DOM.progressSubtitle.textContent = `Optimizing ${data.agent_alias}...`;
        UIState.showToast(`Neural Node busy. Rerouting to ${data.agent_alias}...`, 'warning');
    });

    es.addEventListener('result', (e) => {
        const data = JSON.parse(e.data);
        es.close();
        clearTimeout(watchdogTimer);
        renderResults(data);
    });

    // Watchdog: close stream and show error if no result arrives in 180 seconds
    const watchdogTimer = setTimeout(() => {
        es.close();
        UIState.hideLoading();
        UIState.showError('Analysis is taking longer than expected. Please try again. If the issue persists, try uploading simpler documents.');
    }, 180000);

    es.addEventListener('error', (e) => {
        es.close();
        clearTimeout(watchdogTimer);
        UIState.hideLoading();
        try {
            const data = JSON.parse(e.data);
            UIState.showError(translateError(data.detail || 'Stream connection lost.'));
        } catch {
            // Native EventSource error (network disconnect)
            UIState.showError('Connection to Intelligence Engine lost. Please check your internet and try again.');
        }
    });

    // Native onerror (network-level disconnect, not server-sent error event)
    es.onerror = (e) => {
        if (es.readyState === EventSource.CLOSED) {
            clearTimeout(watchdogTimer);
            UIState.hideLoading();
            UIState.showError('Connection lost. Please check your internet connection and try again.');
        }
    };
}

function renderSkeletons(msg = "Analyzing...") {
    // ── Cinematic Transition ──
    DOM.landingView.classList.add('view-fade-out');
    
    setTimeout(() => {
        DOM.landingView.classList.add('hidden');
        DOM.resultsSection.classList.remove('hidden');
        DOM.resultsSection.classList.add('view-fade-in');
        DOM.endSessionBtn.classList.remove('hidden');
        
        window.scrollTo({ top: 0, behavior: 'smooth' });
        DOM.reportTimestamp.textContent = `Live Stream Active`;
    }, 400); // Wait for fade-out to begin
    
    const content = `
        <div class="result-card clean-card span-2 skeleton-card">
            <h3>System Status</h3>
            <p id="skeletonMessage" style="color: var(--primary); font-weight: bold; margin-bottom: 1rem;">>> ${msg}</p>
            <div class="sk-line long"></div>
            <div class="sk-line long"></div>
            <div class="sk-line medium"></div>
        </div>
        <div class="result-card clean-card skeleton-card">
            <div class="sk-title"></div>
            <div class="sk-line long"></div><div class="sk-line short"></div>
        </div>
        <div class="result-card clean-card skeleton-card">
            <div class="sk-title"></div>
            <div class="sk-line medium"></div><div class="sk-line long"></div>
        </div>
        <div class="result-card clean-card span-2 skeleton-card">
            <div class="sk-title"></div>
            <div class="sk-box"></div>
            <div class="sk-line long"></div>
        </div>
    `;
    DOM.resultsContent.innerHTML = content;
    document.getElementById('resultsSection').scrollIntoView({ behavior: 'smooth' });
}

async function upload(file, type) {
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('doc_type', type);
    fd.append('file', file);
    
    let res;
    try {
        res = await fetch('/upload', { method: 'POST', body: fd });
    } catch (networkErr) {
        throw new Error('Network error: Could not reach the server. Please check your connection.');
    }

    if (!res.ok) {
        let detail = `Upload failed for ${type} document.`;
        try {
            const err = await res.json();
            detail = err.detail || detail;
        } catch {}

        // Map HTTP status codes to user-friendly messages
        if (res.status === 404) throw new Error('Your session has expired. Please refresh the page.');
        if (res.status === 413) throw new Error('File too large. Maximum allowed size is 5MB. Please compress your document.');
        if (res.status === 415) throw new Error('Invalid file format. Please upload a valid PDF document.');
        if (res.status === 503) throw new Error('Intelligence Engine is starting up. Please wait a moment and try again.');
        if (res.status === 504) throw new Error('Document processing timed out. Please try a smaller or simpler PDF.');
        throw new Error(translateError(detail));
    }
    
    UIState.showSuccess(`${type.charAt(0).toUpperCase() + type.slice(1)} document processed successfully.`);
}

function renderResults(data) {
    DOM.heroSection.classList.add('hidden');
    DOM.resultsSection.classList.remove('hidden');
    DOM.endSessionBtn.classList.remove('hidden');
    
    DOM.reportTimestamp.textContent = `Generated on ${new Date().toLocaleString()}${data.agent_alias ? ` | ${data.agent_alias}` : ''}`;
    DOM.disclaimerText.textContent = data?.disclaimer || "Medical disclaimer applies.";
    
    let content = "";

    // Identity Mismatch Warning
    if (data?.validation_warnings && data.validation_warnings.length > 0) {
        content += `
            <div class="validation-warning-banner span-2">
                <div class="warning-icon">!</div>
                <div class="warning-content">
                    <h4>Identity Verification Note</h4>
                    ${data.validation_warnings.map(w => `<p>${w}</p>`).join('')}
                </div>
            </div>
        `;
    }

    content += `
        <div class="result-card clean-card span-2">
            <h3>Health Summary</h3>
            <p class="main-summary">${String(data?.summary || 'N/A')}</p>
        </div>

        <div class="result-card clean-card">
            <h3>Abnormal Parameters</h3>
            <div class="list-container">
                ${(data?.abnormal_explanations || []).map(e => `
                    <div class="list-item">
                        <strong>${String(e?.parameter || 'Value')}:</strong> ${String(e?.explanation || 'N/A')}
                    </div>
                `).join('')}
            </div>
        </div>

        <div class="result-card clean-card">
            <h3>Mapping Patterns</h3>
            <ul class="simple-list">
                ${(data?.pattern_explanation || []).map(p => `<li>${String(p)}</li>`).join('')}
            </ul>
        </div>

        <div class="result-card clean-card">
            <h3>Future Risk Outlook</h3>
            <div class="outlook-grid">
                <div class="outlook-item">
                    <strong>Short:</strong> ${String(data?.risk_outlook?.short_term || 'Stable')}
                </div>
                <div class="outlook-item">
                    <strong>Medium:</strong> ${String(data?.risk_outlook?.medium_term || 'Stable')}
                </div>
                <div class="outlook-item">
                    <strong>Long:</strong> ${String(data?.risk_outlook?.long_term || 'Stable')}
                </div>
            </div>
        </div>

        <div class="result-card clean-card">
            <h3>Safety Directives</h3>
            <ul class="simple-list">${(data?.recommendations || []).map(r => `<li>${String(r)}</li>`).join('')}</ul>
        </div>

        ${(data?.insurance?.contextual_guardrails || []).length > 0 ? `
        <div class="result-card clean-card span-2">
            <h3>Critical Policy Guardrails</h3>
            <div class="guardrails-container">
                ${data.insurance.contextual_guardrails.map(g => {
                    const rRisk = String(g.red_lining_risk || 'Low').toLowerCase();
                    return `
                    <div class="guardrail-card">
                        <div class="guardrail-header">
                            <span class="guardrail-category">${String(g.category)}</span>
                            <span class="red-line-badge ${rRisk}">
                                Red Line Risk: ${String(g.red_lining_risk || 'Low')}
                            </span>
                        </div>
                        <p class="guardrail-details">${String(g.limit_details)}</p>
                        <div class="guardrail-meta">
                            <span>Waiting Period: ${String(g.waiting_period || 'N/A')}</span>
                            <span>Source: ${String(g.source_citation || 'Policy Section')}</span>
                        </div>
                    </div>
                `}).join('')}
            </div>
        </div>
        ` : ''}

        <div class="result-card clean-card span-2">
            <div class="confidence-indicator">
                <div class="c-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><path d="m9 12 2 2 4-4"></path></svg>
                </div>
                <div class="c-text">
                    <h4>Clinical Mapping Confidence: ${Math.round((data.confidence_score || 0.95) * 100)}%</h4>
                    <p>Probability of logical alignment between clinical markers and policy text.</p>
                </div>
            </div>

            <h3>Clinical Insight Indices</h3>
            <div class="metrics-container">
                ${Object.entries(data.health_metrics || {}).map(([key, val]) => {
                    const level = val < 40 ? 'safe' : val < 70 ? 'monitor' : 'alert';
                    return `
                    <div class="metric-item">
                        <div class="metric-label-row">
                            <span class="metric-name">${key} Marker</span>
                            <span class="metric-value">${val}%</span>
                        </div>
                        <div class="h-bar-container">
                            <div class="h-bar-fill ${level}" data-value="${val}"></div>
                        </div>
                    </div>
                `}).join('')}
            </div>
        </div>

        <div class="result-card clean-card insurance-highlight span-2">
            <div class="r-head">
                <h3>Insurance Intelligence</h3>
            </div>
            <div class="mapping-grid">
                <div class="map-section covered">
                    <h4>Current Coverage</h4>
                    <ul>${(data?.insurance?.covered || []).map(i => `<li>${String(i)}</li>`).join('')}</ul>
                </div>
                <div class="map-section conditional">
                    <h4>Wait Periods</h4>
                    <ul>${(data?.insurance?.conditional || []).map(i => `<li>${String(i)}</li>`).join('')}</ul>
                </div>
                <div class="map-section excluded">
                    <h4>Exclusions</h4>
                    <ul>${(data?.insurance?.not_covered || []).map(i => `<li>${String(i)}</li>`).join('')}</ul>
                </div>
            </div>
            <div class="awareness-notice">
                <h4>Policy Wisdom</h4>
                <p>${String(data?.insurance?.future_cost_awareness || 'No major cost spikes detected.')}</p>
            </div>
        </div>

        <div class="result-card clean-card span-2 future-map-card">
            <div class="card-header">
                <h3>Vision 2027: Coverage & Out-of-Pocket Roadmap</h3>
            </div>
            
            <div class="table-container">
                <table class="future-table">
                    <thead>
                        <tr>
                            <th>Trend</th>
                            <th>Potential Diagnosis</th>
                            <th>Expected Timeframe</th>
                            <th>Insurance Confirmation</th>
                            <th>Mapping Intel</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${(data?.future_coverage_mapping || []).map(m => {
                            const status = String(m?.coverage_status || 'Checking...').toLowerCase();
                            const statusClass = status.includes('covered') && !status.includes('not') ? 'covered' : 
                                              status.includes('partial') ? 'partial' : 
                                              status.includes('excluded') || status.includes('not covered') ? 'excluded' : '';
                            const rRisk = String(m?.red_line_risk || 'Low').toLowerCase();

                            return `
                                <tr>
                                    <td><span class="t-pattern">${String(m?.pattern || 'Trend')}</span></td>
                                    <td><strong class="t-condition">${String(m?.future_condition || 'Risk')}</strong></td>
                                    <td>
                                        <div class="t-timeframe" style="color: var(--primary); font-weight: 600; font-size: 0.9rem;">
                                            ${String(m?.timeframe_years || 'Unknown')}
                                        </div>
                                    </td>
                                    <td>
                                        <div class="t-status ${statusClass}">
                                            ${String(m?.coverage_status || 'Checking...')}
                                        </div>
                                        <div class="risk-tag ${rRisk}">
                                            Risk: ${String(m?.red_line_risk || 'Low')}
                                        </div>
                                    </td>
                                    <td>
                                        <div class="t-source" style="font-size: 0.75rem; color: var(--text-tertiary); font-style: italic;">
                                            ${String(m?.source_proof || 'Mapping evidence...')}
                                        </div>
                                        <div class="intent-clarity">
                                            Intent Clarity: ${String(m?.intent_clarity_explanation || 'Logical mapping active')}
                                        </div>
                                    </td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
    
    DOM.resultsContent.innerHTML = content;

    // ── Animate Health Metrics ──
    setTimeout(() => {
        const bars = document.querySelectorAll('.h-bar-fill');
        bars.forEach(bar => {
            const val = bar.getAttribute('data-value');
            if (val) bar.style.width = `${val}%`;
        });
    }, 300);
}

if (DOM.endSessionBtn) {
    DOM.endSessionBtn.addEventListener('click', async () => {
        if (!sessionId) return;
        if (confirm("Permanently destroy this analysis session?")) {
            await fetch('/session/end', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });
            location.reload();
        }
    });
}

// --- Advisor Partner Funnel ---
function initAdvisorLeads() {
    const btn = document.getElementById('advisorBtn');
    const modal = document.getElementById('advisorModal');
    const form = document.getElementById('advisorForm');
    const closeBtns = document.querySelectorAll('.modal-close, .modal-backdrop');

    const openModal = () => {
        if (modal) {
            modal.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        }
    };

    const closeModal = () => {
        if (modal) {
            modal.classList.add('hidden');
            document.body.style.overflow = '';
        }
    };

    if (btn) {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            openModal();
        });
    }

    closeBtns.forEach(c => {
        c.addEventListener('click', (e) => {
            e.preventDefault();
            closeModal();
        });
    });

    if (form) {
        // Per-field inline error helper
        function setFieldError(fieldId, msg) {
            const field = document.getElementById(fieldId);
            if (!field) return;
            field.style.borderColor = msg ? '#e74c3c' : '';
            let errEl = field.parentElement.querySelector('.field-error');
            if (msg) {
                if (!errEl) {
                    errEl = document.createElement('small');
                    errEl.className = 'field-error';
                    errEl.style.cssText = 'color:#e74c3c;font-size:0.78rem;display:block;margin-top:3px;';
                    field.parentElement.appendChild(errEl);
                }
                errEl.textContent = msg;
            } else if (errEl) {
                errEl.remove();
                field.style.borderColor = '';
            }
        }

        function validateAdvisorForm() {
            let valid = true;
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            const phoneRegex = /^[\d\s\-\+\(\)]{7,20}$/;

            const name = document.getElementById('advName')?.value.trim();
            const email = document.getElementById('advEmail')?.value.trim();
            const phone = document.getElementById('advPhone')?.value.trim();
            const agency = document.getElementById('advAgency')?.value.trim();
            const exp = document.getElementById('advExp')?.value.trim();
            const spec = document.getElementById('advSpec')?.value;

            if (!name) { setFieldError('advName', 'Full name is required.'); valid = false; }
            else setFieldError('advName', null);

            if (!email || !emailRegex.test(email)) { setFieldError('advEmail', 'Please enter a valid email address.'); valid = false; }
            else setFieldError('advEmail', null);

            if (!phone || !phoneRegex.test(phone)) { setFieldError('advPhone', 'Please enter a valid phone number.'); valid = false; }
            else setFieldError('advPhone', null);

            if (!agency) { setFieldError('advAgency', 'Agency name is required.'); valid = false; }
            else setFieldError('advAgency', null);

            if (!exp) { setFieldError('advExp', 'Please select your years of experience.'); valid = false; }
            else setFieldError('advExp', null);

            if (!spec) { setFieldError('advSpec', 'Please select your specialization.'); valid = false; }
            else setFieldError('advSpec', null);

            return valid;
        }

        // Live validation feedback on blur
        ['advName','advEmail','advPhone','advAgency','advExp','advSpec'].forEach(id => {
            document.getElementById(id)?.addEventListener('blur', () => validateAdvisorForm());
        });

        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            if (!validateAdvisorForm()) {
                UIState.showWarning('Please fix the highlighted fields before submitting.');
                return;
            }

            const submitBtn = form.querySelector('button[type="submit"]');
            const originalText = submitBtn.innerHTML;
            
            try {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span>Registering...</span>';
                
                const payload = {
                    name: document.getElementById('advName').value.trim(),
                    email: document.getElementById('advEmail').value.trim(),
                    phone: document.getElementById('advPhone').value.trim(),
                    agency: document.getElementById('advAgency').value.trim(),
                    experience: document.getElementById('advExp').value.trim(),
                    specialization: document.getElementById('advSpec').value
                };

                const res = await fetch('/advisor/lead', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || 'Submission failed. Please check your details and try again.');
                }
                
                UIState.showSuccess('Welcome aboard! Your access window has been reserved.');
                closeModal();
                form.reset();
                // Clear inline errors
                ['advName','advEmail','advPhone','advAgency','advExp','advSpec'].forEach(id => setFieldError(id, null));
            } catch (err) {
                UIState.showError(translateError(err.message || 'Submission failed. Please check your connection.'));
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        });
    }
}

// Initialize recruitment funnel
initAdvisorLeads();
