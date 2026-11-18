-- ============================================================================
-- HỆ THỐNG QUẢN LÝ HỌC TẬP TRỰC TUYẾN (EDULMS PRO)
-- Tệp: database/schema.sql
-- Hệ quản trị CSDL: PostgreSQL 15+ (Tương thích chuẩn ANSI SQL)
-- Mô tả: Thiết kế CSDL đầy đủ cho Admin, Giáo viên, Học sinh, Bài tập,
--        Ngân hàng đề, Thi trực tuyến, Giám sát Anti-Cheating và Trợ lý AI.
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. CẤU HÌNH HỆ THỐNG, TÀI KHOẢN & PHÂN QUYỀN
-- ============================================================================

CREATE TABLE system_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    code VARCHAR(30) UNIQUE NOT NULL, -- 'ADMIN', 'TEACHER', 'STUDENT'
    name VARCHAR(100) NOT NULL,
    description TEXT,
    permissions JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(150) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    avatar_url TEXT,
    phone VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    must_change_password BOOLEAN DEFAULT FALSE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    is_revoked BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 2. NĂM HỌC, KHỐI LỚP, MÔN HỌC & HỒ SƠ GIÁO VIÊN / HỌC SINH
-- ============================================================================

CREATE TABLE academic_years (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL, -- VD: '2025-2026', '2026-2027'
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE grade_levels (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL, -- 'K10', 'K11', 'K12'
    name VARCHAR(50) NOT NULL         -- 'Khối 10', 'Khối 11', 'Khối 12'
);

CREATE TABLE subjects (
    id SERIAL PRIMARY KEY,
    code VARCHAR(30) UNIQUE NOT NULL, -- 'TIN', 'TOAN', 'VAN', 'ANH'
    name VARCHAR(100) NOT NULL,
    description TEXT,
    color_hex VARCHAR(7) DEFAULT '#2563EB',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE teachers (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    teacher_code VARCHAR(50) UNIQUE NOT NULL, -- VD: 'GV001'
    department VARCHAR(100),
    specialization VARCHAR(150),
    can_create_class BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE students (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    student_code VARCHAR(50) UNIQUE NOT NULL, -- VD: 'HS2026001'
    date_of_birth DATE,
    gender VARCHAR(15),
    guardian_name VARCHAR(150),
    guardian_phone VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classes (
    id BIGSERIAL PRIMARY KEY,
    academic_year_id INT NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
    grade_level_id INT NOT NULL REFERENCES grade_levels(id) ON DELETE RESTRICT,
    homeroom_teacher_id BIGINT REFERENCES teachers(id) ON DELETE SET NULL,
    code VARCHAR(30) NOT NULL,                -- VD: '10A1', '11A2'
    name VARCHAR(100) NOT NULL,
    join_code VARCHAR(12) UNIQUE NOT NULL,    -- Mã tham gia lớp học
    description TEXT,
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (academic_year_id, code)
);

CREATE TABLE class_members (
    id BIGSERIAL PRIMARY KEY,
    class_id BIGINT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'ACTIVE', -- 'ACTIVE', 'TRANSFERRED', 'DROPPED'
    UNIQUE (class_id, student_id)
);

CREATE TABLE teaching_assignments (
    id BIGSERIAL PRIMARY KEY,
    academic_year_id INT NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    class_id BIGINT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    subject_id INT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    teacher_id BIGINT NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (academic_year_id, class_id, subject_id, teacher_id)
);

-- ============================================================================
-- 3. KHÓA HỌC, BÀI GIẢNG & NGÂN HÀNG TÀI LIỆU
-- ============================================================================

CREATE TABLE courses (
    id BIGSERIAL PRIMARY KEY,
    academic_year_id INT NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    class_id BIGINT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    subject_id INT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    teacher_id BIGINT NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    cover_image_url TEXT,
    is_published BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE lessons (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    chapter_name VARCHAR(150),
    title VARCHAR(200) NOT NULL,
    content_html TEXT,
    video_url TEXT,
    order_index INT DEFAULT 0,
    is_published BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE materials (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT REFERENCES courses(id) ON DELETE SET NULL,
    lesson_id BIGINT REFERENCES lessons(id) ON DELETE SET NULL,
    subject_id INT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    grade_level_id INT REFERENCES grade_levels(id) ON DELETE SET NULL,
    uploaded_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    chapter_tag VARCHAR(100),
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(30) NOT NULL, -- 'PDF', 'DOCX', 'PPTX', 'XLSX', 'ZIP', 'IMAGE', 'VIDEO', 'AI_VIDEO'
    file_size_bytes BIGINT NOT NULL DEFAULT 0,
    version_number INT DEFAULT 1,
    allow_download BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE material_bookmarks (
    id BIGSERIAL PRIMARY KEY,
    material_id BIGINT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (material_id, student_id)
);

-- ============================================================================
-- 4. QUẢN LÝ BÀI TẬP, NỘP BÀI & LẬP TRÌNH SANDBOX
-- ============================================================================

CREATE TABLE assignments (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    class_id BIGINT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    subject_id INT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    teacher_id BIGINT NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
    title VARCHAR(255) NOT NULL,
    instructions TEXT NOT NULL,
    rubric_text TEXT,
    -- Hình thức nộp: 'FILE', 'TEXT', 'QUIZ', 'TRUE_FALSE', 'SHORT_ANSWER', 'ESSAY', 'CODE', 'LINK', 'MIXED'
    submission_types JSONB NOT NULL DEFAULT '["FILE"]'::jsonb,
    allowed_code_languages JSONB DEFAULT '["python", "cpp", "c", "java", "javascript", "html"]'::jsonb,
    starter_code TEXT,
    max_score NUMERIC(6,2) NOT NULL DEFAULT 10.00,
    max_attempts INT NOT NULL DEFAULT 1,
    allow_late_submission BOOLEAN DEFAULT FALSE,
    ai_tutor_enabled BOOLEAN DEFAULT TRUE,
    start_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    due_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE assignment_files (
    id BIGSERIAL PRIMARY KEY,
    assignment_id BIGINT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(30),
    file_size_bytes BIGINT DEFAULT 0,
    allow_student_download BOOLEAN DEFAULT TRUE,
    uploaded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE submissions (
    id BIGSERIAL PRIMARY KEY,
    assignment_id BIGINT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    attempt_number INT NOT NULL DEFAULT 1,
    -- Trạng thái: 'NOT_STARTED', 'IN_PROGRESS', 'SUBMITTED', 'LATE_SUBMITTED', 'GRADED', 'REVISION_REQUESTED'
    status VARCHAR(30) NOT NULL DEFAULT 'IN_PROGRESS',
    text_answer TEXT,
    code_language VARCHAR(30),
    code_content TEXT,
    code_run_instructions TEXT,
    external_link TEXT,
    submitted_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (assignment_id, student_id, attempt_number)
);

CREATE TABLE submission_files (
    id BIGSERIAL PRIMARY KEY,
    submission_id BIGINT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(30),
    file_size_bytes BIGINT DEFAULT 0,
    uploaded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 5. NGÂN HÀNG CÂU HỎI & KIỂM TRA TRỰC TUYẾN
-- ============================================================================

CREATE TABLE exams (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    class_id BIGINT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    subject_id INT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    teacher_id BIGINT NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    duration_minutes INT NOT NULL DEFAULT 45,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    max_attempts INT NOT NULL DEFAULT 1,
    total_score NUMERIC(6,2) NOT NULL DEFAULT 10.00,
    shuffle_questions BOOLEAN DEFAULT TRUE,
    shuffle_options BOOLEAN DEFAULT TRUE,
    allow_backtrack BOOLEAN DEFAULT TRUE,
    show_score_immediately BOOLEAN DEFAULT TRUE,
    publish_answers BOOLEAN DEFAULT FALSE,
    ai_assistant_allowed BOOLEAN DEFAULT FALSE, -- Tắt AI mặc định trong phòng thi
    require_fullscreen BOOLEAN DEFAULT TRUE,
    tab_switch_warning_threshold INT DEFAULT 3,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE questions (
    id BIGSERIAL PRIMARY KEY,
    subject_id INT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    grade_level_id INT REFERENCES grade_levels(id) ON DELETE SET NULL,
    created_by BIGINT NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
    chapter VARCHAR(150),
    lesson_topic VARCHAR(150),
    -- Mức độ nhận thức: 'NHAN_BIET', 'THONG_HIEU', 'VAN_DUNG', 'VAN_DUNG_CAO'
    cognitive_level VARCHAR(30) NOT NULL DEFAULT 'NHAN_BIET',
    -- Dạng câu hỏi: 'SINGLE_CHOICE', 'MULTIPLE_CHOICE', 'TRUE_FALSE', 'FILL_BLANK',
    --               'SHORT_ANSWER', 'ESSAY', 'MATCHING', 'ORDERING', 'MEDIA_QUESTION'
    question_type VARCHAR(30) NOT NULL,
    content_html TEXT NOT NULL,
    media_type VARCHAR(20), -- 'IMAGE', 'AUDIO', 'VIDEO', NULL
    media_url TEXT,
    explanation_html TEXT,
    is_ai_generated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE question_options (
    id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    option_label VARCHAR(10),       -- 'A', 'B', 'C', 'D'
    option_text TEXT NOT NULL,
    match_pair_text TEXT,           -- Dùng cho dạng câu hỏi Ghép đôi (MATCHING)
    correct_order INT,              -- Dùng cho dạng câu hỏi Sắp xếp (ORDERING)
    is_correct BOOLEAN DEFAULT FALSE
);

CREATE TABLE exam_questions (
    id BIGSERIAL PRIMARY KEY,
    exam_id BIGINT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
    points NUMERIC(5,2) NOT NULL DEFAULT 0.25,
    order_index INT NOT NULL DEFAULT 0,
    UNIQUE (exam_id, question_id)
);

CREATE TABLE exam_attempts (
    id BIGSERIAL PRIMARY KEY,
    exam_id BIGINT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    attempt_number INT NOT NULL DEFAULT 1,
    exam_variant_code VARCHAR(20), -- Mã đề đảo (VD: '101', '102')
    question_order_json JSONB,     -- Lưu thứ tự câu hỏi đã đảo riêng cho học sinh
    status VARCHAR(30) NOT NULL DEFAULT 'IN_PROGRESS', -- 'IN_PROGRESS', 'DISCONNECTED', 'SUBMITTED', 'AUTO_SUBMITTED', 'GRADED'
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_saved_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMPTZ,
    tab_switch_count INT DEFAULT 0,
    fullscreen_exit_count INT DEFAULT 0,
    auto_score NUMERIC(6,2) DEFAULT 0.00,
    final_score NUMERIC(6,2),
    UNIQUE (exam_id, student_id, attempt_number)
);

CREATE TABLE student_answers (
    id BIGSERIAL PRIMARY KEY,
    attempt_id BIGINT NOT NULL REFERENCES exam_attempts(id) ON DELETE CASCADE,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    selected_option_ids JSONB DEFAULT '[]'::jsonb,
    text_response TEXT,
    structured_response JSONB, -- Lưu kết quả ghép đôi hoặc sắp xếp
    is_correct BOOLEAN,
    points_earned NUMERIC(5,2) DEFAULT 0.00,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (attempt_id, question_id)
);

-- ============================================================================
-- 6. GIÁM SÁT QUÁ TRÌNH LÀM BÀI (ANTI-CHEATING EVENT LOGS)
-- ============================================================================

CREATE TABLE exam_events (
    id BIGSERIAL PRIMARY KEY,
    attempt_id BIGINT NOT NULL REFERENCES exam_attempts(id) ON DELETE CASCADE,
    exam_id BIGINT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    -- Loại sự kiện: 'TAB_HIDDEN', 'WINDOW_BLUR', 'FULLSCREEN_EXIT',
    --               'NETWORK_OFFLINE', 'NETWORK_ONLINE', 'EXAM_RESUMED', 'EXAM_SUBMITTED'
    event_type VARCHAR(40) NOT NULL,
    event_detail TEXT,
    client_timestamp TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 7. CHẤM ĐIỂM, NHẬN XÉT & LỊCH SỬ THAY ĐỔI ĐIỂM
-- ============================================================================

CREATE TABLE grades (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    class_id BIGINT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    subject_id INT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    assignment_id BIGINT REFERENCES assignments(id) ON DELETE CASCADE,
    exam_attempt_id BIGINT REFERENCES exam_attempts(id) ON DELETE CASCADE,
    graded_by BIGINT REFERENCES teachers(id) ON DELETE SET NULL,
    score NUMERIC(6,2) NOT NULL,
    max_score NUMERIC(6,2) NOT NULL DEFAULT 10.00,
    is_published BOOLEAN DEFAULT FALSE,
    graded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CHECK (assignment_id IS NOT NULL OR exam_attempt_id IS NOT NULL)
);

CREATE TABLE grade_history (
    id BIGSERIAL PRIMARY KEY,
    grade_id BIGINT NOT NULL REFERENCES grades(id) ON DELETE CASCADE,
    changed_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    old_score NUMERIC(6,2),
    new_score NUMERIC(6,2) NOT NULL,
    reason TEXT,
    changed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE grading_feedback (
    id BIGSERIAL PRIMARY KEY,
    submission_id BIGINT REFERENCES submissions(id) ON DELETE CASCADE,
    exam_attempt_id BIGINT REFERENCES exam_attempts(id) ON DELETE CASCADE,
    teacher_id BIGINT NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
    comment_text TEXT NOT NULL,
    annotated_errors JSONB DEFAULT '[]'::jsonb,
    requires_resubmission BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 8. THÔNG BÁO, THẢO LUẬN, LỊCH HỌC & TRỢ LÝ AI
-- ============================================================================

CREATE TABLE announcements (
    id BIGSERIAL PRIMARY KEY,
    class_id BIGINT REFERENCES classes(id) ON DELETE CASCADE, -- NULL nếu là thông báo toàn trường
    author_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    is_pinned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE assignment_comments (
    id BIGSERIAL PRIMARY KEY,
    assignment_id BIGINT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    sender_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_id BIGINT REFERENCES users(id) ON DELETE CASCADE, -- NULL = bình luận chung, có ID = trao đổi riêng GV-HS
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category VARCHAR(40) NOT NULL, -- 'ASSIGNMENT_NEW', 'DUE_SOON', 'GRADED', 'EXAM_ALERT', 'SYSTEM'
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    target_url TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE schedules (
    id BIGSERIAL PRIMARY KEY,
    class_id BIGINT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    subject_id INT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    teacher_id BIGINT REFERENCES teachers(id) ON DELETE SET NULL,
    event_type VARCHAR(30) NOT NULL, -- 'LESSON', 'EXAM', 'ASSIGNMENT_DUE'
    title VARCHAR(200) NOT NULL,
    day_of_week INT CHECK (day_of_week BETWEEN 1 AND 7),
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    room_or_link VARCHAR(150)
);

CREATE TABLE ai_tasks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id BIGINT REFERENCES courses(id) ON DELETE SET NULL,
    exam_id BIGINT REFERENCES exams(id) ON DELETE SET NULL,
    -- Loại tác vụ AI: 'GENERATE_QUESTIONS', 'EXPLAIN_CONCEPT', 'DEBUG_CODE',
    --                 'RUBRIC_SUGGESTION', 'GENERATE_LESSON_VIDEO'
    task_type VARCHAR(40) NOT NULL,
    prompt_input TEXT NOT NULL,
    ai_output TEXT,
    output_media_url TEXT, -- Đường dẫn video/tài liệu AI tạo ra
    status VARCHAR(20) DEFAULT 'COMPLETED', -- 'PROCESSING', 'COMPLETED', 'FAILED'
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE activity_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id BIGINT,
    ip_address VARCHAR(45),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 9. CHỈ MỤC TỐI ƯU HIỆU NĂNG TRUY VẤN (INDEXES)
-- ============================================================================

CREATE INDEX idx_users_role ON users(role_id);
CREATE INDEX idx_class_members_class ON class_members(class_id);
CREATE INDEX idx_class_members_student ON class_members(student_id);
CREATE INDEX idx_assignments_class_due ON assignments(class_id, due_at);
CREATE INDEX idx_submissions_assignment_student ON submissions(assignment_id, student_id);
CREATE INDEX idx_exams_class_time ON exams(class_id, start_at, end_at);
CREATE INDEX idx_exam_attempts_exam_student ON exam_attempts(exam_id, student_id);
CREATE INDEX idx_exam_events_attempt_time ON exam_events(attempt_id, recorded_at);
CREATE INDEX idx_grades_student_subject ON grades(student_id, subject_id);
CREATE INDEX idx_notifications_user_unread ON notifications(user_id, is_read);
CREATE INDEX idx_activity_logs_created ON activity_logs(created_at DESC);

-- ============================================================================
-- 10. DỮ LIỆU KHỞI TẠO MẶC ĐỊNH (SEED DATA)
-- ============================================================================

INSERT INTO system_settings (setting_key, setting_value, description) VALUES
('maintenance_mode', 'false', 'Bật/tắt chế độ bảo trì toàn hệ thống'),
('max_upload_size_mb', '50', 'Dung lượng tối đa cho mỗi tệp tải lên (MB)'),
('default_tab_switch_limit', '3', 'Ngưỡng cảnh báo số lần chuyển tab khi thi');

INSERT INTO roles (code, name, description) VALUES
('ADMIN', 'Quản trị viên', 'Quản lý toàn bộ hệ thống, tài khoản, năm học và sao lưu dữ liệu'),
('TEACHER', 'Giáo viên', 'Quản lý lớp học, tài liệu, giao bài tập, tổ chức thi và chấm điểm'),
('STUDENT', 'Học sinh', 'Học tập, nộp bài, lập trình và tham gia kiểm tra trực tuyến');

INSERT INTO grade_levels (code, name) VALUES
('K10', 'Khối 10'),
('K11', 'Khối 11'),
('K12', 'Khối 12');

INSERT INTO subjects (code, name, color_hex) VALUES
('TIN', 'Tin học', '#2563EB'),
('TOAN', 'Toán học', '#059669'),
('VAN', 'Ngữ văn', '#D97706'),
('ANH', 'Tiếng Anh', '#7C3AED');

INSERT INTO academic_years (name, start_date, end_date, is_current) VALUES
('2026-2027', '2026-09-05', '2027-05-31', TRUE);

-- Tài khoản Admin mặc định (Mật khẩu mẫu đã băm bcrypt)
INSERT INTO users (role_id, username, email, password_hash, full_name)
SELECT id, 'admin', 'admin@edulms.edu.vn', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/HS.iK2.', 'Quản trị viên Hệ thống'
FROM roles WHERE code = 'ADMIN';

COMMIT;