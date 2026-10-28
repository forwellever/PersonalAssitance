/**
 * FocusFlow Client Application Logic
 * Supports Multi-User personal isolation and Email + OTP authentication.
 */

const DEFAULT_CATEGORIES = [
  { id: 1, name: '報告', color: 'indigo' },
  { id: 2, name: '簡報', color: 'rose' },
  { id: 3, name: '資料分析', color: 'amber' },
  { id: 4, name: '系統測試', color: 'emerald' },
  { id: 5, name: '其他', color: 'slate' }
];

let currentTab = 'dashboard';
let state = {
  currentUser: null,
  authToken: localStorage.getItem('focusflow_token') || '',
  tasks: [],
  ideas: [],
  categories: [...DEFAULT_CATEGORIES],
  ideaFilter: 'all', // 'all' or 'starred'
  businessLogs: [],
  stats: {},
  currentAnalysis: null,
  selectedIdeaColor: '#fef3c7'
};

// Web Speech Recognition
let recognition = null;
let isRecording = false;
let otpCooldownTimer = null;

document.addEventListener('DOMContentLoaded', () => {
  checkAuthAndInit();
});

// ----------------- Auth Management -----------------
async function authFetch(url, options = {}) {
  options.headers = options.headers || {};
  if (state.authToken) {
    options.headers['Authorization'] = `Bearer ${state.authToken}`;
  }

  const res = await fetch(url, options);
  if (res.status === 401) {
    localStorage.removeItem('focusflow_token');
    state.authToken = '';
    state.currentUser = null;
    showLoginModal();
    showToast('登入階段已逾期或無效，請重新登入', 'warning');
    throw new Error('Unauthorized');
  }
  return res;
}

function showLoginModal() {
  document.getElementById('login-modal').classList.remove('hidden');
  document.getElementById('user-profile-widget').classList.add('hidden');
}

function hideLoginModal() {
  document.getElementById('login-modal').classList.add('hidden');
  document.getElementById('user-profile-widget').classList.remove('hidden');
}

async function checkAuthAndInit() {
  initSpeechRecognition();
  const savedToken = localStorage.getItem('focusflow_token');
  if (!savedToken) {
    showLoginModal();
    return;
  }

  state.authToken = savedToken;
  try {
    const res = await authFetch('/api/auth/me');
    const json = await res.json();
    if (json.success && json.user) {
      state.currentUser = json.user;
      updateUserProfileUI(json.user);
      hideLoginModal();
      refreshData();
      return;
    }
  } catch (err) {
    console.warn('Auth check failed:', err);
  }

  showLoginModal();
}

function updateUserProfileUI(user) {
  const emailEl = document.getElementById('user-email-display');
  const initialEl = document.getElementById('user-avatar-initial');
  if (emailEl) emailEl.innerText = user.email || 'User';
  if (initialEl) initialEl.innerText = (user.email || 'U')[0].toUpperCase();
}

async function handleSendOtp() {
  const emailInput = document.getElementById('login-input-email');
  const email = emailInput.value.trim();
  if (!email || !email.includes('@')) {
    showToast('請輸入正確的電子信箱 (Email)', 'warning');
    emailInput.focus();
    return;
  }

  const btn = document.getElementById('btn-send-otp');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 發送中...';

  try {
    const res = await fetch('/api/auth/send-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email })
    });
    const json = await res.json();
    if (json.success) {
      showToast(json.message || '動態確認碼已發送！', 'success');
      
      // 開發/測試模式下，直接顯示產生的確認碼以便立即登入
      if (json.dev_code) {
        document.getElementById('dev-otp-hint').classList.remove('hidden');
        document.getElementById('dev-otp-code').innerText = json.dev_code;
      } else {
        document.getElementById('dev-otp-hint').classList.add('hidden');
      }

      // 60 秒倒數計時防重複點擊
      let countdown = 60;
      clearInterval(otpCooldownTimer);
      btn.innerText = `重新發送 (${countdown}s)`;
      otpCooldownTimer = setInterval(() => {
        countdown--;
        if (countdown <= 0) {
          clearInterval(otpCooldownTimer);
          btn.disabled = false;
          btn.innerText = '發送確認碼';
        } else {
          btn.innerText = `重新發送 (${countdown}s)`;
        }
      }, 1000);

      document.getElementById('login-input-code').focus();
    } else {
      btn.disabled = false;
      btn.innerText = '發送確認碼';
      showToast(json.error || '發送失敗，請稍後重試', 'error');
    }
  } catch (err) {
    btn.disabled = false;
    btn.innerText = '發送確認碼';
    showToast('發送失敗：' + err.message, 'error');
  }
}

function autoFillOtp() {
  const code = document.getElementById('dev-otp-code').innerText.trim();
  if (code) {
    document.getElementById('login-input-code').value = code;
    showToast('已為您帶入確認碼！', 'info');
  }
}

async function handleVerifyAndLogin() {
  const email = document.getElementById('login-input-email').value.trim();
  const code = document.getElementById('login-input-code').value.trim();

  if (!email || !code) {
    showToast('請輸入 Email 與 6 位數確認碼', 'warning');
    return;
  }

  const btn = document.getElementById('btn-login-submit');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 驗證登入中...';

  try {
    const res = await fetch('/api/auth/verify-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, code })
    });
    const json = await res.json();
    if (json.success && json.token) {
      state.authToken = json.token;
      state.currentUser = json.user;
      localStorage.setItem('focusflow_token', json.token);
      
      updateUserProfileUI(json.user);
      hideLoginModal();
      showToast(`登入成功！歡迎回來，${json.user.email}`, 'success');

      document.getElementById('login-input-code').value = '';
      document.getElementById('dev-otp-hint').classList.add('hidden');

      await refreshData();
    } else {
      showToast(json.error || '驗證失敗，請確認確認碼是否正確', 'error');
    }
  } catch (err) {
    showToast('登入失敗：' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-arrow-right-to-bracket"></i> 驗證並登入系統';
  }
}

async function logout() {
  if (!confirm('確定要登出目前帳號嗎？')) return;
  try {
    if (state.authToken) {
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${state.authToken}` }
      });
    }
  } catch (e) {
    console.warn(e);
  }

  localStorage.removeItem('focusflow_token');
  state.authToken = '';
  state.currentUser = null;
  state.tasks = [];
  state.ideas = [];
  state.businessLogs = [];

  showLoginModal();
  showToast('您已安全登出系統', 'info');
}

// ----------------- Tab Navigation -----------------
function switchTab(tabName) {
  currentTab = tabName;
  document.querySelectorAll('.tab-view').forEach(el => el.classList.add('hidden'));
  const targetView = document.getElementById(`view-${tabName}`);
  if (targetView) targetView.classList.remove('hidden');

  document.querySelectorAll('.nav-tab').forEach(btn => btn.classList.remove('active-tab'));
  const activeBtn = document.getElementById(`tab-btn-${tabName}`);
  if (activeBtn) activeBtn.classList.add('active-tab');

  if (tabName === 'tasks') renderTasks();
  else if (tabName === 'ideas') renderIdeas();
  else if (tabName === 'business') renderBusinessLogs();
  else if (tabName === 'dashboard') loadStats();
}

function triggerQuickVoice() {
  switchTab('business');
  if (!isRecording) {
    toggleSpeechRecognition();
  }
}

// ----------------- Global Refresh -----------------
async function refreshData() {
  if (!state.authToken) return;
  await Promise.all([
    loadStats(),
    loadCategories(),
    loadTasks(),
    loadIdeas(),
    loadBusinessLogs()
  ]);
  showToast('個人任務與資料已同步', 'info');
}

async function loadStats() {
  try {
    const res = await authFetch('/api/stats');
    const json = await res.json();
    if (json.success) {
      state.stats = json.data;
      document.getElementById('stat-pending-tasks').innerText = json.data.pending_tasks || 0;
      document.getElementById('stat-completed-tasks').innerText = json.data.completed_tasks || 0;
      document.getElementById('stat-total-ideas').innerText = json.data.total_ideas || 0;
      document.getElementById('stat-starred-ideas').innerText = json.data.starred_ideas || 0;
      document.getElementById('stat-scheduled-meetings').innerText = json.data.scheduled_meetings || 0;
    }
  } catch (err) {
    console.error('Failed to load stats:', err);
  }
}

// ----------------- Categories Management -----------------
async function loadCategories() {
  try {
    const res = await authFetch('/api/categories');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    if (json.success && Array.isArray(json.data) && json.data.length > 0) {
      state.categories = json.data;
    } else {
      fallbackCategories();
    }
  } catch (err) {
    console.warn('API /api/categories 載入提示，啟用備援預設:', err);
    fallbackCategories();
  }
  populateCategoryDropdowns();
  renderCategoryList();
}

function fallbackCategories() {
  if (!state.categories || state.categories.length === 0) {
    state.categories = [...DEFAULT_CATEGORIES];
  }
  const existingNames = new Set(state.categories.map(c => c.name));
  if (state.tasks && state.tasks.length > 0) {
    state.tasks.forEach(t => {
      if (t.category && !existingNames.has(t.category)) {
        existingNames.add(t.category);
        state.categories.push({ id: Date.now() + Math.random(), name: t.category, color: 'indigo' });
      }
    });
  }
}

function populateCategoryDropdowns() {
  const filterSelect = document.getElementById('task-filter-category');
  const taskInputSelect = document.getElementById('task-input-category');
  const convertSelect = document.getElementById('convert-task-category');

  const currentFilter = filterSelect.value;
  filterSelect.innerHTML = '<option value="all">所有類別</option>';
  taskInputSelect.innerHTML = '';
  if (convertSelect) convertSelect.innerHTML = '';

  state.categories.forEach(cat => {
    const optFilter = document.createElement('option');
    optFilter.value = cat.name;
    optFilter.textContent = cat.name;
    filterSelect.appendChild(optFilter);

    const optInput = document.createElement('option');
    optInput.value = cat.name;
    optInput.textContent = cat.name;
    taskInputSelect.appendChild(optInput);

    if (convertSelect) {
      const optConv = document.createElement('option');
      optConv.value = cat.name;
      optConv.textContent = cat.name;
      convertSelect.appendChild(optConv);
    }
  });

  if (state.categories.some(c => c.name === currentFilter)) {
    filterSelect.value = currentFilter;
  } else {
    filterSelect.value = 'all';
  }
}

function openCategoryModal() {
  document.getElementById('category-modal').classList.remove('hidden');
  renderCategoryList();
}

function closeCategoryModal() {
  document.getElementById('category-modal').classList.add('hidden');
}

function renderCategoryList() {
  const container = document.getElementById('category-list-container');
  if (!container) return;
  container.innerHTML = '';

  const colorBadges = {
    indigo: 'bg-indigo-100 text-indigo-700 border-indigo-200',
    rose: 'bg-rose-100 text-rose-700 border-rose-200',
    amber: 'bg-amber-100 text-amber-700 border-amber-200',
    emerald: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    purple: 'bg-purple-100 text-purple-700 border-purple-200',
    cyan: 'bg-cyan-100 text-cyan-700 border-cyan-200',
    slate: 'bg-slate-100 text-slate-700 border-slate-200'
  };

  state.categories.forEach(cat => {
    const row = document.createElement('div');
    row.className = "flex items-center justify-between p-2.5 bg-white border border-slate-200 rounded-xl text-xs";
    const badgeClass = colorBadges[cat.color] || colorBadges['slate'];
    const taskCount = state.tasks.filter(t => t.category === cat.name).length;

    row.innerHTML = `
      <div class="flex items-center gap-2">
        <span class="px-2.5 py-0.5 rounded-md font-semibold border ${badgeClass}">${escapeHtml(cat.name)}</span>
        <span class="text-slate-400 text-[11px]">(${taskCount} 項任務)</span>
      </div>
      <div class="flex items-center gap-1.5">
        <button onclick="editCategory(${cat.id}, '${escapeHtml(cat.name)}', '${cat.color}')" class="px-2 py-1 text-slate-500 hover:text-indigo-600 hover:bg-slate-50 rounded transition">
          <i class="fa-solid fa-pen"></i> 修改
        </button>
        <button onclick="deleteCategory(${cat.id}, '${escapeHtml(cat.name)}')" class="px-2 py-1 text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded transition">
          <i class="fa-solid fa-trash-can"></i> 刪除
        </button>
      </div>
    `;
    container.appendChild(row);
  });
}

async function saveNewCategory() {
  const nameInput = document.getElementById('cat-new-name');
  const colorSelect = document.getElementById('cat-new-color');
  const name = nameInput.value.trim();
  const color = colorSelect.value;

  if (!name) {
    showToast('請輸入類別名稱', 'warning');
    return;
  }

  try {
    const res = await authFetch('/api/categories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, color })
    });
    const json = await res.json();
    if (json.success) {
      showToast(`已成功建立「${name}」類別`, 'success');
      nameInput.value = '';
      await loadCategories();
      renderTasks();
    } else {
      showToast(json.error || '新增失敗', 'error');
    }
  } catch (err) {
    showToast('新增失敗：' + err.message, 'error');
  }
}

async function editCategory(id, currentName, currentColor) {
  const newName = prompt('請輸入修改後的類別名稱：', currentName);
  if (!newName || newName.trim() === '' || newName.trim() === currentName) return;

  try {
    const res = await authFetch(`/api/categories/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName.trim(), color: currentColor })
    });
    const json = await res.json();
    if (json.success) {
      showToast(`類別名稱已修改為「${newName.trim()}」`, 'success');
      await loadCategories();
      await loadTasks();
    } else {
      showToast(json.error || '修改失敗', 'error');
    }
  } catch (err) {
    showToast('修改失敗：' + err.message, 'error');
  }
}

async function deleteCategory(id, name) {
  if (!confirm(`確定要刪除類別「${name}」嗎？\n該類別下的任務將自動轉移至「其他」。`)) return;

  try {
    const res = await authFetch(`/api/categories/${id}`, { method: 'DELETE' });
    const json = await res.json();
    if (json.success) {
      showToast(`類別「${name}」已刪除`, 'info');
      await loadCategories();
      await loadTasks();
    } else {
      showToast(json.error || '刪除失敗', 'error');
    }
  } catch (err) {
    showToast('刪除失敗：' + err.message, 'error');
  }
}

// ----------------- A. Tasks Management -----------------
async function loadTasks() {
  try {
    const res = await authFetch('/api/tasks');
    const json = await res.json();
    if (json.success) {
      state.tasks = json.data;
      renderTasks();
    }
  } catch (err) {
    console.error('Failed to load tasks:', err);
  }
}

function calculateRecommendedProgress(createdAt, dueDate) {
  if (!dueDate) return null;
  const now = new Date().getTime();
  const start = createdAt ? new Date(createdAt).getTime() : (new Date(dueDate).getTime() - 7 * 24 * 3600 * 1000);
  const due = new Date(dueDate).getTime();

  if (due <= start) {
    return { percentage: 100, isOverdue: now > due, barColor: 'bg-rose-500' };
  }

  if (now <= start) {
    return { percentage: 0, isOverdue: false, barColor: 'bg-cyan-500' };
  }

  if (now >= due) {
    return { percentage: 100, isOverdue: true, barColor: 'bg-rose-500' };
  }

  const elapsed = now - start;
  const total = due - start;
  const percent = Math.min(100, Math.max(0, Math.round((elapsed / total) * 100)));
  return { percentage: percent, isOverdue: false, barColor: 'bg-cyan-500' };
}

function renderTasks() {
  const filterCat = document.getElementById('task-filter-category').value;
  const filtered = filterCat === 'all' 
    ? state.tasks 
    : state.tasks.filter(t => t.category === filterCat);

  const columns = {
    pending: document.getElementById('column-pending'),
    in_progress: document.getElementById('column-in_progress'),
    review: document.getElementById('column-review'),
    completed: document.getElementById('column-completed')
  };

  const counts = { pending: 0, in_progress: 0, review: 0, completed: 0 };
  Object.values(columns).forEach(col => col.innerHTML = '');

  filtered.forEach(task => {
    const status = task.status || 'pending';
    if (counts[status] !== undefined) counts[status]++;

    const colEl = columns[status] || columns.pending;
    colEl.appendChild(createTaskCard(task));
  });

  Object.keys(counts).forEach(k => {
    const badge = document.getElementById(`count-${k}`);
    if (badge) badge.innerText = counts[k];
  });
}

function createTaskCard(task) {
  const card = document.createElement('div');
  card.className = "task-card bg-white p-4 rounded-xl border border-slate-200/80 shadow-sm space-y-3 cursor-default";

  const catObj = state.categories.find(c => c.name === task.category);
  const colorMap = {
    indigo: "bg-indigo-50 text-indigo-700 border-indigo-100",
    rose: "bg-rose-50 text-rose-700 border-rose-100",
    amber: "bg-amber-50 text-amber-700 border-amber-100",
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-100",
    purple: "bg-purple-50 text-purple-700 border-purple-100",
    cyan: "bg-cyan-50 text-cyan-700 border-cyan-100",
    slate: "bg-slate-50 text-slate-700 border-slate-200"
  };
  const catClass = (catObj && colorMap[catObj.color]) || "bg-indigo-50 text-indigo-700 border-indigo-100";

  const priorityIcons = {
    urgent: '<span class="text-xs text-rose-600 font-bold"><i class="fa-solid fa-fire"></i> 緊急</span>',
    high: '<span class="text-xs text-orange-500 font-bold"><i class="fa-solid fa-angles-up"></i> 高</span>',
    medium: '<span class="text-xs text-amber-500 font-bold"><i class="fa-solid fa-angle-up"></i> 中</span>',
    low: '<span class="text-xs text-emerald-500 font-bold"><i class="fa-solid fa-angle-down"></i> 低</span>'
  };

  let dueHtml = '';
  if (task.due_date) {
    const dueDate = new Date(task.due_date);
    const isOverdue = dueDate < new Date() && task.status !== 'completed';
    dueHtml = `
      <div class="text-[11px] ${isOverdue ? 'text-rose-600 font-bold' : 'text-slate-400'} flex items-center gap-1">
        <i class="fa-regular fa-clock"></i> 截止：${task.due_date.replace('T', ' ')} ${isOverdue ? '(已逾期)' : ''}
      </div>
    `;
  }

  const statusFlow = ['pending', 'in_progress', 'review', 'completed'];
  const currentIndex = statusFlow.indexOf(task.status);
  const nextStatus = currentIndex < statusFlow.length - 1 ? statusFlow[currentIndex + 1] : null;
  const prevStatus = currentIndex > 0 ? statusFlow[currentIndex - 1] : null;

  const rec = calculateRecommendedProgress(task.created_at, task.due_date);

  card.innerHTML = `
    <div class="flex items-start justify-between gap-2">
      <span class="text-[10px] font-bold px-2 py-0.5 rounded border ${catClass}">${escapeHtml(task.category)}</span>
      <div class="flex items-center gap-1.5">
        ${priorityIcons[task.priority] || ''}
        <button onclick="editTask(${task.id})" class="text-slate-400 hover:text-slate-600 text-xs p-1" title="編輯詳情"><i class="fa-solid fa-pen"></i></button>
        <button onclick="deleteTask(${task.id})" class="text-slate-400 hover:text-rose-600 text-xs p-1" title="刪除任務"><i class="fa-solid fa-trash-can"></i></button>
      </div>
    </div>

    <div>
      <h4 class="font-bold text-slate-800 text-sm leading-snug">${escapeHtml(task.title)}</h4>
      ${task.description ? `<p class="text-xs text-slate-500 mt-1 line-clamp-2">${escapeHtml(task.description)}</p>` : ''}
    </div>

    ${dueHtml}

    <!-- 1. 實際進度 Bar (可直接拖拉即時調整) -->
    <div class="space-y-1 bg-slate-50/80 p-2 rounded-xl border border-slate-200/60">
      <div class="flex justify-between items-center text-[11px] font-semibold text-slate-700">
        <span class="flex items-center gap-1"><i class="fa-solid fa-sliders text-indigo-500"></i> 實際進度 (滑動調整)</span>
        <span id="progress-val-${task.id}" class="text-indigo-600 font-bold">${task.progress}%</span>
      </div>
      <input type="range" min="0" max="100" value="${task.progress}"
        oninput="onDragProgress(${task.id}, this.value)"
        onchange="quickUpdateProgress(${task.id}, this.value)"
        class="w-full accent-indigo-600 cursor-pointer h-2 bg-slate-200 rounded-lg appearance-none">
    </div>

    <!-- 2. 建議進度 Bar (依 Due Date 時間線性回推) -->
    ${rec ? `
      <div class="space-y-1 bg-cyan-50/50 p-2 rounded-xl border border-cyan-100/70 text-[11px]">
        <div class="flex justify-between items-center font-medium text-slate-600">
          <span class="flex items-center gap-1 text-cyan-900 font-semibold"><i class="fa-solid fa-bullseye text-cyan-600"></i> 建議進度 (時間回推)</span>
          <span class="font-bold text-cyan-700">${rec.percentage}%</span>
        </div>
        <div class="w-full bg-slate-200/80 rounded-full h-1.5 overflow-hidden">
          <div class="${rec.barColor} h-1.5 rounded-full transition-all" style="width: ${rec.percentage}%"></div>
        </div>
        <div class="flex items-center justify-between pt-0.5 text-[10px]">
          ${task.progress >= rec.percentage 
            ? `<span class="text-emerald-600 font-bold flex items-center gap-0.5"><i class="fa-solid fa-check"></i> 進度領先/正常 (+${task.progress - rec.percentage}%)</span>` 
            : `<span class="text-rose-600 font-bold flex items-center gap-0.5"><i class="fa-solid fa-triangle-exclamation"></i> 進度落後 (${task.progress - rec.percentage}%)</span>`}
          <span class="text-slate-400 text-[9px]">${rec.isOverdue ? '⚠️ 已屆截止日' : '時序回推'}</span>
        </div>
      </div>
    ` : ''}

    <!-- Quick Status Transition Buttons -->
    <div class="flex justify-between items-center pt-2 border-t border-slate-100 text-xs">
      ${prevStatus ? `<button onclick="updateTaskStatus(${task.id}, '${prevStatus}')" class="text-slate-400 hover:text-slate-600 flex items-center gap-1"><i class="fa-solid fa-arrow-left"></i> 上一階</button>` : '<span></span>'}
      ${nextStatus ? `<button onclick="updateTaskStatus(${task.id}, '${nextStatus}')" class="font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1">推向下一階 <i class="fa-solid fa-arrow-right"></i></button>` : '<span class="text-emerald-600 font-bold"><i class="fa-solid fa-check"></i> 完成</span>'}
    </div>
  `;
  return card;
}

function onDragProgress(taskId, value) {
  const el = document.getElementById(`progress-val-${taskId}`);
  if (el) el.innerText = `${value}%`;
}

async function quickUpdateProgress(taskId, value) {
  const val = parseInt(value, 10);
  const task = state.tasks.find(t => t.id === taskId);
  if (!task) return;

  let newStatus = task.status;
  if (val === 100 && task.status !== 'completed') {
    newStatus = 'completed';
  } else if (val < 100 && task.status === 'completed') {
    newStatus = 'in_progress';
  }

  try {
    await authFetch(`/api/tasks/${taskId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ progress: val, status: newStatus })
    });
    task.progress = val;
    task.status = newStatus;
    showToast(`任務進度已更新為 ${val}%`, 'info');
    renderTasks();
    loadStats();
  } catch (err) {
    showToast('更新進度失敗：' + err.message, 'error');
  }
}

function openTaskModal(editData = null) {
  document.getElementById('task-modal').classList.remove('hidden');
  populateCategoryDropdowns();

  if (editData) {
    document.getElementById('task-modal-title').innerText = '編輯工作任務';
    document.getElementById('task-edit-id').value = editData.id;
    document.getElementById('task-input-title').value = editData.title;
    document.getElementById('task-input-category').value = editData.category;
    document.getElementById('task-input-priority').value = editData.priority;
    document.getElementById('task-input-duedate').value = editData.due_date || '';
    document.getElementById('task-input-progress').value = editData.progress;
    document.getElementById('task-progress-val').innerText = editData.progress;
    document.getElementById('task-input-desc').value = editData.description || '';
  } else {
    document.getElementById('task-modal-title').innerText = '新增工作任務';
    document.getElementById('task-edit-id').value = '';
    document.getElementById('task-input-title').value = '';
    document.getElementById('task-input-priority').value = 'medium';
    document.getElementById('task-input-duedate').value = '';
    document.getElementById('task-input-progress').value = '0';
    document.getElementById('task-progress-val').innerText = '0';
    document.getElementById('task-input-desc').value = '';
  }
}

function closeTaskModal() {
  document.getElementById('task-modal').classList.add('hidden');
}

async function saveTaskFromModal() {
  const editId = document.getElementById('task-edit-id').value;
  const title = document.getElementById('task-input-title').value.trim();
  if (!title) {
    showToast('請輸入任務名稱', 'warning');
    return;
  }

  const payload = {
    title,
    category: document.getElementById('task-input-category').value,
    priority: document.getElementById('task-input-priority').value,
    due_date: document.getElementById('task-input-duedate').value,
    progress: parseInt(document.getElementById('task-input-progress').value, 10),
    description: document.getElementById('task-input-desc').value.trim()
  };

  try {
    if (editId) {
      await authFetch(`/api/tasks/${editId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      showToast('任務已成功更新', 'success');
    } else {
      payload.status = 'pending';
      await authFetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      showToast('任務已成功建立', 'success');
    }
    closeTaskModal();
    await loadTasks();
    loadStats();
  } catch (err) {
    showToast('儲存失敗：' + err.message, 'error');
  }
}

function editTask(id) {
  const task = state.tasks.find(t => t.id === id);
  if (task) openTaskModal(task);
}

async function updateTaskStatus(id, newStatus) {
  try {
    const task = state.tasks.find(t => t.id === id);
    const progress = newStatus === 'completed' ? 100 : (task.progress === 100 ? 50 : task.progress);
    await authFetch(`/api/tasks/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus, progress })
    });
    await loadTasks();
    loadStats();
    showToast('任務狀態已更新', 'info');
  } catch (err) {
    showToast('更新失敗', 'error');
  }
}

async function deleteTask(id) {
  if (!confirm('確定要刪除此任務嗎？')) return;
  try {
    await authFetch(`/api/tasks/${id}`, { method: 'DELETE' });
    await loadTasks();
    loadStats();
    showToast('任務已刪除', 'info');
  } catch (err) {
    showToast('刪除失敗', 'error');
  }
}

// ----------------- B. Ideas Management -----------------
async function loadIdeas() {
  try {
    const res = await authFetch('/api/ideas');
    const json = await res.json();
    if (json.success) {
      state.ideas = json.data;
      updateIdeaCountBadges();
      renderIdeas();
    }
  } catch (err) {
    console.error('Failed to load ideas:', err);
  }
}

function updateIdeaCountBadges() {
  const totalCount = state.ideas.length;
  const starredCount = state.ideas.filter(i => i.is_starred).length;

  const allEl = document.getElementById('idea-count-all');
  const starEl = document.getElementById('idea-count-starred');
  if (allEl) allEl.innerText = totalCount;
  if (starEl) starEl.innerText = starredCount;
}

function filterIdeas(type) {
  state.ideaFilter = type;
  const btnAll = document.getElementById('idea-filter-all');
  const btnStarred = document.getElementById('idea-filter-starred');

  if (type === 'starred') {
    btnStarred.className = "px-3.5 py-1.5 rounded-lg bg-white text-amber-600 shadow-sm transition flex items-center gap-1 font-bold";
    btnAll.className = "px-3.5 py-1.5 rounded-lg text-slate-600 hover:text-purple-700 transition";
  } else {
    btnAll.className = "px-3.5 py-1.5 rounded-lg bg-white text-purple-700 shadow-sm transition font-bold";
    btnStarred.className = "px-3.5 py-1.5 rounded-lg text-slate-600 hover:text-amber-600 transition flex items-center gap-1";
  }
  renderIdeas();
}

function selectIdeaColor(color) {
  state.selectedIdeaColor = color;
  document.querySelectorAll('#idea-color-picker button').forEach(btn => {
    if (btn.getAttribute('data-color') === color) {
      btn.classList.add('ring-2', 'ring-offset-1', 'ring-slate-400');
    } else {
      btn.classList.remove('ring-2', 'ring-offset-1', 'ring-slate-400');
    }
  });
}

async function saveIdea() {
  const title = document.getElementById('idea-input-title').value.trim();
  const content = document.getElementById('idea-input-content').value.trim();
  const tags = document.getElementById('idea-input-tags').value.trim();

  if (!title) {
    showToast('請輸入靈感主旨', 'warning');
    return;
  }

  const payload = {
    title,
    content,
    tags,
    color: state.selectedIdeaColor || '#fef3c7',
    is_starred: 0
  };

  try {
    await authFetch('/api/ideas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    document.getElementById('idea-input-title').value = '';
    document.getElementById('idea-input-content').value = '';
    document.getElementById('idea-input-tags').value = '';
    showToast('靈感已收錄至靈感庫！', 'success');
    await loadIdeas();
    loadStats();
  } catch (err) {
    showToast('儲存失敗：' + err.message, 'error');
  }
}

function renderIdeas() {
  const grid = document.getElementById('ideas-grid');
  grid.innerHTML = '';

  const displayList = state.ideaFilter === 'starred'
    ? state.ideas.filter(i => i.is_starred)
    : state.ideas;

  if (displayList.length === 0) {
    grid.innerHTML = `
      <div class="col-span-full py-12 text-center text-slate-400">
        <i class="fa-regular fa-lightbulb text-4xl mb-3"></i>
        <p class="text-sm">${state.ideaFilter === 'starred' ? '目前沒有標記星號的靈感' : '尚未記錄任何靈光乍現的點子。在上方輸入並儲存吧！'}</p>
      </div>
    `;
    return;
  }

  displayList.forEach(idea => {
    const card = document.createElement('div');
    card.className = "idea-card p-5 rounded-2xl border border-slate-200/80 shadow-sm flex flex-col justify-between space-y-3";
    card.style.backgroundColor = idea.color || '#fef3c7';

    const tagsHtml = (idea.tags || '').split(',').filter(Boolean).map(t => 
      `<span class="text-[10px] bg-black/5 font-semibold px-2 py-0.5 rounded-md">#${t.trim()}</span>`
    ).join(' ');

    const isConverted = !!idea.converted_to_task_id;

    card.innerHTML = `
      <div>
        <div class="flex items-start justify-between gap-2 mb-2">
          <h4 class="font-bold text-slate-900 text-base leading-snug">${escapeHtml(idea.title)}</h4>
          <div class="flex items-center gap-1">
            <button onclick="toggleStarIdea(${idea.id}, ${idea.is_starred ? 0 : 1})" class="text-amber-500 hover:scale-110 transition p-1" title="${idea.is_starred ? '取消星號' : '設為星號'}">
              <i class="${idea.is_starred ? 'fa-solid' : 'fa-regular'} fa-star text-base"></i>
            </button>
            <button onclick="openIdeaEditModal(${idea.id})" class="text-slate-500 hover:text-purple-700 transition p-1 text-xs" title="編輯與補充">
              <i class="fa-solid fa-pen-to-square"></i>
            </button>
            <button onclick="deleteIdea(${idea.id})" class="text-slate-400 hover:text-rose-600 transition p-1 text-xs" title="刪除">
              <i class="fa-solid fa-trash-can"></i>
            </button>
          </div>
        </div>

        <p class="text-sm text-slate-700 whitespace-pre-line leading-relaxed">${escapeHtml(idea.content || '')}</p>
        
        <div class="flex flex-wrap gap-1 mt-3">${tagsHtml}</div>
      </div>

      <div class="pt-3 border-t border-black/5 flex items-center justify-between text-xs">
        <span class="text-slate-400 text-[11px]">${(idea.created_at || '').substring(0, 10)}</span>
        
        <div class="flex items-center gap-1.5">
          <button onclick="openIdeaEditModal(${idea.id})" class="px-2.5 py-1.5 bg-white/80 hover:bg-white text-purple-700 border border-purple-200 font-medium rounded-lg transition shadow-xs flex items-center gap-1">
            <i class="fa-solid fa-pen-nib text-[10px]"></i> 編輯/補充
          </button>
          ${isConverted ? `
            <span class="text-indigo-700 font-bold flex items-center gap-1 bg-indigo-50/80 px-2.5 py-1 rounded-lg">
              <i class="fa-solid fa-check"></i> 已晉升專案
            </span>
          ` : `
            <button onclick="openConvertModal(${idea.id}, '${escapeHtml(idea.title)}')" class="px-3 py-1.5 bg-slate-900 hover:bg-indigo-600 text-white font-medium rounded-lg transition shadow-sm flex items-center gap-1.5">
              <i class="fa-solid fa-rocket"></i> 晉升任務
            </button>
          `}
        </div>
      </div>
    `;
    grid.appendChild(card);
  });
}

function openIdeaEditModal(id) {
  const idea = state.ideas.find(i => i.id === id);
  if (!idea) return;
  document.getElementById('idea-edit-modal').classList.remove('hidden');
  document.getElementById('idea-edit-id').value = idea.id;
  document.getElementById('idea-edit-title').value = idea.title;
  document.getElementById('idea-edit-content').value = idea.content || '';
  document.getElementById('idea-edit-tags').value = idea.tags || '';
  document.getElementById('idea-edit-starred').checked = !!idea.is_starred;
  document.getElementById('idea-supplement-input').value = '';
}

function closeIdeaEditModal() {
  document.getElementById('idea-edit-modal').classList.add('hidden');
}

function appendIdeaSupplement() {
  const input = document.getElementById('idea-supplement-input');
  const val = input.value.trim();
  if (!val) {
    showToast('請輸入要追加的補充想法', 'warning');
    return;
  }

  const textarea = document.getElementById('idea-edit-content');
  const now = new Date();
  const timeStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  
  const supplementEntry = `\n\n[${timeStr} 補充筆記]：\n${val}`;
  textarea.value = textarea.value.trim() + supplementEntry;
  input.value = '';
  showToast('已追加補充內容至編輯區，點擊儲存變更即可生效', 'info');
}

async function submitIdeaEdit() {
  const id = document.getElementById('idea-edit-id').value;
  const title = document.getElementById('idea-edit-title').value.trim();
  const content = document.getElementById('idea-edit-content').value.trim();
  const tags = document.getElementById('idea-edit-tags').value.trim();
  const is_starred = document.getElementById('idea-edit-starred').checked ? 1 : 0;

  if (!title) {
    showToast('請輸入靈感標題', 'warning');
    return;
  }

  try {
    const res = await authFetch(`/api/ideas/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, content, tags, is_starred })
    });
    const json = await res.json();
    if (json.success) {
      showToast('靈感內容與補充已成功儲存！', 'success');
      closeIdeaEditModal();
      await loadIdeas();
      loadStats();
    }
  } catch (err) {
    showToast('儲存失敗：' + err.message, 'error');
  }
}

async function toggleStarIdea(id, newState) {
  try {
    await authFetch(`/api/ideas/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_starred: newState })
    });
    await loadIdeas();
    loadStats();
  } catch (err) {
    showToast('更新失敗', 'error');
  }
}

async function deleteIdea(id) {
  if (!confirm('確定要刪除這則靈感便籤嗎？')) return;
  try {
    await authFetch(`/api/ideas/${id}`, { method: 'DELETE' });
    await loadIdeas();
    loadStats();
    showToast('便籤已刪除', 'info');
  } catch (err) {
    showToast('刪除失敗', 'error');
  }
}

function openConvertModal(ideaId, ideaTitle) {
  document.getElementById('convert-modal').classList.remove('hidden');
  populateCategoryDropdowns();
  document.getElementById('convert-idea-id').value = ideaId;
  document.getElementById('convert-task-title').value = ideaTitle;
}

function closeConvertModal() {
  document.getElementById('convert-modal').classList.add('hidden');
}

async function submitIdeaConversion() {
  const ideaId = document.getElementById('convert-idea-id').value;
  const title = document.getElementById('convert-task-title').value.trim();
  const category = document.getElementById('convert-task-category').value;
  const dueDate = document.getElementById('convert-task-duedate').value;

  if (!title) {
    showToast('請確認任務名稱', 'warning');
    return;
  }

  try {
    const res = await authFetch(`/api/ideas/${ideaId}/convert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, category, due_date: dueDate })
    });
    const json = await res.json();
    if (json.success) {
      showToast('🎉 靈感已成功晉升為 A 類靜態工作！', 'success');
      closeConvertModal();
      await loadIdeas();
      await loadTasks();
      loadStats();
      switchTab('tasks');
    }
  } catch (err) {
    showToast('轉換失敗：' + err.message, 'error');
  }
}

// ----------------- C. Business Meetings & Voice -----------------
function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    console.warn('Web Speech API is not supported in this browser.');
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = 'zh-TW';
  recognition.continuous = true;
  recognition.interimResults = true;

  recognition.onstart = () => {
    isRecording = true;
    updateRecordingUI(true);
  };

  recognition.onresult = (event) => {
    let interimTranscript = '';
    let finalTranscript = '';

    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalTranscript += event.results[i][0].transcript;
      } else {
        interimTranscript += event.results[i][0].transcript;
      }
    }

    const textarea = document.getElementById('business-raw-text');
    if (finalTranscript) {
      textarea.value = (textarea.value ? textarea.value + ' ' : '') + finalTranscript;
    }
  };

  recognition.onerror = (event) => {
    console.error('Speech recognition error:', event.error);
    isRecording = false;
    updateRecordingUI(false);
    showToast('語音辨識提醒：' + event.error, 'warning');
  };

  recognition.onend = () => {
    isRecording = false;
    updateRecordingUI(false);
  };
}

function toggleSpeechRecognition() {
  if (!recognition) {
    alert('您的瀏覽器尚未原生支援 Web Speech API 語音輸入，請使用 Google Chrome 或 Edge，或可直接於文字框輸入/貼上會談紀要！');
    return;
  }

  if (isRecording) {
    recognition.stop();
  } else {
    try {
      recognition.start();
    } catch (e) {
      console.warn(e);
    }
  }
}

function updateRecordingUI(recording) {
  const micIcon = document.getElementById('mic-status-icon');
  const micText = document.getElementById('mic-status-text');
  const micSubText = document.getElementById('mic-status-subtext');
  const btnLabel = document.getElementById('btn-record-label');
  const indicator = document.getElementById('recording-indicator');

  if (recording) {
    micIcon.className = 'w-12 h-12 rounded-2xl bg-rose-500 text-white flex items-center justify-center text-xl shadow-lg shadow-rose-200 animate-pulse';
    micText.innerText = '正在即時聆聽會談...';
    micSubText.innerText = '系統正辨識語音並即時轉錄為文字';
    btnLabel.innerText = '停止錄音';
    indicator.classList.remove('hidden');
  } else {
    micIcon.className = 'w-12 h-12 rounded-2xl bg-slate-100 text-slate-500 flex items-center justify-center text-xl';
    micText.innerText = '語音輸入待命';
    micSubText.innerText = '點擊開始錄音，或直接於下方輸入會談紀錄';
    btnLabel.innerText = '開始錄音';
    indicator.classList.add('hidden');
  }
}

function clearTranscript() {
  document.getElementById('business-raw-text').value = '';
  document.getElementById('ai-result-panel').classList.add('hidden');
  state.currentAnalysis = null;
}

async function analyzeMeetingText() {
  const text = document.getElementById('business-raw-text').value.trim();
  if (!text) {
    showToast('請先輸入或錄製會談內容', 'warning');
    return;
  }

  const btn = document.getElementById('btn-analyze');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> AI 萃取與解析中...';

  try {
    const res = await authFetch('/api/business/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    const json = await res.json();
    if (json.success) {
      state.currentAnalysis = json.data;
      state.currentAnalysis.raw_transcript = text;
      renderAnalysisResult(json.data);
      showToast('AI 分析與時序提取完成！', 'success');
    }
  } catch (err) {
    showToast('分析失敗：' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> 提煉重點摘要 & 解析時序';
  }
}

function renderAnalysisResult(analysis) {
  const panel = document.getElementById('ai-result-panel');
  panel.classList.remove('hidden');

  document.getElementById('result-client-badge').innerText = analysis.client_name ? `對象：${analysis.client_name}` : '一般業務對談';
  document.getElementById('result-summary').innerText = analysis.summary || '無摘要';
  document.getElementById('result-event-time').innerText = analysis.event_time || '未偵測到明確時間時序';

  // Action Items
  const actionList = document.getElementById('result-action-items');
  actionList.innerHTML = '';
  if (analysis.action_items && analysis.action_items.length > 0) {
    analysis.action_items.forEach(item => {
      const li = document.createElement('li');
      li.className = 'flex items-center gap-2';
      li.innerHTML = `<i class="fa-regular fa-square-check text-indigo-500"></i> <span>${escapeHtml(item.text)}</span>`;
      actionList.appendChild(li);
    });
  } else {
    actionList.innerHTML = '<li class="text-slate-400">無特別標註待辦</li>';
  }

  // Google Calendar Link
  const gcalLink = document.getElementById('btn-gcal-link');
  if (analysis.google_calendar_url) {
    gcalLink.href = analysis.google_calendar_url;
    gcalLink.classList.remove('pointer-events-none', 'opacity-50');
  } else {
    gcalLink.href = '#';
    gcalLink.classList.add('pointer-events-none', 'opacity-50');
  }
}

async function saveCurrentMeetingLog() {
  if (!state.currentAnalysis) {
    showToast('請先執行 AI 提煉與分析', 'warning');
    return;
  }

  try {
    await authFetch('/api/business', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state.currentAnalysis)
    });
    showToast('業務會談紀錄已成功歸檔！', 'success');
    await loadBusinessLogs();
    loadStats();
  } catch (err) {
    showToast('儲存失敗：' + err.message, 'error');
  }
}

async function loadBusinessLogs() {
  try {
    const res = await authFetch('/api/business');
    const json = await res.json();
    if (json.success) {
      state.businessLogs = json.data;
      renderBusinessLogs();
    }
  } catch (err) {
    console.error('Failed to load business logs:', err);
  }
}

function renderBusinessLogs() {
  const container = document.getElementById('business-logs-list');
  container.innerHTML = '';

  if (state.businessLogs.length === 0) {
    container.innerHTML = `
      <div class="py-8 text-center text-slate-400 bg-white rounded-2xl border border-slate-200">
        <i class="fa-regular fa-folder-open text-3xl mb-2"></i>
        <p class="text-sm">尚無歷史業務紀錄。完成語音提煉後儲存即可建立存檔！</p>
      </div>
    `;
    return;
  }

  state.businessLogs.forEach(log => {
    const item = document.createElement('div');
    item.className = "bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-3";

    const actionsHtml = (log.action_items || []).map(a => 
      `<span class="inline-block bg-slate-100 text-slate-700 text-xs px-2.5 py-1 rounded-lg mr-1 mb-1"><i class="fa-solid fa-check text-indigo-500 mr-1"></i>${escapeHtml(a.text)}</span>`
    ).join('');

    item.innerHTML = `
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-100 pb-2.5">
        <div>
          <h4 class="font-bold text-slate-900 text-base">${escapeHtml(log.title)}</h4>
          <div class="flex items-center gap-3 text-xs text-slate-400 mt-1">
            <span><i class="fa-regular fa-calendar"></i> 記錄日期：${(log.created_at || '').substring(0, 16).replace('T', ' ')}</span>
            ${log.client_name ? `<span class="text-indigo-600 font-semibold"><i class="fa-regular fa-user"></i> ${escapeHtml(log.client_name)}</span>` : ''}
          </div>
        </div>

        <div class="flex items-center gap-2">
          ${log.google_calendar_url ? `
            <a href="${log.google_calendar_url}" target="_blank" class="px-3 py-1.5 bg-blue-50 text-blue-700 hover:bg-blue-100 font-bold rounded-lg text-xs transition flex items-center gap-1">
              <i class="fa-brands fa-google"></i> Google 日曆
            </a>
          ` : ''}
          ${log.event_time ? `
            <a href="/api/business/${log.id}/ics" class="px-3 py-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 font-medium rounded-lg text-xs transition flex items-center gap-1">
              <i class="fa-solid fa-download"></i> .ics 下載
            </a>
          ` : ''}
          <button onclick="deleteBusinessLog(${log.id})" class="text-slate-400 hover:text-rose-600 p-1.5 text-xs transition">
            <i class="fa-solid fa-trash-can"></i>
          </button>
        </div>
      </div>

      <div class="text-xs text-slate-600 bg-slate-50 p-3 rounded-xl whitespace-pre-line leading-relaxed">
        ${escapeHtml(log.summary || log.raw_transcript)}
      </div>

      ${actionsHtml ? `<div>${actionsHtml}</div>` : ''}
    `;
    container.appendChild(item);
  });
}

async function deleteBusinessLog(id) {
  if (!confirm('確定要刪除這筆業務紀錄嗎？')) return;
  try {
    await authFetch(`/api/business/${id}`, { method: 'DELETE' });
    await loadBusinessLogs();
    loadStats();
    showToast('紀錄已刪除', 'info');
  } catch (err) {
    showToast('刪除失敗', 'error');
  }
}

// ----------------- Utilities -----------------
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  
  const colors = {
    info: 'bg-slate-900 text-white',
    success: 'bg-emerald-600 text-white',
    warning: 'bg-amber-600 text-white',
    error: 'bg-rose-600 text-white'
  };

  const icons = {
    info: 'fa-solid fa-circle-info',
    success: 'fa-solid fa-circle-check',
    warning: 'fa-solid fa-triangle-exclamation',
    error: 'fa-solid fa-circle-xmark'
  };

  toast.className = `toast px-4 py-3 rounded-xl shadow-lg text-sm flex items-center gap-2.5 ${colors[type] || colors.info}`;
  toast.innerHTML = `<i class="${icons[type] || icons.info}"></i> <span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
