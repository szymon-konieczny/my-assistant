let currentProject = null;
let currentView = 'kanban';
let tasks = [];

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

const STATUS_LABELS = { todo: 'To Do', in_progress: 'In Progress', done: 'Done' };
const PRIORITY_CLASSES = { high: 'status-failed', medium: 'status-running', low: 'status-completed' };

// --- Projects ---

async function loadProjects() {
    const data = await fetchJSON('/api/projects');
    const select = document.getElementById('project-select');
    const current = select.value;
    select.innerHTML = '<option value="">Select project...</option>';
    for (const p of data.projects) {
        select.innerHTML += `<option value="${p.id}" ${String(p.id) === current ? 'selected' : ''}>${esc(p.name)}</option>`;
    }
}

function onProjectChange() {
    const id = document.getElementById('project-select').value;
    if (id) {
        currentProject = parseInt(id);
        document.getElementById('project-content').style.display = '';
        document.getElementById('no-project').style.display = 'none';
        loadTasks();
    } else {
        currentProject = null;
        document.getElementById('project-content').style.display = 'none';
        document.getElementById('no-project').style.display = '';
    }
}

function showNewProject() {
    document.getElementById('project-modal').style.display = 'flex';
    document.getElementById('modal-project-name').value = '';
    document.getElementById('modal-project-name').focus();
}

function closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('project-modal').style.display = 'none';
}

async function createProject() {
    const name = document.getElementById('modal-project-name').value.trim();
    if (!name) return;
    const data = await (await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
    })).json();
    closeModal();
    await loadProjects();
    document.getElementById('project-select').value = data.id;
    onProjectChange();
    showToast(`Project "${name}" created`);
}

// --- Tasks ---

async function loadTasks() {
    if (!currentProject) return;
    const data = await fetchJSON(`/api/tasks?project_id=${currentProject}`);
    tasks = data.tasks || [];
    renderCurrentView();
}

async function addTask() {
    if (!currentProject) return;
    const title = document.getElementById('new-task-title').value.trim();
    if (!title) return;
    const priority = document.getElementById('new-task-priority').value;
    const due_date = document.getElementById('new-task-due').value || null;
    await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: currentProject, title, priority, due_date }),
    });
    document.getElementById('new-task-title').value = '';
    document.getElementById('new-task-due').value = '';
    loadTasks();
}

async function updateTask(taskId, updates) {
    await fetch(`/api/tasks/${taskId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
    });
    loadTasks();
}

async function deleteTask(taskId) {
    await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
    loadTasks();
}

// --- Views ---

function switchView(view) {
    currentView = view;
    document.querySelectorAll('.tab').forEach(el => {
        el.classList.toggle('active', el.dataset.view === view);
    });
    document.getElementById('kanban-view').style.display = view === 'kanban' ? '' : 'none';
    document.getElementById('list-view').style.display = view === 'list' ? '' : 'none';
    renderCurrentView();
}

function renderCurrentView() {
    if (currentView === 'kanban') renderKanban();
    else renderList();
}

// --- Kanban ---

function renderKanban() {
    for (const status of ['todo', 'in_progress', 'done']) {
        const col = document.getElementById(`col-${status}`);
        const statusTasks = tasks.filter(t => t.status === status).sort((a, b) => a.position - b.position);
        if (statusTasks.length === 0) {
            col.innerHTML = '<div class="kanban-empty">No tasks</div>';
            continue;
        }
        col.innerHTML = statusTasks.map(t => `
            <div class="kanban-card" draggable="true" data-id="${t.id}"
                 ondragstart="onDragStart(event, ${t.id})">
                <div class="kanban-card-header">
                    <span class="status-badge ${PRIORITY_CLASSES[t.priority] || ''}">${t.priority}</span>
                    ${t.due_date ? `<span class="kanban-due">${t.due_date}</span>` : ''}
                </div>
                <div class="kanban-card-title">${esc(t.title)}</div>
                ${t.description ? `<div class="kanban-card-desc">${esc(t.description)}</div>` : ''}
                <div class="kanban-card-actions">
                    <button onclick="event.stopPropagation(); deleteTask(${t.id})" class="kanban-delete">&times;</button>
                </div>
            </div>
        `).join('');
    }
}

function onDragStart(event, taskId) {
    event.dataTransfer.setData('text/plain', taskId);
    event.dataTransfer.effectAllowed = 'move';
    event.target.classList.add('dragging');
}

function onDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    event.currentTarget.classList.add('drag-over');
}

function onDrop(event, newStatus) {
    event.preventDefault();
    event.currentTarget.classList.remove('drag-over');
    const taskId = parseInt(event.dataTransfer.getData('text/plain'));
    document.querySelectorAll('.dragging').forEach(el => el.classList.remove('dragging'));
    updateTask(taskId, { status: newStatus });
}

// Remove drag-over when leaving
document.addEventListener('dragleave', (e) => {
    if (e.target.classList) e.target.classList.remove('drag-over');
});

// --- List ---

function renderList() {
    const tbody = document.getElementById('task-list-body');
    if (tasks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty">No tasks</td></tr>';
        return;
    }
    tbody.innerHTML = tasks.map(t => `
        <tr>
            <td>${t.status === 'done' ? '<s>' : ''}${esc(t.title)}${t.status === 'done' ? '</s>' : ''}</td>
            <td>
                <select onchange="updateTask(${t.id}, {status: this.value})" style="padding:4px 8px; border:1px solid var(--border); border-radius:4px; font-size:13px;">
                    ${['todo', 'in_progress', 'done'].map(s => `<option value="${s}" ${t.status === s ? 'selected' : ''}>${STATUS_LABELS[s]}</option>`).join('')}
                </select>
            </td>
            <td><span class="status-badge ${PRIORITY_CLASSES[t.priority] || ''}">${t.priority}</span></td>
            <td>${t.due_date || '-'}</td>
        </tr>
    `).join('');
}

// --- Init ---

document.addEventListener('DOMContentLoaded', () => {
    loadProjects();
});
