let currentMonth = '';
let currentTab = 'accountant';

async function fetchJSON(url) {
    const res = await fetch(url);
    return res.json();
}

async function loadAccounts() {
    const data = await fetchJSON('/api/accounts');
    const container = document.getElementById('accounts-list');

    if (!data.accounts || data.accounts.length === 0) {
        container.innerHTML = '<div class="empty">No accounts configured</div>';
        return;
    }

    const allConnected = data.accounts.every(a => a.connected);
    const section = document.getElementById('accounts-section');

    if (allConnected) {
        section.style.display = 'none';
    } else {
        section.style.display = '';
        container.innerHTML = data.accounts.map(acc => `
            <div style="display: flex; align-items: center; gap: 12px; padding: 8px 0;">
                <span class="status-badge ${acc.connected ? 'status-completed' : 'status-failed'}">
                    ${acc.connected ? 'Connected' : 'Not connected'}
                </span>
                <strong>${esc(acc.email)}</strong>
                <span style="color: var(--text-secondary);">(${esc(acc.alias)})</span>
                ${!acc.connected ? `<a href="/oauth/connect/${esc(acc.alias)}" class="btn btn-primary" style="font-size: 12px; padding: 4px 12px;">Connect</a>` : ''}
            </div>
        `).join('');
    }

    // Disable scan button if no accounts connected
    const anyConnected = data.accounts.some(a => a.connected);
    const btn = document.getElementById('scan-btn');
    btn.disabled = !anyConnected;
    if (!anyConnected) btn.title = 'Connect at least one Gmail account first';
}

function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab').forEach(el => {
        el.classList.toggle('active', el.dataset.tab === tab);
    });

    const dbSections = document.querySelectorAll('.db-only');
    const monthSelect = document.getElementById('month-filter');
    const ksefMonth = document.getElementById('ksef-month-filter');

    if (tab === 'ksef') {
        dbSections.forEach(el => el.style.display = 'none');
        monthSelect.style.display = 'none';
        ksefMonth.style.display = '';
        // Default KSeF to previous month
        const now = new Date();
        const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        const y = prev.getFullYear();
        const m = String(prev.getMonth() + 1).padStart(2, '0');
        ksefMonth.value = `${y}-${m}`;
        currentMonth = `${y}-${m}`;
    } else {
        dbSections.forEach(el => el.style.display = '');
        monthSelect.style.display = '';
        ksefMonth.style.display = 'none';
        currentMonth = '';
        monthSelect.value = '';
    }
    loadInvoices(currentMonth);
}

async function loadGrandTotals() {
    const data = await fetchJSON('/api/invoices/grand-total');
    const container = document.getElementById('grand-totals');
    container.innerHTML = '';

    if (!data.totals || data.totals.length === 0) {
        container.innerHTML = '<div class="card"><div class="label">Total</div><div class="value">-</div></div>';
        return;
    }

    for (const t of data.totals) {
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
            <div class="label">${t.currency}</div>
            <div class="value">${formatAmount(t.total)}</div>
            <div class="sub">${t.count} invoice${t.count !== 1 ? 's' : ''}</div>
        `;
        container.appendChild(card);
    }
}

async function loadMonthlyTotals() {
    const data = await fetchJSON('/api/invoices/totals');
    const container = document.getElementById('monthly-totals');

    if (!data.totals || data.totals.length === 0) {
        container.innerHTML = '<div class="empty">No data yet</div>';
        return;
    }

    const byMonth = {};
    for (const t of data.totals) {
        if (!byMonth[t.month]) byMonth[t.month] = [];
        byMonth[t.month].push(t);
    }

    let html = '<div class="monthly-totals">';
    for (const [month, items] of Object.entries(byMonth).sort((a, b) => b[0].localeCompare(a[0]))) {
        const lines = items.map(i => `<div>${formatAmount(i.total)} ${i.currency}</div>`).join('');
        const count = items.reduce((s, i) => s + i.count, 0);
        html += `
            <div class="monthly-total-item${currentMonth === month ? ' active' : ''}" data-month="${month}" onclick="filterMonth('${month}')" style="cursor:pointer">
                <div class="month">${formatMonth(month)}</div>
                <div class="amounts">${lines}</div>
                <div class="count">${count} invoice${count !== 1 ? 's' : ''}</div>
            </div>
        `;
    }
    html += '</div>';
    container.innerHTML = html;

    const select = document.getElementById('month-filter');
    select.innerHTML = '<option value="">All months</option>';
    for (const month of Object.keys(byMonth).sort().reverse()) {
        select.innerHTML += `<option value="${month}">${month}</option>`;
    }
}

async function loadInvoices(month = '') {
    const tbody = document.getElementById('invoice-table-body');
    const thead = document.querySelector('#invoice-table thead tr');

    if (currentTab === 'ksef') {
        thead.innerHTML = `
            <th>Vendor</th>
            <th>NIP</th>
            <th>Invoice #</th>
            <th>Issue Date</th>
            <th>Net</th>
            <th>Gross</th>
            <th>Currency</th>
        `;
        tbody.innerHTML = '<tr><td colspan="7" class="empty">Loading from KSeF...</td></tr>';

        const url = month ? `/api/ksef/invoices?month=${month}` : '/api/ksef/invoices';
        const data = await fetchJSON(url);

        if (data.error) {
            tbody.innerHTML = `<tr><td colspan="7" class="empty">Error: ${esc(data.error)}</td></tr>`;
            return;
        }
        if (!data.invoices || data.invoices.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty">No invoices found</td></tr>';
            return;
        }

        tbody.innerHTML = data.invoices.map(inv => `
            <tr>
                <td>${esc(inv.vendor_name || '-')}</td>
                <td>${esc(inv.vendor_nip || '-')}</td>
                <td>${esc(inv.invoice_number || '-')}</td>
                <td>${esc(inv.issue_date || '-')}</td>
                <td class="amount">${inv.net_amount != null ? formatAmount(inv.net_amount) : '-'}</td>
                <td class="amount">${inv.gross_amount != null ? formatAmount(inv.gross_amount) : '-'}</td>
                <td>${esc(inv.currency || '-')}</td>
            </tr>
        `).join('');
    } else {
        thead.innerHTML = `
            <th>Vendor</th>
            <th>Invoice #</th>
            <th>Sell Date</th>
            <th>Amount</th>
            <th>Currency</th>
            <th>From</th>
            <th>Account</th>
        `;
        const url = month ? `/api/invoices?month=${month}` : '/api/invoices';
        const data = await fetchJSON(url);

        if (!data.invoices || data.invoices.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty">No invoices found</td></tr>';
            return;
        }

        tbody.innerHTML = data.invoices.map(inv => `
            <tr>
                <td>${esc(inv.vendor_name || '-')}</td>
                <td>${esc(inv.invoice_number || '-')}</td>
                <td>${esc(inv.sell_date || '-')}</td>
                <td class="amount">${inv.amount != null ? formatAmount(inv.amount) : '-'}</td>
                <td>${esc(inv.currency || '-')}</td>
                <td>${esc(inv.sender_email || '-')}</td>
                <td>${esc(inv.gmail_account || '-')}</td>
            </tr>
        `).join('');
    }
}

async function loadLastRun() {
    const data = await fetchJSON('/api/status');
    const el = document.getElementById('last-run-info');
    const scanBtn = document.getElementById('scan-btn');
    const cancelBtn = document.getElementById('cancel-btn');

    if (data.last_run) {
        const r = data.last_run;
        const statusClass = `status-${r.status}`;
        const timestamp = formatTimestamp(r.completed_at || r.started_at);
        el.innerHTML = `
            <span class="status-badge ${statusClass}">${r.status}</span>
            ${timestamp} &mdash;
            ${r.invoices_found} invoices, ${r.invoices_polish_skipped} KSeF
        `;

        if (r.status === 'running') {
            scanBtn.disabled = true;
            scanBtn.textContent = 'Scanning...';
            cancelBtn.style.display = '';
        } else {
            scanBtn.disabled = false;
            scanBtn.textContent = 'Run Scan';
            cancelBtn.style.display = 'none';
        }
    } else {
        el.textContent = 'No scans yet';
        cancelBtn.style.display = 'none';
    }
}

async function triggerScan() {
    const btn = document.getElementById('scan-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    cancelBtn.style.display = '';

    try {
        const monthInput = document.getElementById('scan-month').value;
        const body = {};
        if (monthInput) {
            const [year, month] = monthInput.split('-').map(Number);
            const lastDay = new Date(year, month, 0).getDate();
            body.after_date = `${year}-${String(month).padStart(2, '0')}-01`;
            body.before_date = `${year}-${String(month).padStart(2, '0')}-${lastDay}`;
        }
        await fetch('/api/runs/trigger', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        showToast(`Scan started for ${monthInput || 'previous month'}!`);
        pollForCompletion();
    } catch (e) {
        showToast('Error starting scan');
        btn.disabled = false;
        btn.textContent = 'Run Scan';
        cancelBtn.style.display = 'none';
    }
}

async function cancelScan() {
    const cancelBtn = document.getElementById('cancel-btn');
    cancelBtn.disabled = true;
    cancelBtn.textContent = 'Cancelling...';

    try {
        await fetch('/api/runs/cancel', { method: 'POST' });
        showToast('Scan cancelled');
        await loadLastRun();
    } catch (e) {
        showToast('Error cancelling scan');
    } finally {
        cancelBtn.disabled = false;
        cancelBtn.textContent = 'Cancel';
    }
}

async function pollForCompletion() {
    let attempts = 0;
    const poll = setInterval(async () => {
        attempts++;
        await loadLastRun();
        const data = await fetchJSON('/api/status');
        if (data.last_run && data.last_run.status !== 'running') {
            clearInterval(poll);
            await refreshAll();
            if (data.last_run.status === 'cancelled') {
                showToast('Scan was cancelled');
            } else {
                showToast(`Scan completed: ${data.last_run.invoices_found} invoices found`);
            }
        }
        if (attempts > 120) clearInterval(poll);
    }, 5000);
}

function filterMonth(month) {
    // Toggle: clicking the same month deselects it
    if (currentMonth === month) month = '';
    currentMonth = month;
    document.getElementById('month-filter').value = month;
    document.querySelectorAll('.monthly-total-item').forEach(el => {
        el.classList.toggle('active', el.dataset.month === month);
    });
    loadInvoices(month);
}

function onMonthFilterChange(e) {
    filterMonth(e.target.value);
}

function onKsefMonthChange(e) {
    currentMonth = e.target.value;
    loadInvoices(currentMonth);
}

function formatTimestamp(ts) {
    if (!ts) return '';
    const d = new Date(ts.includes('T') || ts.includes('+') ? ts : ts + 'Z');
    if (isNaN(d)) return ts;
    return d.toLocaleString('sv-SE', { dateStyle: 'short', timeStyle: 'short' });
}

function formatMonth(ym) {
    const [y, m] = ym.split('-');
    const d = new Date(Number(y), Number(m) - 1);
    return d.toLocaleString('en-US', { month: 'long', year: 'numeric' });
}

function formatAmount(num) {
    return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 4000);
}

async function refreshAll() {
    await Promise.all([
        loadAccounts(),
        loadGrandTotals(),
        loadMonthlyTotals(),
        loadInvoices(currentMonth),
        loadLastRun(),
    ]);

    // Show toast if just connected
    const params = new URLSearchParams(window.location.search);
    if (params.get('connected')) {
        showToast(`Account "${params.get('connected')}" connected successfully!`);
        window.history.replaceState({}, '', '/');
    }
    if (params.get('error')) {
        showToast('OAuth connection failed. Please try again.');
        window.history.replaceState({}, '', '/');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Default scan month to previous month
    const now = new Date();
    const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const y = prev.getFullYear();
    const m = String(prev.getMonth() + 1).padStart(2, '0');
    document.getElementById('scan-month').value = `${y}-${m}`;
    refreshAll();
});
