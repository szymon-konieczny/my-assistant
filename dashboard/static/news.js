let currentCategory = '';
let currentDate = '';
let selectedIndex = -1;

async function fetchJSON(url) {
    const res = await fetch(url);
    return res.json();
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function renderMarkdown(text) {
    return text
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/^/, '<p>').replace(/$/, '</p>');
}

function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 4000);
}

function formatDate(ts) {
    if (!ts) return '';
    const d = new Date(ts.includes('T') || ts.includes('+') ? ts : ts + 'Z');
    if (isNaN(d)) return ts;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// --- Categories ---

async function loadCategories() {
    const data = await fetchJSON('/api/news/categories');
    const tabs = document.getElementById('category-tabs');
    tabs.innerHTML = '<button class="tab active" data-cat="" onclick="filterCategory(\'\')">All</button>';

    for (const cat of data.categories) {
        tabs.innerHTML += `<button class="tab" data-cat="${cat.id}" onclick="filterCategory('${cat.id}')">${esc(cat.name)}</button>`;
    }

    const settingsContainer = document.getElementById('categories-settings');
    if (data.categories.length === 0) {
        settingsContainer.innerHTML = '<div class="empty" style="padding:16px">No categories configured</div>';
        return;
    }

    settingsContainer.innerHTML = data.categories.map(cat => `
        <div style="display:flex; justify-content:space-between; align-items:flex-start; padding:8px 0; border-bottom:1px solid var(--border);">
            <div>
                <strong>${esc(cat.name)}</strong>
                <div style="font-size:12px; color:var(--text-secondary); margin-top:2px;">
                    ${cat.feeds.map(f => esc(f.name)).join(', ')}
                </div>
            </div>
            <button class="btn" style="font-size:12px; padding:4px 12px; color:var(--danger);" onclick="deleteCategory(${cat.id})">Remove</button>
        </div>
    `).join('');
}

function filterCategory(catId) {
    currentCategory = catId;
    document.querySelectorAll('#category-tabs .tab').forEach(el => {
        el.classList.toggle('active', el.dataset.cat === String(catId));
    });
    selectedIndex = -1;
    loadArticles();
    document.getElementById('detail-panel').innerHTML = '<div class="empty">Select an article to read</div>';
}

async function addCategory() {
    const name = document.getElementById('new-cat-name').value.trim();
    const feedsStr = document.getElementById('new-cat-feeds').value.trim();
    if (!name || !feedsStr) return;

    const feeds = feedsStr.split(',').map(url => ({
        name: url.trim().replace(/^https?:\/\/(www\.)?/, '').split('/')[0],
        feed_url: url.trim(),
    }));

    await fetch('/api/news/categories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, feeds }),
    });

    document.getElementById('new-cat-name').value = '';
    document.getElementById('new-cat-feeds').value = '';
    showToast(`Category "${name}" added`);
    loadCategories();
}

async function deleteCategory(id) {
    await fetch(`/api/news/categories/${id}`, { method: 'DELETE' });
    showToast('Category removed');
    if (String(currentCategory) === String(id)) currentCategory = '';
    loadCategories();
    loadArticles();
}

// --- Articles ---

async function loadArticles() {
    const container = document.getElementById('articles-list');
    let url = '/api/news?date=' + currentDate;
    if (currentCategory) url += `&category_id=${currentCategory}`;
    const data = await fetchJSON(url);

    if (!data.articles || data.articles.length === 0) {
        container.innerHTML = '<div class="section"><div class="empty">No articles yet. Click "Fetch Now" to load news.</div></div>';
        return;
    }

    window._articles = data.articles;

    container.innerHTML = data.articles.map((a, i) => `
        <article class="news-article${i === selectedIndex ? ' active' : ''}" onclick="selectArticle(${i})" style="cursor:pointer">
            <div class="news-meta">
                <span class="news-source">${esc(a.source_name || '')}</span>
                <span class="news-date">${formatDate(a.published_at)}</span>
            </div>
            <h3 class="news-title">${esc(a.title)}</h3>
        </article>
    `).join('');
}

async function selectArticle(index) {
    selectedIndex = index;
    const a = window._articles[index];
    if (!a) return;

    // Highlight active article
    document.querySelectorAll('.news-article').forEach((el, i) => {
        el.classList.toggle('active', i === index);
    });

    const panel = document.getElementById('detail-panel');
    const hasSummary = a.summary && a.summary.length > 10;
    panel.innerHTML = `
        <div class="detail-header">
            <h3>${esc(a.title)}</h3>
        </div>
        <div class="detail-meta">
            <span>${esc(a.source_name || '')}</span>
            <span>${formatDate(a.published_at)}</span>
            ${a.source_url ? `<a href="${esc(a.source_url)}" target="_blank" rel="noopener">Open article</a>` : ''}
        </div>
        <div class="detail-body">
            ${hasSummary ? `<p>${esc(a.summary)}</p>` : ''}
            <p style="color:var(--text-secondary)">Generating detailed summary...</p>
        </div>
    `;

    // Fetch extended summary (cached after first generation)
    try {
        const data = await fetchJSON(`/api/news/${a.id}/detail`);
        if (selectedIndex !== index) return;

        const body = panel.querySelector('.detail-body');
        const detail = data.article;
        if (detail && detail.extended_summary) {
            body.innerHTML = renderMarkdown(detail.extended_summary);
        } else if (hasSummary) {
            body.innerHTML = `<p>${esc(a.summary)}</p>`;
        } else {
            body.innerHTML = '<p style="color:var(--text-secondary)">Could not generate summary for this article.</p>';
        }
    } catch (e) {
        if (selectedIndex !== index) return;
        panel.querySelector('.detail-body').innerHTML =
            hasSummary ? `<p>${esc(a.summary)}</p>` : '<p style="color:var(--text-secondary)">Failed to load summary.</p>';
    }
}

// --- Actions ---

async function fetchNow() {
    showToast('Fetching news...');
    await fetch('/api/news/fetch', { method: 'POST' });
    let attempts = 0;
    const poll = setInterval(async () => {
        attempts++;
        const data = await fetchJSON('/api/news?limit=1');
        if ((data.articles && data.articles.length > 0) || attempts > 12) {
            clearInterval(poll);
            loadArticles();
            showToast('News updated');
        }
    }, 3000);
}

function toggleSettings() {
    const panel = document.getElementById('settings-panel');
    panel.style.display = panel.style.display === 'none' ? '' : 'none';
}

async function showSummary() {
    const modal = document.getElementById('summary-modal');
    const content = document.getElementById('summary-content');
    modal.style.display = 'flex';
    content.innerHTML = '<div style="color:var(--text-secondary)">Generating summary...</div>';

    const url = currentCategory ? `/api/news/summarize?category_id=${currentCategory}` : '/api/news/summarize';
    const res = await fetch(url, { method: 'POST' });
    const data = await res.json();

    content.innerHTML = data.summary
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/^##\s+(.+)$/gm, '<h3>$1</h3>')
        .replace(/^[-•]\s+(.+)$/gm, '<li>$1</li>')
        .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
        .replace(/\n\n/g, '<br><br>')
        .replace(/\n/g, '<br>');
}

function closeSummary(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('summary-modal').style.display = 'none';
}

function onNewsDateChange() {
    currentDate = document.getElementById('news-date').value;
    selectedIndex = -1;
    document.getElementById('detail-panel').innerHTML = '<div class="empty">Select an article to read</div>';
    loadArticles();
}

// --- Init ---

document.addEventListener('DOMContentLoaded', () => {
    // Default to yesterday
    const now = new Date();
    const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
    currentDate = yesterday.toISOString().split('T')[0];
    document.getElementById('news-date').value = currentDate;
    loadCategories();
    loadArticles();
});
