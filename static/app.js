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
    showError(msg) {
        DOM.errorMessage.textContent = msg;
        DOM.errorToast.classList.remove('hidden');
        setTimeout(() => DOM.errorToast.classList.add('hidden'), 5000);
    },
    showSection(sectionId) {
        [DOM.heroSection, DOM.resultsSection].forEach(s => {
            if (s) s.classList.add('hidden');
        });
        const target = document.getElementById(sectionId);
        if (target) target.classList.remove('hidden');
        window.scrollTo(0, 0);
    }
};

// Initialize Session
(async function init() {
    try {
        const res = await fetch('/session/start', { method: 'POST' });
        if (!res.ok) throw new Error("Could not initialize secure session");
        const data = await res.json();
        sessionId = data.session_id;
    } catch (e) {
        UIState.showError("Security Handshake Failed. Please refresh.");
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
        healthFile = file;
    } else {
        policyFile = file;
    }

    labelEl.textContent = file.name;
    if (zone) zone.classList.add('selected');

    if (healthFile && policyFile) {
        DOM.analyzeBtn.disabled = false;
        DOM.analyzeBtn.classList.remove('disabled');
    }
}

DOM.analyzeBtn.addEventListener('click', async () => {
    if (!healthFile || !policyFile || !sessionId) return;
    
    try {
        UIState.setLoading("Document Secure Upload", "Encrypting and transmitting medical records...");
        
        await Promise.all([
            upload(healthFile, 'health'),
            upload(policyFile, 'policy')
        ]);
        
        triggerAnalysis();
        
    } catch (e) {
        UIState.hideLoading();
        UIState.showError(e.message);
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

    es.addEventListener('result', (e) => {
        const data = JSON.parse(e.data);
        es.close();
        renderResults(data);
    });

    es.addEventListener('error', (e) => {
        es.close();
        UIState.hideLoading();
        try {
            const data = JSON.parse(e.data);
            UIState.showError(data.detail || "Stream connection lost.");
        } catch {
            UIState.showError("Stream connection lost or timed out.");
        }
    });
}

function renderSkeletons(msg = "Analyzing...") {
    DOM.heroSection.classList.add('hidden');
    DOM.resultsSection.classList.remove('hidden');
    DOM.endSessionBtn.classList.remove('hidden');
    DOM.reportTimestamp.textContent = `Live Stream Active`;
    // Removed 'Awaiting final analysis...' set to disclaimerText to avoid layout breaks
    
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
    
    const res = await fetch('/upload', { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`Document verification failed for ${type} report`);
}

function renderResults(data) {
    DOM.heroSection.classList.add('hidden');
    DOM.resultsSection.classList.remove('hidden');
    DOM.endSessionBtn.classList.remove('hidden');
    
    DOM.reportTimestamp.textContent = `Generated on ${new Date().toLocaleString()}`;
    DOM.disclaimerText.textContent = data?.disclaimer || "Medical disclaimer applies.";
    
    const content = `
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
                            <th>Insurance Confirmation</th>
                            <th>Source / Proof</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${(data?.future_coverage_mapping || []).map(m => {
                            const status = String(m?.coverage_status || 'Checking...').toLowerCase();
                            const statusClass = status.includes('covered') && !status.includes('not') ? 'covered' : 
                                              status.includes('partial') ? 'partial' : 
                                              status.includes('excluded') || status.includes('not covered') ? 'excluded' : '';
                            
                            return `
                                <tr>
                                    <td><span class="t-pattern">${String(m?.pattern || 'Trend')}</span></td>
                                    <td><strong class="t-condition">${String(m?.future_condition || 'Risk')}</strong></td>
                                    <td>
                                        <div class="t-status ${statusClass}">
                                            ${String(m?.coverage_status || 'Checking...')}
                                        </div>
                                    </td>
                                    <td>
                                        <div class="t-source" style="font-size: 0.75rem; color: var(--text-tertiary); font-style: italic;">
                                            ${String(m?.source_proof || 'Mapping evidence...')}
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
}

DOM.endSessionBtn.addEventListener('click', async () => {
    if (!sessionId) return;
    if (confirm("Permanently destroy this analysis session?")) {
        resetTokenTracker();
        await fetch('/session/end', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });
        location.reload();
    }
});

