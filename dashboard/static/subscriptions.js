let currentSubView = 'newsletters';

async function fetchJSON(url) {
    const res = await fetch(url);
    return res.json();
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

function switchSubView(view) {
    currentSubView = view;
    document.querySelectorAll('.tab').forEach(el => {
        el.classList.toggle('active', el.dataset.view === view);
    });
    document.getElementById('newsletters-view').style.display = view === 'newsletters' ? '' : 'none';
    document.getElementById('services-view').style.display = view === 'services' ? '' : 'none';
}

// --- Newsletters ---

async function loadNewsletters() {
    const data = await fetchJSON('/api/subscriptions/newsletters');
    const tbody = document.getElementById('newsletter-body');

    if (!data.newsletters || data.newsletters.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty">No newsletters detected. Click "Scan Gmail" to find them.</td></tr>';
        return;
    }

    tbody.innerHTML = data.newsletters.map(n => `
        <tr>
            <td>
                <strong>${esc(n.sender_name || n.sender_email)}</strong>
                ${n.sender_name ? `<div style="font-size:12px;color:var(--text-secondary)">${esc(n.sender_email)}</div>` : ''}
            </td>
            <td>${n.email_count}</td>
            <td style="font-size:13px;color:var(--text-secondary)">${esc(n.last_seen || '-')}</td>
            <td style="white-space:nowrap">
                ${n.unsubscribe_url ? `<a href="${esc(n.unsubscribe_url)}" target="_blank" rel="noopener" class="btn" style="font-size:12px;padding:4px 12px;color:var(--danger);text-decoration:none">Unsubscribe</a>` : ''}
                <button class="btn" style="font-size:12px;padding:4px 12px;color:var(--text-secondary)" onclick="hideNewsletter(${n.id})">Hide</button>
            </td>
        </tr>
    `).join('');
}

async function scanNewsletters() {
    showToast('Scanning Gmail for newsletters...');
    await fetch('/api/subscriptions/newsletters/scan', { method: 'POST' });
    let attempts = 0;
    const poll = setInterval(async () => {
        attempts++;
        await loadNewsletters();
        if (attempts > 20) {
            clearInterval(poll);
            showToast('Scan complete');
        }
    }, 3000);
}

async function hideNewsletter(id) {
    await fetch(`/api/subscriptions/newsletters/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hidden: true }),
    });
    loadNewsletters();
}

// --- Services ---

async function loadServices() {
    const data = await fetchJSON('/api/subscriptions/services');
    const tbody = document.getElementById('service-body');
    const totalEl = document.getElementById('service-total');

    if (!data.services || data.services.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">No services added</td></tr>';
        totalEl.innerHTML = '';
        return;
    }

    // Monthly total
    const byCurrency = {};
    for (const s of data.services) {
        if (!s.cost) continue;
        const monthly = s.billing_cycle === 'yearly' ? s.cost / 12 : s.cost;
        const cur = s.currency || 'PLN';
        byCurrency[cur] = (byCurrency[cur] || 0) + monthly;
    }
    const totalParts = Object.entries(byCurrency).map(
        ([cur, total]) => `<span style="margin-right:16px"><strong>${total.toFixed(2)} ${cur}</strong>/mo</span>`
    ).join('');
    totalEl.innerHTML = totalParts ? `<div class="card" style="display:inline-block">${totalParts}</div>` : '';

    tbody.innerHTML = data.services.map(s => `
        <tr>
            <td>
                <strong>${esc(s.name)}</strong>
                ${s.url ? `<div style="font-size:12px"><a href="${esc(s.url)}" target="_blank" rel="noopener" style="color:var(--accent)">${esc(s.url)}</a></div>` : ''}
                ${s.notes ? `<div style="font-size:12px;color:var(--text-secondary)">${esc(s.notes)}</div>` : ''}
            </td>
            <td class="amount">${s.cost != null ? s.cost.toFixed(2) + ' ' + (s.currency || 'PLN') : '-'}</td>
            <td>${s.billing_cycle || '-'}</td>
            <td>${s.renewal_date || '-'}</td>
            <td>
                <button class="btn" style="font-size:12px;padding:4px 12px;color:var(--danger)" onclick="deleteService(${s.id})">Remove</button>
            </td>
        </tr>
    `).join('');
}

async function addService() {
    const name = document.getElementById('svc-name').value.trim();
    if (!name) return;
    const body = {
        name,
        cost: parseFloat(document.getElementById('svc-cost').value) || null,
        currency: document.getElementById('svc-currency').value,
        billing_cycle: document.getElementById('svc-cycle').value,
        renewal_date: document.getElementById('svc-renewal').value || null,
        url: document.getElementById('svc-url').value.trim() || null,
    };
    await fetch('/api/subscriptions/services', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    document.getElementById('svc-name').value = '';
    document.getElementById('svc-cost').value = '';
    document.getElementById('svc-url').value = '';
    document.getElementById('svc-renewal').value = '';
    showToast(`"${name}" added`);
    loadServices();
}

async function deleteService(id) {
    await fetch(`/api/subscriptions/services/${id}`, { method: 'DELETE' });
    loadServices();
}

// --- Init ---

document.addEventListener('DOMContentLoaded', () => {
    loadNewsletters();
    loadServices();
});
