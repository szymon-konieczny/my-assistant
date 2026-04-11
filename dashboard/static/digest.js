let currentDate = '';

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

function urgencyBadge(urgency) {
    const cls = { high: 'status-failed', medium: 'status-running', low: 'status-completed' };
    return `<span class="status-badge ${cls[urgency] || ''}">${urgency}</span>`;
}

function renderSection(title, icon, items) {
    if (!items || items.length === 0) return '';

    const rows = items.map(item => `
        <div class="digest-item">
            <div class="digest-item-header">
                ${urgencyBadge(item.urgency)}
                <strong>${esc(item.subject)}</strong>
            </div>
            <div class="digest-item-meta">${esc(item.sender)}</div>
            <div class="digest-item-summary">${esc(item.summary)}</div>
        </div>
    `).join('');

    return `
        <div class="section">
            <div class="section-header">
                <h2>${icon} ${title}</h2>
                <span style="font-size:13px; color:var(--text-secondary)">${items.length}</span>
            </div>
            <div style="padding:12px 20px">${rows}</div>
        </div>
    `;
}

async function loadDigest(date) {
    const container = document.getElementById('digest-content');
    const url = date ? `/api/digest?date=${date}` : '/api/digest';
    const data = await fetchJSON(url);

    currentDate = data.requested_date;
    document.getElementById('digest-date').value = currentDate;

    if (!data.digest) {
        container.innerHTML = `
            <div class="section">
                <div class="empty">
                    No digest for ${currentDate}.<br>
                    <button class="btn btn-primary" onclick="generateNow()" style="margin-top:12px">Generate Now</button>
                </div>
            </div>
        `;
        return;
    }

    const content = JSON.parse(data.digest.content);
    const emailCount = data.digest.email_count || 0;

    let html = `<div style="font-size:13px; color:var(--text-secondary); margin-bottom:16px;">${emailCount} emails processed</div>`;
    html += renderSection('Action Items', '&#9888;&#65039;', content.action_items);
    html += renderSection('Important', '&#11088;', content.important);
    html += renderSection('FYI', '&#128196;', content.fyi);

    if (!content.action_items?.length && !content.important?.length && !content.fyi?.length) {
        html += '<div class="section"><div class="empty">No notable emails for this day.</div></div>';
    }

    container.innerHTML = html;
}

function onDateChange() {
    const date = document.getElementById('digest-date').value;
    if (date) loadDigest(date);
}

async function generateNow() {
    showToast('Generating digest...');
    const date = document.getElementById('digest-date').value || undefined;
    await fetch('/api/digest/generate' + (date ? `?date=${date}` : ''), { method: 'POST' });

    let attempts = 0;
    const poll = setInterval(async () => {
        attempts++;
        const data = await fetchJSON(`/api/digest?date=${currentDate}`);
        if (data.digest || attempts > 24) {
            clearInterval(poll);
            loadDigest(currentDate);
            showToast(data.digest ? 'Digest ready' : 'Digest generation may still be in progress');
        }
    }, 5000);
}

document.addEventListener('DOMContentLoaded', () => {
    // Default to yesterday
    const now = new Date();
    const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
    const y = yesterday.getFullYear();
    const m = String(yesterday.getMonth() + 1).padStart(2, '0');
    const d = String(yesterday.getDate()).padStart(2, '0');
    document.getElementById('digest-date').value = `${y}-${m}-${d}`;
    loadDigest(`${y}-${m}-${d}`);
});
