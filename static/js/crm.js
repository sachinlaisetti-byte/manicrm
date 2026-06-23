// crm.js – Front‑end logic for Manikanta Customer Dealer CRM
// ------------------------------------------------------------
// Global state
let googleClientId = "575061568101-4lt1m9eabuv7q7jdqps1hj568b4ch4hd.apps.googleusercontent.com";
let userEmail = null;

// Utility: safe fetch with full error handling
async function safeFetch(url, options = {}) {
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errText}`);
        }
        const data = await response.json();
        return data;
    } catch (err) {
        console.error('Fetch error:', err);
        return { __error: err.message };
    }
}

// UI helpers
function showError(elemId, message) {
    const el = document.getElementById(elemId);
    if (el) el.textContent = message;
}
function clearError(elemId) {
    const el = document.getElementById(elemId);
    if (el) el.textContent = '';
}
function hideLogin() {
    document.getElementById('loginOverlay').style.display = 'none';
    document.getElementById('dashboard').style.display = 'block';
}
function showLogin() {
    document.getElementById('loginOverlay').style.display = 'flex';
    document.getElementById('dashboard').style.display = 'none';
}

// Google Sign‑In initialization with defensive polling and crash isolation
function safeInitGoogle() {
    try {
        if (typeof window.google !== 'undefined' && window.google.accounts && window.google.accounts.id) {
            google.accounts.id.initialize({
                client_id: googleClientId,
                callback: handleCredentialResponse,
                auto_select: false,
                itp_support: true
            });
            var btn = document.getElementById("google-signin-btn");
            if (btn) google.accounts.id.renderButton(btn, { theme: 'outline', size: 'large', width: 240 });
        }
    } catch (err) {
        console.warn('[UNEXPECTED_ISSUE] AuthService client initialization failed:', err);
        showError('loginError', 'Sign-in service temporarily unavailable. Please refresh.');
    }
}

function initGoogleSignIn() {
    try {
        let attempts = 0;
        const maxAttempts = 10;
        const interval = 300;
        const poll = setInterval(function() {
            attempts++;
            if (window.google && window.google.accounts && window.google.accounts.id) {
                clearInterval(poll);
                safeInitGoogle();
            } else if (attempts >= maxAttempts) {
                clearInterval(poll);
                showError('loginError', 'Unable to load Google Sign‑In. Please refresh the page.');
            }
        }, interval);
    } catch (err) {
        console.warn('[UNEXPECTED_ISSUE] Google Sign-In poll initialization failed:', err);
        showError('loginError', 'Sign-in service unavailable. Please refresh.');
    }
}

function handleCredentialResponse(response) {
    // Decode JWT payload (base64 decode) only to extract email for UI – no server token needed.
    try {
        const payload = JSON.parse(atob(response.credential.split('.')[1]));
        userEmail = payload.email || 'unknown';
        clearError('loginError');
        hideLogin();
        loadDashboard();
    } catch (e) {
        console.error('Google credential decode error', e);
        showError('loginError', 'Invalid Google response.');
    }
}

// Logout – simply reload the page to reset state.
function logout() {
    userEmail = null;
    // Optional: revoke token (not required for our simplified flow)
    showLogin();
}

// Dashboard loader – bind navigation & initial view
function loadDashboard() {
    document.getElementById('logoutBtn').addEventListener('click', logout);
    const navButtons = document.querySelectorAll('nav button[data-view]');
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => switchView(btn.dataset.view));
    });
    // Default view
    switchView('leads');
}

// Switch between panels
async function switchView(view) {
    const contentArea = document.getElementById('contentArea');
    contentArea.innerHTML = '';
    switch (view) {
        case 'leads':
            await renderLeadsPanel();
            break;
        case 'followups':
            await renderFollowUpsPanel();
            break;
        case 'workflow':
            await renderWorkflowPanel();
            break;
        default:
            contentArea.textContent = 'Unknown view';
    }
}

// Leads Panel ---------------------------------------------------
async function renderLeadsPanel() {
    const panel = document.createElement('div');
    panel.className = 'panel';
    panel.innerHTML = `<h2>Leads</h2>
        <button id="addLeadBtn">Add New Lead</button>
        <div id="leadsError" class="error"></div>
        <table id="leadsTable"><thead><tr><th>Name</th><th>Contact</th><th>Actions</th></tr></thead><tbody></tbody></table>`;
    document.getElementById('contentArea').appendChild(panel);
    document.getElementById('addLeadBtn').addEventListener('click', showAddLeadModal);
    await loadLeads();
}

async function loadLeads() {
    const tbody = document.querySelector('#leadsTable tbody');
    const errorEl = document.getElementById('leadsError');
    clearError('leadsError');
    const data = await safeFetch('/api/leads');
    if (data.__error) {
        showError('leadsError', data.__error);
        return;
    }
    tbody.innerHTML = '';
    (data.leads || []).forEach(lead => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${lead.name}</td><td>${lead.contact}</td><td><button data-id="${lead.id}" class="deleteLead">Delete</button></td>`;
        tbody.appendChild(tr);
    });
    // Delete handlers
    document.querySelectorAll('.deleteLead').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.target.dataset.id;
            const res = await safeFetch(`/api/leads/${id}`, { method: 'DELETE' });
            if (res.__error) {
                showError('leadsError', res.__error);
            } else {
                await loadLeads();
            }
        });
    });
}

function showAddLeadModal() {
    const name = prompt('Lead Name:');
    if (!name) return;
    const contact = prompt('Contact Info:');
    if (!contact) return;
    addLead({ name, contact });
}

async function addLead(payload) {
    const errorEl = document.getElementById('leadsError');
    clearError('leadsError');
    const res = await safeFetch('/api/leads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (res.__error) {
        showError('leadsError', res.__error);
    } else {
        await loadLeads();
    }
}

// Follow‑Ups Panel ---------------------------------------------
async function renderFollowUpsPanel() {
    const panel = document.createElement('div');
    panel.className = 'panel';
    panel.innerHTML = `<h2>Follow‑Ups</h2>
        <button id="addFollowBtn">Add Follow‑Up</button>
        <div id="followError" class="error"></div>
        <table id="followTable"><thead><tr><th>Lead ID</th><th>Note</th><th>Actions</th></tr></thead><tbody></tbody></table>`;
    document.getElementById('contentArea').appendChild(panel);
    document.getElementById('addFollowBtn').addEventListener('click', showAddFollowModal);
    await loadFollowUps();
}

async function loadFollowUps() {
    const tbody = document.querySelector('#followTable tbody');
    const errorEl = document.getElementById('followError');
    clearError('followError');
    const data = await safeFetch('/api/follow-ups');
    if (data.__error) { showError('followError', data.__error); return; }
    tbody.innerHTML = '';
    (data.follow_ups || []).forEach(fu => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${fu.lead_id}</td><td>${fu.note}</td><td><button data-id="${fu.id}" class="deleteFollow">Delete</button></td>`;
        tbody.appendChild(tr);
    });
    document.querySelectorAll('.deleteFollow').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.target.dataset.id;
            const res = await safeFetch(`/api/follow-ups/${id}`, { method: 'DELETE' });
            if (res.__error) showError('followError', res.__error);
            else await loadFollowUps();
        });
    });
}

function showAddFollowModal() {
    const leadId = prompt('Lead ID:');
    if (!leadId) return;
    const note = prompt('Follow‑Up Note:');
    if (!note) return;
    addFollowUp({ lead_id: leadId, note });
}

async function addFollowUp(payload) {
    const errorEl = document.getElementById('followError');
    clearError('followError');
    const res = await safeFetch('/api/follow-ups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (res.__error) showError('followError', res.__error);
    else await loadFollowUps();
}

// Workflow Logs Panel ------------------------------------------
async function renderWorkflowPanel() {
    const panel = document.createElement('div');
    panel.className = 'panel';
    panel.innerHTML = `<h2>Workflow Logs</h2>
        <div id="workflowError" class="error"></div>
        <table id="workflowTable"><thead><tr><th>Timestamp</th><th>Message</th></tr></thead><tbody></tbody></table>`;
    document.getElementById('contentArea').appendChild(panel);
    await loadWorkflowLogs();
}

async function loadWorkflowLogs() {
    const tbody = document.querySelector('#workflowTable tbody');
    const errorEl = document.getElementById('workflowError');
    clearError('workflowError');
    const data = await safeFetch('/api/workflow/logs');
    if (data.__error) { showError('workflowError', data.__error); return; }
    tbody.innerHTML = '';
    (data.logs || []).forEach(log => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${new Date(log.timestamp).toLocaleString()}</td><td>${log.message}</td>`;
        tbody.appendChild(tr);
    });
}

// Initialise on DOM ready
window.addEventListener('DOMContentLoaded', () => {
    initGoogleSignIn();
});
