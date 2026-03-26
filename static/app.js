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
    reportTimestamp: document.getElementById('reportTimestamp')
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
        if (files.length) handleFileSelect(files[0], labelEl, type);
    });

    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', e => {
        if (e.target.files.length) handleFileSelect(e.target.files[0], labelEl, type);
    });
}

setupDropZone(DOM.healthDropZone, DOM.healthInput, DOM.healthFileName, 'health');
setupDropZone(DOM.policyDropZone, DOM.policyInput, DOM.policyFileName, 'policy');

function handleFileSelect(file, labelEl, type) {
    if (file.type !== 'application/pdf') {
        UIState.showError('Invalid Format: Only medical/insurance PDFs are allowed.');
        return;
    }
    
    if (type === 'health') {
        healthFile = file;
        DOM.healthDropZone.style.borderColor = 'var(--success)';
    } else {
        policyFile = file;
        DOM.policyDropZone.style.borderColor = 'var(--success)';
    }

    labelEl.textContent = file.name;
    labelEl.classList.add('selected');
    
    if (healthFile && policyFile) {
        DOM.analyzeBtn.disabled = false;
        DOM.analyzeBtn.classList.remove('disabled');
    }
}

DOM.analyzeBtn.addEventListener('click', async () => {
    if (!healthFile || !policyFile || !sessionId) return;
    
    try {
        UIState.setLoading("Document Secure Upload", "Encrypting and transmitting medical records...");
        
        // Parallel Upload for efficiency
        await Promise.all([
            upload(healthFile, 'health'),
            upload(policyFile, 'policy')
        ]);
        
        UIState.setLoading("OCR & Fact Extraction", "Mistral AI is reading laboratory values and policy clauses...");
        
        const analyzeRes = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });
        
        if (!analyzeRes.ok) {
            const err = await analyzeRes.json();
            throw new Error(err.detail || "Intelligent Analysis Failed");
        }
        
        UIState.setLoading("Rendering Intelligence", "Assembling your personalized coverage roadmap...");
        const result = await analyzeRes.json();
        
        setTimeout(() => {
            renderResults(result);
            UIState.hideLoading();
        }, 800);
        
    } catch (e) {
        UIState.hideLoading();
        UIState.showError(e.message);
    }
});

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
        <div class="result-card glass-card span-2">
            <h3>Health Summary</h3>
            <p class="main-summary">${String(data?.summary || 'N/A')}</p>
        </div>

        <div class="result-card glass-card">
            <h3>Abnormal Parameters</h3>
            <div class="list-container">
                ${(data?.abnormal_explanations || []).map(e => `
                    <div class="list-item">
                        <strong>${String(e?.parameter || 'Value')}:</strong> ${String(e?.explanation || 'N/A')}
                    </div>
                `).join('')}
            </div>
        </div>

        <div class="result-card glass-card">
            <h3>Mapping Patterns</h3>
            <ul class="simple-list">
                ${(data?.pattern_explanation || []).map(p => `<li>${String(p)}</li>`).join('')}
            </ul>
        </div>

        <div class="result-card glass-card">
            <h3>Future Risk Outlook</h3>
            <div class="outlook-grid">
                <div class="outlook-item">
                    <strong>Short:</strong> ${String(data?.risk_outlook?.short_term || 'Stable')}
                    <span class="badg mini">${String(data?.risk_outlook?.short_term_multiplier || '')}</span>
                </div>
                <div class="outlook-item">
                    <strong>Medium:</strong> ${String(data?.risk_outlook?.medium_term || 'Stable')}
                    <span class="badg mini warn">${String(data?.risk_outlook?.medium_term_multiplier || '')}</span>
                </div>
                <div class="outlook-item">
                    <strong>Long:</strong> ${String(data?.risk_outlook?.long_term || 'Stable')}
                    <span class="badg mini crit">${String(data?.risk_outlook?.long_term_multiplier || '')}</span>
                </div>
            </div>
        </div>

        <div class="result-card glass-card">
            <h3>Safety Directives</h3>
            <ul class="simple-list">${(data?.recommendations || []).map(r => `<li>${String(r)}</li>`).join('')}</ul>
        </div>

        <div class="result-card glass-card insurance-highlight span-2">
            <div class="r-head">
                <h3>Insurance Intelligence</h3>
                <div class="badg error">Potential Cost Hike: ${String(data?.insurance?.potential_out_of_pocket_increase || '0%')}</div>
            </div>
            <div class="mapping-grid">
                <div class="map-section covered">
                    <h4>Current Coverage</h4>
                    <ul>${(data?.insurance?.covered || []).map(i => `<li>${String(i)}</li>`).join('')}</ul>
                </div>
                <div class="map-section conditional">
                    <h4>Wait Periods / Limits</h4>
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

        <div class="result-card glass-card span-2 future-map-card">
            <div class="card-header">
                <h3>Vision 2027: Coverage & Out-of-Pocket Roadmap</h3>
                <p class="section-desc">If current health trends continue into diagnoses next year:</p>
            </div>
            
            <div class="table-container">
                <table class="future-table">
                    <thead>
                        <tr>
                            <th>Trend Identified</th>
                            <th>Potential Diagnosis</th>
                            <th>Future Severity</th>
                            <th>Insurance Confirmation</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${(data?.future_coverage_mapping || []).map(m => `
                            <tr>
                                <td><span class="t-pattern">${String(m?.pattern || 'Trend')}</span></td>
                                <td><strong class="t-condition">${String(m?.future_condition || 'Risk')}</strong></td>
                                <td><span class="badg mini warn">${String(m?.severity_trend || 'Low')}</span></td>
                                <td>
                                    <div class="t-status">
                                        ${String(m?.coverage_status || 'Checking...')}
                                        <div class="t-gap">Risk Gap: ${String(m?.coverage_gap_risk || 'N/A')}</div>
                                    </div>
                                </td>
                            </tr>
                        `).join('')}
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
        await fetch('/session/end', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });
        location.reload();
    }
});

// Changelog Modal Logic
const changelogModal = document.getElementById('changelogModal');
const openChangelog = document.getElementById('openChangelog');
const closeChangelog = document.getElementById('closeChangelog');

if (openChangelog) {
    openChangelog.addEventListener('click', () => {
        changelogModal.classList.remove('hidden');
    });
}
if (closeChangelog) {
    closeChangelog.addEventListener('click', () => {
        changelogModal.classList.add('hidden');
    });
}
