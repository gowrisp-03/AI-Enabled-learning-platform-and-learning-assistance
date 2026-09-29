const state = { subject: 'General', questions: [], activity: [], user: null };
const $ = (selector) => document.querySelector(selector);

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Something went wrong');
  return data;
}

function timeAgo(dateString) {
  const diff = Math.max(0, Date.now() - new Date(dateString).getTime());
  const minutes = Math.floor(diff / 60000);
  if (minutes < 2) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function renderActivity() {
  const list = $('#activity-list');
  if (!state.activity.length) {
    list.innerHTML = '<div class="empty-state">Your first question will appear here.</div>';
    return;
  }
  list.innerHTML = state.activity.slice(0, 4).map((item) => `<div class="activity-item"><span class="activity-icon">✦</span><div><strong>${item.label}</strong><p>${item.detail}</p></div><time>${timeAgo(item.created_at)}</time></div>`).join('');
}

function renderLibrary() {
  const list = $('#library-list');
  if (!state.questions.length) {
    list.innerHTML = '<div class="empty-state">No saved questions yet. Ask your first question from Workspace.</div>';
    return;
  }
  list.innerHTML = state.questions.map((item) => `<article class="question-card"><div class="question-meta"><span>${item.subject}</span><time>${timeAgo(item.created_at)}</time></div><h3>${item.question}</h3><div class="answer-preview">${window.marked ? marked.parse(item.answer) : item.answer}</div></article>`).join('');
}

async function loadData() {
  try {
    [state.user, state.questions, state.activity] = await Promise.all([fetchJson('/api/me'), fetchJson('/api/questions'), fetchJson('/api/activity')]);
    const initials = state.user.name.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase();
    $('#user-name').textContent = state.user.name;
    $('#user-avatar').textContent = initials;
    $('#top-avatar').textContent = initials;
    document.querySelector('.welcome h1').innerHTML = `Good morning, ${state.user.name.split(' ')[0]}<span>.</span>`;
    renderActivity();
    renderLibrary();
    $('#progress-questions').textContent = String(state.questions.length).padStart(2, '0');
  } catch (error) {
    $('#activity-list').innerHTML = '<div class="empty-state">Could not connect to the learning service.</div>';
  }
}

$('#logout-button').addEventListener('click', async () => {
  await fetchJson('/api/logout', { method: 'POST' });
  window.location.href = '/login';
});

function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('visible');
  setTimeout(() => toast.classList.remove('visible'), 3000);
}

async function askQuestion() {
  const input = $('#question');
  const button = $('#ask-button');
  const question = input.value.trim();
  if (!question) { input.focus(); return; }
  button.disabled = true;
  button.innerHTML = 'Thinking <span class="spinner">◌</span>';
  try {
    const result = await fetchJson('/api/questions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, subject: state.subject }) });
    input.value = '';
    $('#char-count').textContent = '0 / 500';
    state.questions.unshift({ ...result, created_at: new Date().toISOString() });
    state.activity.unshift({ label: 'Doubt resolved', detail: `${state.subject} · ${question.slice(0, 58)}`, kind: 'spark', created_at: new Date().toISOString() });
    renderActivity(); renderLibrary();
    $('#progress-questions').textContent = String(state.questions.length).padStart(2, '0');
    showToast('Your answer is ready in My library.');
    document.querySelector('[data-view="library"]').click();
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Ask Lumen <span>↗</span>';
  }
}

document.querySelectorAll('.subject').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('.subject').forEach((item) => item.classList.remove('active'));
  button.classList.add('active');
  state.subject = button.textContent.replace('More +', 'General');
}));
document.querySelectorAll('.nav-item').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('.nav-item').forEach((item) => item.classList.remove('active'));
  document.querySelectorAll('.view').forEach((view) => view.classList.remove('active-view'));
  button.classList.add('active');
  $(`#view-${button.dataset.view}`).classList.add('active-view');
}));
$('#view-all').addEventListener('click', () => document.querySelector('[data-view="library"]').click());
$('#ask-button').addEventListener('click', askQuestion);
$('#question').addEventListener('input', (event) => { $('#char-count').textContent = `${event.target.value.length} / 500`; });
$('#question').addEventListener('keydown', (event) => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') askQuestion(); });
loadData();
