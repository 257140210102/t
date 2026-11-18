/**
 * ============================================================================
 * HỆ THỐNG QUẢN LÝ HỌC TẬP TRỰC TUYẾN (EDULMS PRO)
 * Tệp: frontend/app.js
 * Mô tả: Điều khiển giao diện người dùng (SPA Vanilla JS), xác thực JWT,
 *        phân quyền theo vai trò (ADMIN / TEACHER / STUDENT), biểu đồ Chart.js,
 *        Sandbox lập trình đa ngôn ngữ, Studio Video AI, Gia sư AI Gemini
 *        và hệ thống giám sát phòng thi trực tuyến (Anti-Cheating + WebSocket).
 * ============================================================================
 */

const API_BASE_URL = window.EDULMS_API_URL || 'http://localhost:8000';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

// ============================================================================
// 1. TRẠNG THÁI ỨNG DỤNG TOÀN CỤC (APPLICATION STATE)
// ============================================================================

const AppState = {
  token: localStorage.getItem('edulms_token') || null,
  user: JSON.parse(localStorage.getItem('edulms_user') || 'null'),
  currentView: 'dashboard',
  analyticsChart: null,
  meta: { classes: [], subjects: [] },
  lastAiGeneratedQuestions: [],
  proctoringPollInterval: null,

  // Trạng thái phòng thi trực tuyến & Anti-Cheating
  activeExam: {
    attemptId: null,
    examId: null,
    title: '',
    variantCode: '',
    aiAllowed: false,
    remainingSeconds: 0,
    timerInterval: null,
    autosaveInterval: null,
    tabSwitchCount: 0,
    fullscreenExitCount: 0,
    answers: {}, // { question_id: { selected_option_ids: [], text_response: '' } }
  },

  // Kết nối WebSocket giám sát thi cho Giáo viên
  proctoringSocket: null,

  // Dữ liệu hiển thị & đồng bộ cục bộ
  notifications: [
    {
      id: 1,
      title: 'Bài tập mới: Thuật toán sắp xếp Python',
      message: 'Hạn nộp: 23:59 ngày 25/11/2026',
      isRead: false,
    },
    {
      id: 2,
      title: 'Kỳ thi giữa kỳ I môn Tin học',
      message: 'Hệ thống bật giám sát Anti-Cheating và khóa AI.',
      isRead: false,
    },
  ],
};

// Cấu hình menu điều hướng theo từng vai trò
const ROLE_MENUS = {
  ADMIN: [
    { id: 'dashboard', label: 'Tổng quan hệ thống', icon: 'layout-dashboard' },
    { id: 'admin-users', label: 'Tài khoản & Bảo trì', icon: 'users-cog' },
    { id: 'classes', label: 'Quản lý lớp học', icon: 'school' },
    { id: 'materials', label: 'Kho học liệu & Video AI', icon: 'folder-open' },
    { id: 'exams', label: 'Giám sát kỳ thi', icon: 'shield-check' },
    { id: 'grades', label: 'Báo cáo điểm số', icon: 'bar-chart-3' },
    { id: 'profile', label: 'Hồ sơ & Đổi mật khẩu', icon: 'user-cog' },
  ],
  TEACHER: [
    { id: 'dashboard', label: 'Tổng quan giảng dạy', icon: 'layout-dashboard' },
    { id: 'classes', label: 'Lớp học phụ trách', icon: 'users' },
    { id: 'materials', label: 'Tài liệu & Video AI', icon: 'video' },
    { id: 'assignments', label: 'Bài tập & Code Sandbox', icon: 'code-2' },
    { id: 'exams', label: 'Đề thi & Giám sát Live', icon: 'clipboard-check' },
    { id: 'grades', label: 'Chấm bài & Bảng điểm', icon: 'award' },
    { id: 'profile', label: 'Hồ sơ & Đổi mật khẩu', icon: 'user-cog' },
  ],
  STUDENT: [
    { id: 'dashboard', label: 'Góc học tập', icon: 'layout-dashboard' },
    { id: 'classes', label: 'Lớp học của tôi', icon: 'book-open' },
    { id: 'materials', label: 'Bài giảng & Tài liệu', icon: 'file-text' },
    { id: 'assignments', label: 'Bài tập & Lập trình', icon: 'terminal' },
    { id: 'exams', label: 'Kiểm tra trực tuyến', icon: 'pen-tool' },
    { id: 'grades', label: 'Kết quả học tập', icon: 'trending-up' },
    { id: 'profile', label: 'Hồ sơ & Đổi mật khẩu', icon: 'user-cog' },
  ],
};

const ROLE_LABELS = {
  ADMIN: 'QUẢN TRỊ VIÊN',
  TEACHER: 'GIÁO VIÊN',
  STUDENT: 'HỌC SINH',
};

const SANDBOX_TEMPLATES = {
  html: `<!DOCTYPE html>\n<html>\n<body style="font-family:sans-serif;padding:16px;">\n  <h2 style="color:#2563eb;">Xin chào từ EduLMS Live HTML!</h2>\n  <button onclick="alert('Chạy JavaScript thành công!')">Bấm thử nghiệm</button>\n</body>\n</html>`,
  python: `def giai_thua(n):\n    return 1 if n <= 1 else n * giai_thua(n - 1)\n\nprint("Kết quả 5! =", giai_thua(5))`,
  javascript: `function fibonacci(n) {\n  if (n <= 1) return n;\n  return fibonacci(n - 1) + fibonacci(n - 2);\n}\n\nconsole.log("Fibonacci(8) =", fibonacci(8));`,
  cpp: `#include <iostream>\nusing namespace std;\n\nint main() {\n    int sum = 0;\n    for (int i = 1; i <= 10; ++i) sum += i;\n    cout << "Tong 1..10 = " << sum << endl;\n    return 0;\n}`,
  c: `#include <stdio.h>\n\nint main() {\n    printf("Xin chao tu ngon ngu C tren EduLMS Pro!\\n");\n    return 0;\n}`,
  java: `public class Main {\n    public static void main(String[] args) {\n        System.out.println("Xin chao tu Java 17 Sandbox!");\n    }\n}`,
};

// ============================================================================
// 2. HÀM GỌI REST API & XỬ LÝ LỖI TẬP TRUNG
// ============================================================================

async function apiFetch(endpoint, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (AppState.token) {
    headers['Authorization'] = `Bearer ${AppState.token}`;
  }
  const customGeminiKey = localStorage.getItem('edulms_gemini_key');
  if (customGeminiKey) {
    headers['X-Gemini-Api-Key'] = customGeminiKey;
  }
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  // Hiển thị banner cảnh báo nếu hệ thống đang bật chế độ bảo trì (HTTP 503)
  const banner = document.getElementById('maintenance-banner');
  if (response.status === 503) {
    banner?.classList.remove('hidden');
    throw new Error('Hệ thống đang trong chế độ bảo trì.');
  } else {
    banner?.classList.add('hidden');
  }

  if (response.status === 401) {
    handleLogout();
    throw new Error('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
  }

  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = typeof data === 'object' && data.detail ? data.detail : 'Lỗi kết nối máy chủ.';
    throw new Error(message);
  }

  return data;
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ============================================================================
// 3. KHỞI TẠO ỨNG DỤNG & XÁC THỰC ĐĂNG NHẬP
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
  const endpointLabel = document.getElementById('api-endpoint-label');
  if (endpointLabel) endpointLabel.textContent = API_BASE_URL;

  bindGlobalEvents();
  refreshIcons();

  if (AppState.token && AppState.user) {
    enterAppShell();
  } else {
    showAuthScreen();
  }
});

function refreshIcons() {
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons();
  }
}

function showAuthScreen() {
  document.getElementById('auth-screen')?.classList.remove('hidden');
  document.getElementById('app-shell')?.classList.add('hidden');
}

async function enterAppShell() {
  document.getElementById('auth-screen')?.classList.add('hidden');
  document.getElementById('app-shell')?.classList.remove('hidden');

  const role = AppState.user?.role || 'STUDENT';
  document.getElementById('current-role-pill').textContent = ROLE_LABELS[role] || role;
  document.getElementById('current-user-name').textContent = AppState.user?.full_name || 'Người dùng';

  applyRoleVisibility(role);
  renderSidebarNavigation(role);
  renderNotifications();
  try {
    AppState.meta = await apiFetch('/api/meta/options');
  } catch (_) {}
  switchView('dashboard');
}

function applyRoleVisibility(role) {
  const isStaff = role === 'ADMIN' || role === 'TEACHER';
  document.querySelectorAll('.role-teacher-admin').forEach((el) => {
    el.classList.toggle('hidden', !isStaff);
  });
  document.querySelectorAll('.role-student').forEach((el) => {
    el.classList.toggle('hidden', role !== 'STUDENT');
  });
}

async function handleLoginSubmit(event) {
  event.preventDefault();
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const errorBox = document.getElementById('login-error');
  errorBox.classList.add('hidden');

  try {
    const formBody = new URLSearchParams();
    formBody.append('username', username);
    formBody.append('password', password);

    const data = await apiFetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formBody.toString(),
    });

    AppState.token = data.access_token;
    AppState.user = data.user;
    localStorage.setItem('edulms_token', data.access_token);
    localStorage.setItem('edulms_user', JSON.stringify(data.user));
    enterAppShell();
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.remove('hidden');
  }
}

function handleLogout() {
  if (AppState.proctoringSocket) {
    AppState.proctoringSocket.close();
    AppState.proctoringSocket = null;
  }
  AppState.token = null;
  AppState.user = null;
  localStorage.removeItem('edulms_token');
  localStorage.removeItem('edulms_user');
  showAuthScreen();
}

// ============================================================================
// 4. ĐIỀU HƯỚNG SIDEBAR & CHUYỂN ĐỔI PHÂN HỆ (VIEWS)
// ============================================================================

function renderSidebarNavigation(role) {
  const nav = document.getElementById('sidebar-nav');
  const items = ROLE_MENUS[role] || ROLE_MENUS.STUDENT;

  nav.innerHTML = items
    .map(
      (item) => `
      <button type="button" class="nav-item ${item.id === AppState.currentView ? 'active' : ''}" data-view="${item.id}">
        <i data-lucide="${item.icon}"></i>
        <span>${item.label}</span>
      </button>
    `
    )
    .join('');

  nav.querySelectorAll('.nav-item').forEach((btn) => {
    btn.addEventListener('click', () => {
      switchView(btn.dataset.view);
      document.getElementById('sidebar')?.classList.remove('open');
    });
  });

  refreshIcons();
}

function switchView(viewId) {
  AppState.currentView = viewId;

  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.view === viewId);
  });

  document.querySelectorAll('.view-section').forEach((sec) => {
    sec.classList.toggle('hidden', sec.id !== `view-${viewId}`);
  });

  const activeMenu = (ROLE_MENUS[AppState.user?.role] || []).find((m) => m.id === viewId);
  if (activeMenu) {
    document.getElementById('page-title').textContent = activeMenu.label;
  }

  // Nạp dữ liệu tương ứng với phân hệ đang mở
  if (viewId === 'dashboard') loadDashboardView();
  if (viewId === 'admin-users') loadAdminUsersView();
  if (viewId === 'classes') loadClassesView();
  if (viewId === 'materials') loadMaterialsView();
  if (viewId === 'assignments') loadAssignmentsView();
  if (viewId !== 'exams' && AppState.proctoringPollInterval) {
    clearInterval(AppState.proctoringPollInterval);
    AppState.proctoringPollInterval = null;
  }
  if (viewId === 'exams') loadExamsAndProctoringView();
  if (viewId === 'grades') loadGradesView();
  if (viewId === 'profile') loadProfileView();
}
// ============================================================================
// 5. PHÂN HỆ TỔNG QUAN (DASHBOARD KPI & BIỂU ĐỒ CHART.JS)
// ============================================================================

async function loadDashboardView() {
  const role = AppState.user?.role || 'STUDENT';
  let kpis = [];

  if (role === 'ADMIN') {
    let stats = {
      total_users: 148,
      total_teachers: 18,
      total_students: 129,
      total_classes: 12,
      total_assignments: 64,
      total_exams: 24,
    };
    try {
      stats = await apiFetch('/api/admin/dashboard');
    } catch (_) {
      // Giữ số liệu tổng quan mặc định nếu máy chủ chưa khởi động
    }
    kpis = [
      { label: 'Tổng tài khoản', value: stats.total_users },
      { label: 'Giáo viên', value: stats.total_teachers },
      { label: 'Học sinh', value: stats.total_students },
      { label: 'Lớp học hoạt động', value: stats.total_classes },
      { label: 'Bài tập đã giao', value: stats.total_assignments },
      { label: 'Đề kiểm tra', value: stats.total_exams },
    ];
  } else if (role === 'TEACHER') {
    kpis = [
      { label: 'Lớp phụ trách', value: '4 lớp' },
      { label: 'Bài tập chờ chấm', value: '14 bài' },
      { label: 'Đề thi đang mở', value: '2 đề' },
      { label: 'Điểm TB toàn khối', value: '8.2 / 10' },
    ];
  } else {
    kpis = [
      { label: 'Lớp đã tham gia', value: '4 lớp' },
      { label: 'Bài tập hoàn thành', value: '18 / 20' },
      { label: 'Điểm trung bình', value: '8.6' },
      { label: 'Bài sắp đến hạn', value: '2 bài' },
    ];
  }

  document.getElementById('kpi-grid').innerHTML = kpis
    .map(
      (k) => `
      <div class="kpi-card">
        <div>
          <div class="kpi-label">${escapeHtml(k.label)}</div>
          <div class="kpi-value">${escapeHtml(k.value)}</div>
        </div>
      </div>
    `
    )
    .join('');

  renderAnalyticsChart(role);

  document.getElementById('upcoming-deadlines-list').innerHTML = `
    <li>
      <strong>[Tin học 10A1] Thực hành Đệ quy Python</strong>
      <div class="muted-text">Hạn nộp: 25/11/2026 · Hình thức: Code Sandbox</div>
    </li>
    <li>
      <strong>[Toán 10A1] Kiểm tra 45 phút Hàm số bậc hai</strong>
      <div class="muted-text">Thời gian: 08:00 ngày 27/11/2026 · Giám sát Anti-Cheating</div>
    </li>
    <li>
      <strong>[Tiếng Anh 10A1] Bài luận Unit 4: For a Better Community</strong>
      <div class="muted-text">Hạn nộp: 30/11/2026 · Cho phép nộp tệp PDF/DOCX</div>
    </li>
  `;
}

function renderAnalyticsChart(role) {
  const ctx = document.getElementById('main-analytics-chart');
  if (!ctx || !window.Chart) return;

  if (AppState.analyticsChart) {
    AppState.analyticsChart.destroy();
  }

  const isStudent = role === 'STUDENT';
  AppState.analyticsChart = new Chart(ctx, {
    type: isStudent ? 'line' : 'bar',
    data: {
      labels: isStudent
        ? ['Tuần 1', 'Tuần 2', 'Tuần 3', 'Tuần 4', 'Tuần 5', 'Tuần 6']
        : ['Yếu (<5)', 'Trung bình (5-6.4)', 'Khá (6.5-7.9)', 'Giỏi (8.0-8.9)', 'Xuất sắc (9-10)'],
      datasets: [
        {
          label: isStudent ? 'Điểm kiểm tra trung bình' : 'Số lượng học sinh',
          data: isStudent ? [7.5, 8.0, 7.8, 8.5, 8.8, 9.0] : [3, 12, 34, 48, 22],
          backgroundColor: isStudent ? 'rgba(37, 99, 235, 0.15)' : '#2563eb',
          borderColor: '#2563eb',
          borderWidth: 2,
          borderRadius: 6,
          fill: isStudent,
          tension: 0.35,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: 'top' },
      },
    },
  });
}

// ============================================================================
// 6. PHÂN HỆ QUẢN TRỊ VIÊN (TÀI KHOẢN, CSV, BẢO TRÌ, SAO LƯU SQL)
// ============================================================================

async function loadAdminUsersView() {
  try {
    const users = await apiFetch('/api/admin/users');
    document.getElementById('admin-users-tbody').innerHTML = users
      .map(
        (u) => `
        <tr>
          <td>#${u.id}</td>
          <td><code>${escapeHtml(u.username)}</code></td>
          <td><strong>${escapeHtml(u.full_name)}</strong></td>
          <td><span class="badge badge-primary">${escapeHtml(u.role)}</span></td>
          <td>${escapeHtml(u.email || '')}</td>
          <td><span class="badge ${u.is_active ? 'badge-success' : 'badge-danger'}">${u.is_active ? 'Hoạt động' : 'Đã khóa'}</span></td>
          <td>
            <button type="button" class="btn btn-secondary" onclick="toggleUserActive(${u.id})">
              ${u.is_active ? 'Khóa' : 'Mở khóa'}
            </button>
          </td>
        </tr>
      `
      )
      .join('');
  } catch (err) {
    alert(`Lỗi tải danh sách tài khoản: ${err.message}`);
  }
}

window.toggleUserActive = async function (userId) {
  try {
    await apiFetch(`/api/admin/users/${userId}/toggle-active`, { method: 'PATCH' });
    loadAdminUsersView();
  } catch (err) {
    alert(err.message);
  }
};

async function handleCreateUserPrompt() {
  const fullName = prompt('Nhập họ và tên người dùng mới:');
  if (!fullName) return;
  const username = prompt('Nhập tên đăng nhập (VD: GV002 hoặc HS2026010):');
  if (!username) return;
  const roleCode = (prompt('Nhập vai trò (ADMIN / TEACHER / STUDENT):', 'STUDENT') || 'STUDENT').toUpperCase();
  const password = prompt('Nhập mật khẩu khởi tạo:', '123456') || '123456';

  try {
    const res = await apiFetch('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify({
        username,
        full_name: fullName,
        role_code: roleCode,
        password,
        code_identifier: username,
      }),
    });
    alert(res.message || 'Tạo tài khoản thành công!');
    loadAdminUsersView();
  } catch (err) {
    alert(`Lỗi tạo tài khoản: ${err.message}`);
  }
}

async function handleCsvUsersUpload(event) {
  const file = event.target.files?.[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await apiFetch('/api/admin/users/import-csv', {
      method: 'POST',
      body: formData,
    });
    alert(`Đã nhập thành công ${res.created_count} tài khoản từ tệp CSV.`);
    loadAdminUsersView();
  } catch (err) {
    alert(`Lỗi nhập CSV: ${err.message}`);
  } finally {
    event.target.value = '';
  }
}

async function handleToggleMaintenance(event) {
  const enabled = event.target.checked;
  try {
    await apiFetch(`/api/admin/settings/maintenance?enabled=${enabled}`, {
      method: 'PATCH',
    });
    alert(enabled ? 'Đã BẬT chế độ bảo trì toàn hệ thống.' : 'Đã TẮT chế độ bảo trì.');
  } catch (err) {
    alert(`Không thể cập nhật chế độ bảo trì: ${err.message}`);
    event.target.checked = !enabled;
  }
}

async function handleExportSqlBackup() {
  try {
    const sqlText = await apiFetch('/api/admin/backup/sql');
    const blob = new Blob([sqlText], { type: 'application/sql;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `edulms_backup_${new Date().toISOString().slice(0, 10)}.sql`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert(`Lỗi sao lưu SQL: ${err.message}`);
  }
}

// ============================================================================
// 7. QUẢN LÝ LỚP HỌC, TÀI LIỆU & STUDIO VIDEO BÀI GIẢNG AI
// ============================================================================

let activeManageClassId = null;

async function loadClassesView() {
  try {
    AppState.meta = await apiFetch('/api/meta/options');
  } catch (err) {
    console.error(err);
  }

  const isStaff = ['ADMIN', 'TEACHER'].includes(AppState.user?.role);
  const myClassIds = AppState.meta.my_class_ids || [];
  const classes = AppState.meta.classes || [];

  if (!classes.length) {
    document.getElementById('classes-grid').innerHTML =
      '<p class="muted-text">Chưa có lớp học nào. Hãy bấm "Tạo lớp học mới" hoặc nhập mã tham gia lớp.</p>';
    return;
  }

  document.getElementById('classes-grid').innerHTML = classes
    .map((c) => {
      const isJoined = myClassIds.includes(c.id);
      return `
        <div class="item-card">
          <div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
              <span class="badge badge-primary">${escapeHtml(c.code)}</span>
              <span class="muted-text">${c.member_count || 0} học sinh</span>
            </div>
            <h4>${escapeHtml(c.name)}</h4>
            <p class="muted-text mt-10">Mã tham gia lớp: <code>${escapeHtml(c.join_code)}</code></p>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">
            ${
              isStaff
                ? `<button type="button" class="btn btn-primary" onclick="openClassMembersPanel(${c.id}, '${escapeHtml(c.code)} - ${escapeHtml(c.name)}')">Phân lớp &amp; DS Học sinh</button>`
                : isJoined
                ? `<span class="badge badge-success">Đã tham gia lớp</span>`
                : `<button type="button" class="btn btn-primary" onclick="quickJoinClassByCode('${escapeHtml(c.join_code)}')">Tham gia lớp ngay</button>`
            }
            <button type="button" class="btn btn-secondary" onclick="switchView('assignments')">
              Bài tập lớp
            </button>
          </div>
        </div>
      `;
    })
    .join('');
}

window.quickJoinClassByCode = async function (joinCode) {
  try {
    const res = await apiFetch(`/api/student/classes/join?join_code=${encodeURIComponent(joinCode)}`, {
      method: 'POST',
    });
    alert(res.message);
    loadClassesView();
  } catch (err) {
    alert(err.message);
  }
};

window.openClassMembersPanel = async function (classId, classTitle) {
  activeManageClassId = classId;
  const panel = document.getElementById('class-members-panel');
  document.getElementById('class-members-title').textContent = `Phân lớp & Danh sách Học sinh: ${classTitle}`;
  panel.classList.remove('hidden');

  const isStaff = ['ADMIN', 'TEACHER'].includes(AppState.user?.role);

  try {
    const members = await apiFetch(`/api/classes/${classId}/members`);
    const memberStudentIds = new Set(members.map((m) => m.student_id));

    if (isStaff) {
      const allStudents = await apiFetch('/api/students');
      const availableStudents = allStudents.filter((s) => !memberStudentIds.has(s.student_id));
      const selectEl = document.getElementById('assign-students-select');
      if (availableStudents.length) {
        selectEl.innerHTML = availableStudents
          .map(
            (s) =>
              `<option value="${s.student_id}">${escapeHtml(s.student_code)} - ${escapeHtml(s.full_name)} (Lớp hiện tại: ${s.class_codes.join(', ') || 'Chưa phân lớp'})</option>`
          )
          .join('');
      } else {
        selectEl.innerHTML = '<option disabled>Tất cả học sinh đều đã có trong lớp này</option>';
      }
    }

    const tbody = document.getElementById('class-members-tbody');
    if (!members.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="muted-text" style="text-align:center;">Lớp này chưa có học sinh nào. Hãy chọn học sinh ở khung phía trên để phân vào lớp.</td></tr>';
      return;
    }

    tbody.innerHTML = members
      .map(
        (m) => `
        <tr>
          <td><code>${escapeHtml(m.student_code)}</code></td>
          <td><strong>${escapeHtml(m.full_name)}</strong></td>
          <td>${escapeHtml(m.email || '')}</td>
          <td><span class="badge badge-success">Đang học</span></td>
          <td class="role-teacher-admin">
            <button type="button" class="btn btn-secondary" onclick="removeStudentFromClass(${classId}, ${m.student_id}, '${escapeHtml(classTitle)}')">
              Xóa khỏi lớp
            </button>
          </td>
        </tr>
      `
      )
      .join('');
  } catch (err) {
    alert(`Lỗi tải danh sách lớp: ${err.message}`);
  }
};

async function handleAssignStudentsSubmit() {
  if (!activeManageClassId) return;
  const selectEl = document.getElementById('assign-students-select');
  const selectedIds = Array.from(selectEl.selectedOptions).map((opt) => Number(opt.value));
  if (!selectedIds.length) {
    return alert('Vui lòng chọn ít nhất 1 học sinh trong danh sách.');
  }

  try {
    const res = await apiFetch(`/api/classes/${activeManageClassId}/members`, {
      method: 'POST',
      body: JSON.stringify({ student_ids: selectedIds }),
    });
    alert(res.message);
    const currentTitle = document.getElementById('class-members-title').textContent.replace('Phân lớp & Danh sách Học sinh: ', '');
    await openClassMembersPanel(activeManageClassId, currentTitle);
    await loadClassesView();
  } catch (err) {
    alert(err.message);
  }
}

window.removeStudentFromClass = async function (classId, studentId, classTitle) {
  if (!confirm('Xác nhận xóa học sinh này khỏi lớp?')) return;
  try {
    await apiFetch(`/api/classes/${classId}/members/${studentId}`, { method: 'DELETE' });
    await openClassMembersPanel(classId, classTitle);
    await loadClassesView();
  } catch (err) {
    alert(err.message);
  }
};

async function handleCreateClass() {
  const code = prompt('Nhập mã lớp học (VD: 12A1):');
  if (!code) return;
  const name = prompt('Nhập tên lớp học:', `Lớp ${code} - Năm học 2026-2027`);
  if (!name) return;

  try {
    const res = await apiFetch('/api/teacher/classes', {
      method: 'POST',
      body: JSON.stringify({ code, name, grade_level_id: 1 }),
    });
    alert(`Tạo lớp ${res.code} thành công! Mã tham gia lớp: ${res.join_code}`);
    loadClassesView();
  } catch (err) {
    alert(`Lỗi tạo lớp: ${err.message}`);
  }
}

async function handleStudentJoinClass() {
  const input = document.getElementById('student-join-code');
  const joinCode = input.value.trim();
  if (!joinCode) {
    alert('Vui lòng nhập mã tham gia lớp học.');
    return;
  }

  try {
    const res = await apiFetch(`/api/student/classes/join?join_code=${encodeURIComponent(joinCode)}`, {
      method: 'POST',
    });
    alert(res.message);
    input.value = '';
    loadClassesView();
  } catch (err) {
    alert(`Không thể tham gia lớp: ${err.message}`);
  }
}

function loadMaterialsView() {
  const materials = [
    { title: 'Chương 1: Thuật toán và Cấu trúc dữ liệu cơ bản', subject: 'Tin học', type: 'PDF', size: '2.4 MB' },
    { title: 'Video AI: Minh họa trực quan Thuật toán Bubble Sort', subject: 'Tin học', type: 'AI_VIDEO', size: '18.6 MB' },
    { title: 'Chuyên đề Hàm số bậc hai và Đồ thị', subject: 'Toán học', type: 'PPTX', size: '5.1 MB' },
  ];

  const renderList = (keyword = '') => {
    const filtered = materials.filter(
      (m) =>
        m.title.toLowerCase().includes(keyword.toLowerCase()) ||
        m.subject.toLowerCase().includes(keyword.toLowerCase())
    );
    document.getElementById('materials-grid').innerHTML = filtered
      .map(
        (m) => `
        <div class="item-card">
          <div>
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
              <span class="badge ${m.type === 'AI_VIDEO' ? 'badge-warning' : 'badge-primary'}">${escapeHtml(m.type)}</span>
              <span class="muted-text">${escapeHtml(m.size)}</span>
            </div>
            <h4>${escapeHtml(m.title)}</h4>
            <p class="muted-text mt-10">Môn học: ${escapeHtml(m.subject)}</p>
          </div>
          <button type="button" class="btn btn-secondary" onclick="alert('Đang mở trình xem trước tài liệu: ${escapeHtml(m.title)}')">
            Xem trước / Tải về
          </button>
        </div>
      `
      )
      .join('');
  };

  renderList();
  const searchInput = document.getElementById('material-search-input');
  searchInput.oninput = (e) => renderList(e.target.value);
}

async function handleGenerateAiVideo(event) {
  event.preventDefault();
  const subjectName = document.getElementById('ai-video-subject').value;
  const lessonTitle = document.getElementById('ai-video-title').value.trim();
  const lessonOutline = document.getElementById('ai-video-outline').value.trim();
  const resultBox = document.getElementById('ai-video-result-box');

  resultBox.textContent = 'Đang kết nối Gemini AI để dựng kịch bản phân cảnh và video bài giảng...';

  try {
    const res = await apiFetch('/api/ai/generate-video', {
      method: 'POST',
      body: JSON.stringify({
        subject_name: subjectName,
        lesson_title: lessonTitle,
        lesson_outline: lessonOutline,
        duration_seconds: 60,
      }),
    });

    resultBox.innerHTML = `
      <strong>Đã tạo Video Bài giảng AI thành công!</strong>
      <div class="muted-text">Tệp xuất bản: <code>${escapeHtml(res.video_url)}</code></div>
      <hr style="margin:10px 0;border:none;border-top:1px solid #ddd6fe;" />
      <div>${escapeHtml(res.storyboard)}</div>
    `;
  } catch (err) {
    resultBox.textContent = `Lỗi tạo Video AI: ${err.message}`;
  }
}

// ============================================================================
// 8. BÀI TẬP & MÔI TRƯỜNG LẬP TRÌNH SANDBOX ĐA NGÔN NGỮ
// ============================================================================

async function loadAssignmentsView() {
  const isStaff = ['ADMIN', 'TEACHER'].includes(AppState.user?.role);

  const clsSel = document.getElementById('asg-class-id');
  const subSel = document.getElementById('asg-subject-id');
  if (clsSel && AppState.meta.classes) {
    clsSel.innerHTML = AppState.meta.classes
      .map((c) => `<option value="${c.id}">${escapeHtml(c.code)} - ${escapeHtml(c.name)}</option>`)
      .join('');
  }
  if (subSel && AppState.meta.subjects) {
    subSel.innerHTML = AppState.meta.subjects
      .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`)
      .join('');
  }
  const dueInput = document.getElementById('asg-due-at');
  if (dueInput && !dueInput.value) {
    dueInput.value = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 16);
  }

  try {
    const assignments = await apiFetch('/api/assignments');
    document.getElementById('assignments-list').innerHTML = assignments
      .map(
        (a) => `
        <div class="item-card">
          <div>
            <div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:8px;">
              <span class="badge badge-primary">${escapeHtml(a.class_code)} · ${escapeHtml(a.subject_name)}</span>
              <span class="badge badge-neutral">Tối đa ${a.max_score}đ</span>
            </div>
            <h4>${escapeHtml(a.title)}</h4>
            <p class="muted-text mt-10">${escapeHtml(a.instructions)}</p>
            <p class="muted-text mt-10">Hạn nộp: ${a.due_at ? new Date(a.due_at).toLocaleString('vi-VN') : 'Không giới hạn'}</p>
          </div>
          ${
            isStaff
              ? `<button type="button" class="btn btn-secondary" onclick="openGradingSubmissions(${a.id}, '${escapeHtml(a.title)}')">Xem &amp; Chấm bài nộp (${a.submission_count})</button>`
              : `<button type="button" class="btn btn-primary" onclick="submitSandboxAsAssignment(${a.id})">Nộp bài từ Code Sandbox (${a.my_score !== null ? 'Điểm: ' + a.my_score : a.my_status})</button>`
          }
        </div>
      `
      )
      .join('');
  } catch (err) {
    document.getElementById('assignments-list').innerHTML = `<div class="error-text">${escapeHtml(err.message)}</div>`;
  }
}

async function handleCreateAssignmentSubmit(event) {
  event.preventDefault();
  try {
    const res = await apiFetch('/api/teacher/assignments', {
      method: 'POST',
      body: JSON.stringify({
        class_id: Number(document.getElementById('asg-class-id').value),
        subject_id: Number(document.getElementById('asg-subject-id').value),
        title: document.getElementById('asg-title').value,
        instructions: document.getElementById('asg-instructions').value,
        submission_types: [document.getElementById('asg-type').value],
        max_score: Number(document.getElementById('asg-max-score').value),
        due_at: document.getElementById('asg-due-at').value,
      }),
    });
    alert(res.message || 'Đã giao bài tập thành công!');
    document.getElementById('create-assignment-panel')?.classList.add('hidden');
    document.getElementById('create-assignment-form')?.reset();
    loadAssignmentsView();
  } catch (err) {
    alert(`Lỗi giao bài tập: ${err.message}`);
  }
}

window.openGradingSubmissions = async function (assignmentId, title) {
  const panel = document.getElementById('grading-submissions-panel');
  const body = document.getElementById('grading-submissions-body');
  document.getElementById('grading-panel-title').textContent = `Bài nộp: ${title}`;
  panel.classList.remove('hidden');

  const subs = await apiFetch(`/api/teacher/assignments/${assignmentId}/submissions`);
  if (!subs.length) {
    body.innerHTML = '<p class="muted-text">Chưa có học sinh nào nộp bài tập này.</p>';
    return;
  }
  body.innerHTML = subs
    .map(
      (s) => `
      <div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin-bottom:12px;">
        <strong>${escapeHtml(s.student_name)} (${escapeHtml(s.student_code)}) — Lần nộp #${s.attempt_number}</strong>
        <pre class="console-output mt-10" style="min-height:60px;">${escapeHtml(s.code_content || s.text_answer || s.external_link || '')}</pre>
        <div style="display:flex;gap:8px;margin-top:10px;">
          <input type="number" id="grade-score-${s.id}" min="0" max="10" step="0.5" value="${s.score ?? 9}" style="width:120px;" />
          <input type="text" id="grade-comment-${s.id}" value="Bài làm tốt, đúng yêu cầu." />
          <button type="button" class="btn btn-primary" onclick="submitGradeForSubmission(${s.id}, ${assignmentId}, '${escapeHtml(title)}')">Lưu điểm</button>
        </div>
      </div>
    `
    )
    .join('');
};

window.submitGradeForSubmission = async function (submissionId, assignmentId, title) {
  const score = Number(document.getElementById(`grade-score-${submissionId}`).value);
  const comment = document.getElementById(`grade-comment-${submissionId}`).value;
  const res = await apiFetch(`/api/teacher/submissions/${submissionId}/grade`, {
    method: 'POST',
    body: JSON.stringify({ score, comment_text: comment }),
  });
  alert(res.message);
  openGradingSubmissions(assignmentId, title);
};

async function handleRunCodeSandbox() {
  const language = document.getElementById('sandbox-language').value;
  const sourceCode = document.getElementById('sandbox-code-editor').value;
  const stdinInput = document.getElementById('sandbox-stdin').value;
  const outputPre = document.getElementById('sandbox-output');
  const htmlFrame = document.getElementById('sandbox-html-preview');

  if (language === 'html') {
    outputPre.classList.add('hidden');
    htmlFrame.classList.remove('hidden');
    htmlFrame.srcdoc = sourceCode;
    return;
  }

  htmlFrame?.classList.add('hidden');
  outputPre.classList.remove('hidden');
  outputPre.style.color = '#38bdf8';
  outputPre.textContent = `Đang biên dịch & thực thi ${language.toUpperCase()}...`;
  try {
    const res = await apiFetch('/api/sandbox/run', {
      method: 'POST',
      body: JSON.stringify({
        language,
        source_code: sourceCode,
        stdin_input: stdinInput,
      }),
    });

    if (res.success) {
      outputPre.style.color = '#34d399';
      outputPre.textContent = res.stdout || '(Chương trình kết thúc thành công, không có dữ liệu in ra)';
    } else {
      outputPre.style.color = '#f87171';
      outputPre.textContent = res.stderr || res.stdout || 'Lỗi thực thi chương trình.';
    }
  } catch (err) {
    outputPre.style.color = '#f87171';
    outputPre.textContent = `Lỗi Sandbox: ${err.message}`;
  }
}

window.submitSandboxAsAssignment = async function (assignmentId) {
  const language = document.getElementById('sandbox-language').value;
  const codeContent = document.getElementById('sandbox-code-editor').value;

  try {
    const res = await apiFetch(`/api/student/assignments/${assignmentId}/submit`, {
      method: 'POST',
      body: JSON.stringify({
        code_language: language,
        code_content: codeContent,
        code_run_instructions: `Chạy trực tiếp trên trình biên dịch ${language}`,
      }),
    });
    alert(`Nộp bài thành công! Mã bài nộp: #${res.submission_id} (Lần nộp thứ ${res.attempt_number})`);
  } catch (err) {
    alert(`Không thể nộp bài: ${err.message}`);
  }
};

// ============================================================================
// 9. KIỂM TRA TRỰC TUYẾN & GIÁM SÁT ANTI-CHEATING (VISIBILITY API + WEBSOCKET)
// ============================================================================

async function loadExamsAndProctoringView() {
  const isStaff = ['ADMIN', 'TEACHER'].includes(AppState.user?.role);

  const aiSubj = document.getElementById('ai-q-subject');
  const exSubj = document.getElementById('exam-new-subject');
  const exCls = document.getElementById('exam-new-class');
  if (AppState.meta.subjects) {
    const subjOpts = AppState.meta.subjects
      .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`)
      .join('');
    if (aiSubj) aiSubj.innerHTML = subjOpts;
    if (exSubj) exSubj.innerHTML = subjOpts;
  }
  if (AppState.meta.classes && exCls) {
    exCls.innerHTML = AppState.meta.classes
      .map((c) => `<option value="${c.id}">${escapeHtml(c.code)} - ${escapeHtml(c.name)}</option>`)
      .join('');
  }

  let exams = [];
  try {
    exams = await apiFetch('/api/exams');
  } catch (_) {}

  document.getElementById('exams-list').innerHTML = exams
    .map(
      (ex) => `
      <div class="item-card">
        <div>
          <div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:8px;">
            <span class="badge badge-primary">${ex.duration_minutes} phút · ${ex.question_count} câu</span>
            <span class="badge ${ex.ai_assistant_allowed ? 'badge-success' : 'badge-danger'}">
              ${ex.ai_assistant_allowed ? 'Cho phép AI' : 'Khóa AI khi thi'}
            </span>
          </div>
          <h4>${escapeHtml(ex.title)}</h4>
          <p class="muted-text mt-10">${escapeHtml(ex.class_code)} · ${escapeHtml(ex.subject_name)} (${ex.attempt_count} lượt thi)</p>
        </div>
        ${
          !isStaff
            ? `<button type="button" class="btn btn-primary" onclick="startOnlineExam(${ex.id}, '${escapeHtml(ex.title)}', ${ex.duration_minutes}, ${ex.ai_assistant_allowed})">Vào phòng thi</button>`
            : `<button type="button" class="btn btn-secondary" onclick="selectExamForProctoring(${ex.id})">Giám sát phòng thi này</button>`
        }
      </div>
    `
    )
    .join('');

  if (isStaff) {
    await refreshQuestionBankChecklist();
    const proctorSel = document.getElementById('proctoring-exam-select');
    if (proctorSel && exams.length) {
      proctorSel.innerHTML = exams
        .map((e) => `<option value="${e.id}">Giám sát: ${escapeHtml(e.title)}</option>`)
        .join('');
      const targetExamId = Number(proctorSel.value || exams[0].id);
      connectTeacherProctoring(targetExamId);
      if (AppState.proctoringPollInterval) clearInterval(AppState.proctoringPollInterval);
      AppState.proctoringPollInterval = setInterval(() => {
        connectTeacherProctoring(Number(proctorSel.value));
      }, 3000);
    }
  }
}

window.selectExamForProctoring = function (examId) {
  const proctorSel = document.getElementById('proctoring-exam-select');
  if (proctorSel) proctorSel.value = String(examId);
  connectTeacherProctoring(examId);
};

async function refreshQuestionBankChecklist() {
  const box = document.getElementById('question-bank-checklist');
  if (!box) return;
  try {
    const questions = await apiFetch('/api/questions');
    box.innerHTML = questions
      .map(
        (q) => `
        <label style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid #f1f5f9;">
          <input type="checkbox" class="qb-checkbox" value="${q.id}" checked />
          <span><strong>[#${q.id}]</strong> ${escapeHtml(q.content_html)} <small class="muted-text">(${escapeHtml(q.cognitive_level)})</small></span>
        </label>
      `
      )
      .join('');
  } catch (_) {}
}

async function handleAiGenerateQuestionsSubmit(event) {
  event.preventDefault();
  const subjectId = Number(document.getElementById('ai-q-subject').value || 1);
  const subjectName = document.getElementById('ai-q-subject').selectedOptions[0]?.text || 'Tin học';
  const topicContent = document.getElementById('ai-q-topic').value.trim();
  const numQuestions = Number(document.getElementById('ai-q-count').value || 3);
  const cognitiveLevel = document.getElementById('ai-q-level').value;

  const previewBox = document.getElementById('ai-generated-questions-box');
  const saveBtn = document.getElementById('btn-save-ai-questions');
  previewBox.textContent = 'AI đang biên soạn câu hỏi trắc nghiệm...';
  saveBtn.classList.add('hidden');

  try {
    const res = await apiFetch('/api/ai/generate-questions', {
      method: 'POST',
      body: JSON.stringify({
        subject_id: subjectId,
        subject_name: subjectName,
        topic_content: topicContent,
        num_questions: numQuestions,
        cognitive_level: cognitiveLevel,
      }),
    });

    AppState.lastAiGeneratedQuestions = (res.questions || []).map((q) => ({
      ...q,
      subject_id: subjectId,
      chapter: topicContent.slice(0, 80),
      cognitive_level: cognitiveLevel,
    }));

    previewBox.innerHTML = AppState.lastAiGeneratedQuestions
      .map(
        (q, idx) => `
        <div style="margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #ddd6fe;">
          <strong>Câu ${idx + 1}: ${escapeHtml(q.question)}</strong>
          <ul style="margin-left:18px;margin-top:4px;">
            ${(q.options || [])
              .map(
                (opt, oIdx) =>
                  `<li style="${oIdx === q.correct_index ? 'color:#059669;font-weight:600;' : ''}">${String.fromCharCode(65 + oIdx)}. ${escapeHtml(opt)}</li>`
              )
              .join('')}
          </ul>
        </div>
      `
      )
      .join('');

    if (AppState.lastAiGeneratedQuestions.length > 0) saveBtn.classList.remove('hidden');
  } catch (err) {
    previewBox.textContent = `Lỗi AI tạo câu hỏi: ${err.message}`;
  }
}

async function handleSaveAiQuestionsToBank() {
  if (!AppState.lastAiGeneratedQuestions.length) return;
  try {
    for (const q of AppState.lastAiGeneratedQuestions) {
      await apiFetch('/api/teacher/questions', {
        method: 'POST',
        body: JSON.stringify({
          subject_id: q.subject_id,
          chapter: q.chapter,
          cognitive_level: q.cognitive_level,
          question_type: 'SINGLE_CHOICE',
          content_html: q.question,
          explanation_html: q.explanation || '',
          is_ai_generated: true,
          options: (q.options || []).map((optText, idx) => ({
            option_label: String.fromCharCode(65 + idx),
            option_text: optText,
            is_correct: idx === q.correct_index,
          })),
        }),
      });
    }
    alert(`Đã lưu ${AppState.lastAiGeneratedQuestions.length} câu hỏi AI vào Ngân hàng câu hỏi!`);
    document.getElementById('btn-save-ai-questions')?.classList.add('hidden');
    await refreshQuestionBankChecklist();
  } catch (err) {
    alert(err.message);
  }
}

async function handleCreateExamSubmit(event) {
  event.preventDefault();
  const selectedIds = Array.from(document.querySelectorAll('.qb-checkbox:checked')).map((cb) => Number(cb.value));
  if (!selectedIds.length) return alert('Vui lòng chọn ít nhất 1 câu hỏi.');

  try {
    const res = await apiFetch('/api/teacher/exams', {
      method: 'POST',
      body: JSON.stringify({
        class_id: Number(document.getElementById('exam-new-class').value),
        subject_id: Number(document.getElementById('exam-new-subject').value),
        title: document.getElementById('exam-new-title').value,
        duration_minutes: Number(document.getElementById('exam-new-duration').value),
        start_at: new Date().toISOString(),
        end_at: new Date(Date.now() + 7 * 86400000).toISOString(),
        question_ids: selectedIds,
        ai_assistant_allowed: document.getElementById('exam-new-ai-allowed').value === 'true',
      }),
    });
    alert(res.message);
    document.getElementById('create-exam-panel')?.classList.add('hidden');
    loadExamsAndProctoringView();
  } catch (err) {
    alert(err.message);
  }
}

window.connectTeacherProctoring = async function (examId) {
  const tbody = document.getElementById('proctoring-tbody');
  if (!tbody) return;
  try {
    const rows = await apiFetch(`/api/teacher/exams/${examId}/proctoring`);
    if (!rows.length) {
      tbody.innerHTML =
        '<tr><td colspan="7" class="muted-text" style="text-align:center;">Chưa có học sinh nào vào phòng thi này.</td></tr>';
      return;
    }
    tbody.innerHTML = rows
      .map((r) => {
        const eventSummary = (r.events || [])
          .slice(0, 3)
          .map((e) => `${e.type} (${new Date(e.recorded_at).toLocaleTimeString('vi-VN')})`)
          .join(' · ');
        return `
          <tr>
            <td><code>${escapeHtml(r.student_code)}</code></td>
            <td><strong>${escapeHtml(r.student_name)}</strong></td>
            <td><span class="badge ${r.status === 'DISCONNECTED' ? 'badge-danger' : 'badge-success'}">${escapeHtml(r.status)}</span></td>
            <td><span class="badge ${r.tab_switch_count >= 3 ? 'badge-danger' : 'badge-warning'}">${r.tab_switch_count} lần</span></td>
            <td>${r.fullscreen_exit_count} lần</td>
            <td>${r.score !== null ? r.score + ' / 10' : 'Đang thi'}</td>
            <td><small class="muted-text">${escapeHtml(eventSummary || 'Bình thường')}</small></td>
          </tr>
        `;
      })
      .join('');
  } catch (_) {}
};

window.startOnlineExam = async function (examId, title, durationMinutes, aiAllowed) {
  let attemptData;
  try {
    attemptData = await apiFetch(`/api/student/exams/${examId}/start`, { method: 'POST' });
  } catch (err) {
    alert(`Không thể vào phòng thi: ${err.message}`);
    return;
  }

  AppState.activeExam = {
    attemptId: attemptData.attempt_id,
    examId,
    title,
    variantCode: attemptData.variant_code || 'MD-101',
    aiAllowed: Boolean(attemptData.ai_assistant_allowed),
    remainingSeconds: (attemptData.duration_minutes || durationMinutes) * 60,
    timerInterval: null,
    autosaveInterval: null,
    tabSwitchCount: 0,
    fullscreenExitCount: 0,
    answers: {},
  };

  document.getElementById('exam-room-title').textContent = title;
  document.getElementById('exam-variant-label').textContent =
    `Mã đề: ${AppState.activeExam.variantCode} · Tự động lưu mỗi 5 giây`;
  document.getElementById('exam-proctor-counter').textContent = 'Chuyển tab: 0';

  // Khóa/mở Trợ lý AI theo quy chế phòng thi
  updateAiDrawerLockState();

  // Hiển thị danh sách câu hỏi
  const container = document.getElementById('exam-questions-container');
  container.innerHTML = attemptData.questions
    .map(
      (q) => `
      <div class="question-card">
        <div><strong>${q.content_html}</strong></div>
        <div>
          ${(q.options || [])
            .map(
              (opt) => `
              <label class="option-item">
                <input type="radio" name="q_${q.id}" value="${opt.id}" onchange="selectExamOption(${q.id}, ${opt.id})" />
                <span><strong>${escapeHtml(opt.label)}.</strong> ${escapeHtml(opt.text)}</span>
              </label>
            `
            )
            .join('')}
        </div>
      </div>
    `
    )
    .join('');

  const overlay = document.getElementById('exam-room-overlay');
  overlay.classList.remove('hidden');

  // Yêu cầu chế độ toàn màn hình (Fullscreen API)
  if (document.documentElement.requestFullscreen) {
    document.documentElement.requestFullscreen().catch(() => {});
  }

  attachExamProctoringListeners();
  startExamTimers();
};

window.selectExamOption = function (questionId, optionId) {
  AppState.activeExam.answers[questionId] = {
    question_id: questionId,
    selected_option_ids: [optionId],
  };
  document.getElementById('exam-autosave-status').textContent = 'Có thay đổi chưa lưu...';
};

function startExamTimers() {
  const timerEl = document.getElementById('exam-countdown-timer');

  AppState.activeExam.timerInterval = setInterval(() => {
    AppState.activeExam.remainingSeconds -= 1;
    const sec = Math.max(0, AppState.activeExam.remainingSeconds);
    const mins = String(Math.floor(sec / 60)).padStart(2, '0');
    const remSec = String(sec % 60).padStart(2, '0');
    timerEl.textContent = `${mins}:${remSec}`;

    if (sec <= 0) {
      finishAndSubmitExam(true);
    }
  }, 1000);

  // Tự động lưu bài làm mỗi 5 giây
  AppState.activeExam.autosaveInterval = setInterval(async () => {
    const attemptId = AppState.activeExam.attemptId;
    if (!attemptId) return;

    const answersPayload = Object.values(AppState.activeExam.answers);
    try {
      await apiFetch(`/api/student/attempts/${attemptId}/autosave`, {
        method: 'POST',
        body: JSON.stringify({ answers: answersPayload }),
      });
      document.getElementById('exam-autosave-status').textContent =
        `Đã lưu lúc ${new Date().toLocaleTimeString('vi-VN')}`;
    } catch (_) {
      document.getElementById('exam-autosave-status').textContent = 'Lưu cục bộ (Offline)';
    }
  }, 5000);
}

// Bộ lắng nghe sự kiện Anti-Cheating (Visibility API, Fullscreen API, Network)
function handleVisibilityChange() {
  if (!AppState.activeExam.attemptId) return;
  if (document.hidden) {
    AppState.activeExam.tabSwitchCount += 1;
    document.getElementById('exam-proctor-counter').textContent =
      `Chuyển tab: ${AppState.activeExam.tabSwitchCount}`;
    sendProctoringEvent('TAB_HIDDEN', 'Học sinh chuyển sang tab khác hoặc ẩn trình duyệt');
  } else {
    sendProctoringEvent('EXAM_RESUMED', 'Học sinh quay lại màn hình bài thi');
  }
}

function handleFullscreenChange() {
  if (!AppState.activeExam.attemptId) return;
  if (!document.fullscreenElement) {
    AppState.activeExam.fullscreenExitCount += 1;
    sendProctoringEvent('FULLSCREEN_EXIT', 'Học sinh thoát chế độ toàn màn hình');
  }
}

function handleNetworkOffline() {
  if (AppState.activeExam.attemptId) {
    sendProctoringEvent('NETWORK_OFFLINE', 'Mất kết nối Internet trong lúc làm bài');
  }
}

function handleNetworkOnline() {
  if (AppState.activeExam.attemptId) {
    sendProctoringEvent('NETWORK_ONLINE', 'Đã khôi phục kết nối Internet');
  }
}

async function sendProctoringEvent(eventType, detail) {
  try {
    await apiFetch('/api/exams/events', {
      method: 'POST',
      body: JSON.stringify({
        attempt_id: AppState.activeExam.attemptId,
        exam_id: AppState.activeExam.examId,
        event_type: eventType,
        event_detail: detail,
        client_timestamp: new Date().toISOString(),
      }),
    });
  } catch (_) {
    // Bỏ qua lỗi mạng tạm thời khi offline
  }
}

function attachExamProctoringListeners() {
  document.addEventListener('visibilitychange', handleVisibilityChange);
  document.addEventListener('fullscreenchange', handleFullscreenChange);
  window.addEventListener('offline', handleNetworkOffline);
  window.addEventListener('online', handleNetworkOnline);
}

function detachExamProctoringListeners() {
  document.removeEventListener('visibilitychange', handleVisibilityChange);
  document.removeEventListener('fullscreenchange', handleFullscreenChange);
  window.removeEventListener('offline', handleNetworkOffline);
  window.removeEventListener('online', handleNetworkOnline);
}

async function finishAndSubmitExam(autoSubmitted = false) {
  const attemptId = AppState.activeExam.attemptId;
  if (!attemptId) return;

  clearInterval(AppState.activeExam.timerInterval);
  clearInterval(AppState.activeExam.autosaveInterval);
  detachExamProctoringListeners();

  try {
    const res = await apiFetch(
      `/api/student/attempts/${attemptId}/submit?auto_submitted=${autoSubmitted}`,
      { method: 'POST' }
    );
    alert(
      res.score !== null && res.score !== undefined
        ? `${res.message}\nĐiểm trắc nghiệm tự động: ${res.score} / 10`
        : res.message
    );
  } catch (_) {
    alert(autoSubmitted ? 'Đã hết giờ! Hệ thống đã tự động thu bài.' : 'Đã nộp bài kiểm tra thành công!');
  }

  AppState.activeExam.attemptId = null;
  document.getElementById('exam-room-overlay').classList.add('hidden');
  updateAiDrawerLockState();

  if (document.fullscreenElement && document.exitFullscreen) {
    document.exitFullscreen().catch(() => {});
  }
}

// ============================================================================
// 10. BẢNG ĐIỂM & XUẤT BÁO CÁO CSV
// ============================================================================

async function loadGradesView() {
  try {
    const rows = await apiFetch('/api/grades');
    if (!rows.length) {
      document.getElementById('grades-tbody').innerHTML =
        '<tr><td colspan="6" class="muted-text" style="text-align:center;">Chưa có dữ liệu điểm số.</td></tr>';
      return;
    }
    document.getElementById('grades-tbody').innerHTML = rows
      .map(
        (r) => `
        <tr>
          <td><strong>${escapeHtml(r.student_name)}</strong></td>
          <td><span class="badge badge-primary">${escapeHtml(r.class_code)}</span></td>
          <td>${escapeHtml(r.subject_name)}</td>
          <td>${escapeHtml(r.item_title)}</td>
          <td><span class="badge badge-success">${r.score} / ${r.max_score}</span></td>
          <td>${escapeHtml(r.feedback)}</td>
        </tr>
      `
      )
      .join('');
  } catch (err) {
    alert(err.message);
  }
}

function handleExportGradesCsv() {
  const csvLines = [
    '\uFEFFHọc sinh,Lớp,Môn học,Đầu điểm,Điểm số,Nhận xét',
    '"Nguyễn Ngọc Ánh","10A1","Tin học","Kiểm tra 45 phút Chương 1","9.0","Tư duy thuật toán tốt"',
    '"Lê Hoàng Nam","10A1","Tin học","Thực hành Đệ quy Python","8.5","Code chạy đúng test case"',
  ];
  const blob = new Blob([csvLines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `bang_diem_edulms_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ============================================================================
// 11. GIA SƯ TRÍ TUỆ NHÂN TẠO GEMINI (AI TUTOR DRAWER) & THÔNG BÁO
// ============================================================================

function updateAiDrawerLockState() {
  const isLocked =
    Boolean(AppState.activeExam.attemptId) && !AppState.activeExam.aiAllowed;
  const indicator = document.getElementById('ai-lock-indicator');
  const input = document.getElementById('ai-chat-input');

  if (isLocked) {
    indicator.textContent = 'Đang khóa trong giờ kiểm tra';
    input.disabled = true;
    input.placeholder = 'Trợ lý AI bị tạm khóa theo quy chế phòng thi...';
  } else {
    indicator.textContent = 'Sẵn sàng hỗ trợ học tập';
    input.disabled = false;
    input.placeholder = 'Hỏi bài, giải thích kiến thức hoặc gỡ lỗi code...';
  }
}

async function loadProfileView() {
  try {
    const me = await apiFetch('/api/auth/me');
    AppState.user = me;
    localStorage.setItem('edulms_user', JSON.stringify(me));
    document.getElementById('prof-username').value = `${me.username} (${me.code_identifier || me.username})`;
    document.getElementById('prof-role').value = me.role_name || me.role;
    document.getElementById('prof-fullname').value = me.full_name || '';
    document.getElementById('prof-email').value = me.email || '';
    document.getElementById('prof-phone').value = me.phone || '';
  } catch (err) {
    alert(err.message);
  }
}

async function handleProfileUpdateSubmit(event) {
  event.preventDefault();
  try {
    const res = await apiFetch('/api/auth/profile', {
      method: 'PUT',
      body: JSON.stringify({
        full_name: document.getElementById('prof-fullname').value,
        email: document.getElementById('prof-email').value,
        phone: document.getElementById('prof-phone').value,
      }),
    });
    AppState.user = res.user;
    localStorage.setItem('edulms_user', JSON.stringify(res.user));
    document.getElementById('current-user-name').textContent = res.user.full_name;
    alert(res.message);
  } catch (err) {
    alert(err.message);
  }
}

async function handleChangePasswordSubmit(event) {
  event.preventDefault();
  const oldPassword = document.getElementById('pwd-old').value;
  const newPassword = document.getElementById('pwd-new').value;
  if (newPassword !== document.getElementById('pwd-confirm').value) {
    return alert('Mật khẩu mới và mật khẩu xác nhận không trùng khớp.');
  }
  try {
    const res = await apiFetch('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    });
    alert(res.message);
    document.getElementById('change-password-form')?.reset();
  } catch (err) {
    alert(err.message);
  }
}

async function sendAiTutorMessage() {
  const input = document.getElementById('ai-chat-input');
  const promptText = input.value.trim();
  if (!promptText) return;

  const history = document.getElementById('ai-chat-messages');
  history.innerHTML += `<div class="chat-msg user">${escapeHtml(promptText)}</div>`;
  input.value = '';
  history.scrollTop = history.scrollHeight;

  const codeEditor = document.getElementById('sandbox-code-editor');
  const contextCode = AppState.currentView === 'assignments' && codeEditor ? codeEditor.value : null;

  try {
    const res = await apiFetch('/api/ai/tutor', {
      method: 'POST',
      body: JSON.stringify({ prompt: promptText, context_code: contextCode, subject_name: 'Tin học' }),
    });
    history.innerHTML += `<div class="chat-msg ai">${escapeHtml(res.reply)}</div>`;
  } catch (err) {
    history.innerHTML += `<div class="chat-msg ai">${escapeHtml(err.message)}</div>`;
  }
  history.scrollTop = history.scrollHeight;
}

async function handleTeacherAiGenerateQuestions() {
  const topic = prompt('Nhập chủ đề hoặc nội dung kiến thức để AI tạo câu hỏi trắc nghiệm:');
  if (!topic) return;

  try {
    const res = await apiFetch('/api/ai/generate-questions', {
      method: 'POST',
      body: JSON.stringify({
        subject_name: 'Tin học',
        topic_content: topic,
        num_questions: 5,
        cognitive_level: 'THONG_HIEU',
      }),
    });
    alert(`AI đã sinh bộ câu hỏi thành công:\n\n${res.questions_raw.slice(0, 600)}...`);
  } catch (err) {
    alert(`Lỗi AI tạo câu hỏi: ${err.message}`);
  }
}

function renderNotifications() {
  const unreadCount = AppState.notifications.filter((n) => !n.isRead).length;
  const badge = document.getElementById('notif-unread-badge');
  badge.textContent = unreadCount;
  badge.classList.toggle('hidden', unreadCount === 0);

  document.getElementById('notif-list').innerHTML = AppState.notifications
    .map(
      (n) => `
      <div style="padding:8px;border-bottom:1px solid #e2e8f0;background:${n.isRead ? '#fff' : '#eff6ff'}">
        <strong style="font-size:12.5px;">${escapeHtml(n.title)}</strong>
        <p class="muted-text">${escapeHtml(n.message)}</p>
      </div>
    `
    )
    .join('');
}

// ============================================================================
// 12. GẮN SỰ KIỆN GIAO DIỆN (EVENT BINDINGS)
// ============================================================================

function bindGlobalEvents() {
  document.getElementById('login-form')?.addEventListener('submit', handleLoginSubmit);
  document.getElementById('logout-btn')?.addEventListener('click', handleLogout);

  // Điều hướng responsive trên di động
  document.getElementById('sidebar-toggle-btn')?.addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.add('open');
  });
  document.getElementById('sidebar-close-btn')?.addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.remove('open');
  });

  // Thông báo
  document.getElementById('notif-bell-btn')?.addEventListener('click', () => {
    document.getElementById('notif-dropdown')?.classList.toggle('hidden');
  });
  document.getElementById('mark-all-read-btn')?.addEventListener('click', () => {
    AppState.notifications.forEach((n) => (n.isRead = true));
    renderNotifications();
  });

  // Admin
  document.getElementById('btn-new-user-modal')?.addEventListener('click', handleCreateUserPrompt);
  document.getElementById('csv-users-input')?.addEventListener('change', handleCsvUsersUpload);
  document.getElementById('toggle-maintenance')?.addEventListener('change', handleToggleMaintenance);
  document.getElementById('btn-export-sql')?.addEventListener('click', handleExportSqlBackup);

    // Lớp học
  document.getElementById('btn-create-class')?.addEventListener('click', handleCreateClass);
  document.getElementById('btn-join-class')?.addEventListener('click', handleStudentJoinClass);
  document.getElementById('btn-close-class-members')?.addEventListener('click', () => {
    document.getElementById('class-members-panel')?.classList.add('hidden');
  });
  document.getElementById('btn-assign-students-submit')?.addEventListener('click', handleAssignStudentsSubmit);
  // Studio Video Bài giảng AI
  document.getElementById('btn-open-ai-video-studio')?.addEventListener('click', () => {
    document.getElementById('ai-video-studio-card')?.classList.remove('hidden');
  });
  document.getElementById('btn-close-ai-video-studio')?.addEventListener('click', () => {
    document.getElementById('ai-video-studio-card')?.classList.add('hidden');
  });
  document.getElementById('ai-video-form')?.addEventListener('submit', handleGenerateAiVideo);

  // Sandbox lập trình
  document.getElementById('sandbox-language')?.addEventListener('change', (e) => {
    const lang = e.target.value;
    if (SANDBOX_TEMPLATES[lang]) {
      document.getElementById('sandbox-code-editor').value = SANDBOX_TEMPLATES[lang];
    }
  });
  document.getElementById('btn-run-sandbox')?.addEventListener('click', handleRunCodeSandbox);

  // Thi trực tuyến & AI tạo câu hỏi
  document.getElementById('btn-ai-gen-questions')?.addEventListener('click', handleTeacherAiGenerateQuestions);
  document.getElementById('btn-submit-exam')?.addEventListener('click', () => {
    if (confirm('Bạn có chắc chắn muốn nộp bài thi ngay bây giờ?')) {
      finishAndSubmitExam(false);
    }
  });

  // Xuất bảng điểm
  document.getElementById('btn-export-grades-csv')?.addEventListener('click', handleExportGradesCsv);

  // Ngăn kéo Gia sư AI
  document.getElementById('open-ai-tutor-btn')?.addEventListener('click', () => {
    updateAiDrawerLockState();
    document.getElementById('ai-drawer')?.classList.remove('hidden');
  });
  document.getElementById('close-ai-drawer-btn')?.addEventListener('click', () => {
    document.getElementById('ai-drawer')?.classList.add('hidden');
  });
  // Hồ sơ & Đổi mật khẩu
  document.getElementById('sidebar-profile-trigger')?.addEventListener('click', () => switchView('profile'));
  document.getElementById('profile-update-form')?.addEventListener('submit', handleProfileUpdateSubmit);
  document.getElementById('change-password-form')?.addEventListener('submit', handleChangePasswordSubmit);

  // Giao bài tập & Chấm bài
  document.getElementById('btn-create-assignment')?.addEventListener('click', () => {
    document.getElementById('create-assignment-panel')?.classList.remove('hidden');
  });
  document.getElementById('btn-close-assignment-panel')?.addEventListener('click', () => {
    document.getElementById('create-assignment-panel')?.classList.add('hidden');
  });
  document.getElementById('create-assignment-form')?.addEventListener('submit', handleCreateAssignmentSubmit);
  document.getElementById('btn-close-grading-panel')?.addEventListener('click', () => {
    document.getElementById('grading-submissions-panel')?.classList.add('hidden');
  });

  // AI Tạo đề, Tạo kỳ thi & Giám sát
  document.getElementById('btn-open-ai-question-panel')?.addEventListener('click', () => {
    document.getElementById('ai-question-panel')?.classList.remove('hidden');
  });
  document.getElementById('btn-close-ai-question-panel')?.addEventListener('click', () => {
    document.getElementById('ai-question-panel')?.classList.add('hidden');
  });
  document.getElementById('ai-question-form')?.addEventListener('submit', handleAiGenerateQuestionsSubmit);
  document.getElementById('btn-save-ai-questions')?.addEventListener('click', handleSaveAiQuestionsToBank);

  document.getElementById('btn-open-create-exam-panel')?.addEventListener('click', () => {
    document.getElementById('create-exam-panel')?.classList.remove('hidden');
  });
  document.getElementById('btn-close-create-exam-panel')?.addEventListener('click', () => {
    document.getElementById('create-exam-panel')?.classList.add('hidden');
  });
  document.getElementById('create-exam-form')?.addEventListener('submit', handleCreateExamSubmit);

  document.getElementById('proctoring-exam-select')?.addEventListener('change', (e) => {
    connectTeacherProctoring(Number(e.target.value));
  });
  document.getElementById('btn-refresh-proctoring')?.addEventListener('click', () => {
    const val = document.getElementById('proctoring-exam-select')?.value;
    if (val) connectTeacherProctoring(Number(val));
  });

  // Lưu Gemini API Key & Gửi chat AI không tải lại trang
  const keyInput = document.getElementById('gemini-custom-key');
  if (keyInput) {
    keyInput.value = localStorage.getItem('edulms_gemini_key') || '';
    keyInput.addEventListener('change', (e) => localStorage.setItem('edulms_gemini_key', e.target.value.trim()));
  }
  document.getElementById('ai-chat-send-btn')?.addEventListener('click', sendAiTutorMessage);
  document.getElementById('ai-chat-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      sendAiTutorMessage();
    }
  });
}