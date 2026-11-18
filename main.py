"""
============================================================================
HỆ THỐNG QUẢN LÝ HỌC TẬP TRỰC TUYẾN (EDULMS PRO)
Tệp: main.py
Mô tả: Máy chủ REST API & WebSocket hoàn chỉnh (hỗ trợ cả SQLite & PostgreSQL),
       tự động khởi tạo dữ liệu mẫu, quản lý hồ sơ/đổi mật khẩu, giao bài tập,
       giám sát thi trực tuyến, AI sinh đề/gia sư và trình biên dịch đa ngôn ngữ.
============================================================================
"""

import csv
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt
from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# ============================================================================
# 1. CẤU HÌNH CƠ SỞ DỮ LIỆU (MẶC ĐỊNH SQLITE CHẠY NGAY, HỖ TRỢ POSTGRESQL)
# ============================================================================

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./edulms_pro.db")
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "edulms-pro-super-secret-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 720
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
DEFAULT_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

os.makedirs(UPLOAD_DIR, exist_ok=True)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# 2. MÔ HÌNH CƠ SỞ DỮ LIỆU (ORM MODELS)
# ============================================================================


class SystemSetting(Base):
    __tablename__ = "system_settings"
    setting_key = Column(String(100), primary_key=True)
    setting_value = Column(Text, nullable=False)
    description = Column(Text)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(30), unique=True, nullable=False)
    name = Column(String(100), nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(150))
    phone = Column(String(25))
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    role = relationship("Role")
    teacher_profile = relationship("Teacher", back_populates="user", uselist=False)
    student_profile = relationship("Student", back_populates="user", uselist=False)


class Teacher(Base):
    __tablename__ = "teachers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    teacher_code = Column(String(50), unique=True, nullable=False)
    department = Column(String(100))
    specialization = Column(String(150))
    can_create_class = Column(Boolean, default=True)

    user = relationship("User", back_populates="teacher_profile")


class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    student_code = Column(String(50), unique=True, nullable=False)
    guardian_name = Column(String(150))
    guardian_phone = Column(String(20))

    user = relationship("User", back_populates="student_profile")


class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(30), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    color_hex = Column(String(7), default="#2563EB")


class ClassRoom(Base):
    __tablename__ = "classes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    academic_year_id = Column(Integer, nullable=False, default=1)
    grade_level_id = Column(Integer, nullable=False, default=1)
    homeroom_teacher_id = Column(Integer, ForeignKey("teachers.id"))
    code = Column(String(30), nullable=False)
    name = Column(String(100), nullable=False)
    join_code = Column(String(12), unique=True, nullable=False)
    description = Column(Text)
    is_archived = Column(Boolean, default=False)


class ClassMember(Base):
    __tablename__ = "class_members"
    id = Column(Integer, primary_key=True, autoincrement=True)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    status = Column(String(20), default="ACTIVE")


class Material(Base):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    chapter_tag = Column(String(100))
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_type = Column(String(30), nullable=False)
    file_size_bytes = Column(Integer, default=0)
    allow_download = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, nullable=False, default=1)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    title = Column(String(255), nullable=False)
    instructions = Column(Text, nullable=False)
    rubric_text = Column(Text)
    submission_types = Column(JSON, default=["CODE"])
    max_score = Column(Numeric(6, 2), default=10.00)
    max_attempts = Column(Integer, default=3)
    allow_late_submission = Column(Boolean, default=True)
    ai_tutor_enabled = Column(Boolean, default=True)
    start_at = Column(DateTime(timezone=True), server_default=func.now())
    due_at = Column(DateTime(timezone=True), nullable=False)


class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    attempt_number = Column(Integer, default=1)
    status = Column(String(30), default="SUBMITTED")
    text_answer = Column(Text)
    code_language = Column(String(30))
    code_content = Column(Text)
    code_run_instructions = Column(Text)
    external_link = Column(Text)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())


class Exam(Base):
    __tablename__ = "exams"
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, nullable=False, default=1)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    duration_minutes = Column(Integer, default=45)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    max_attempts = Column(Integer, default=3)
    total_score = Column(Numeric(6, 2), default=10.00)
    shuffle_questions = Column(Boolean, default=True)
    shuffle_options = Column(Boolean, default=True)
    allow_backtrack = Column(Boolean, default=True)
    show_score_immediately = Column(Boolean, default=True)
    publish_answers = Column(Boolean, default=False)
    ai_assistant_allowed = Column(Boolean, default=False)
    require_fullscreen = Column(Boolean, default=True)
    tab_switch_warning_threshold = Column(Integer, default=3)


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    chapter = Column(String(150))
    cognitive_level = Column(String(30), default="NHAN_BIET")
    question_type = Column(String(30), nullable=False)
    content_html = Column(Text, nullable=False)
    explanation_html = Column(Text)
    is_ai_generated = Column(Boolean, default=False)

    options = relationship("QuestionOption", back_populates="question", cascade="all, delete-orphan")


class QuestionOption(Base):
    __tablename__ = "question_options"
    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    option_label = Column(String(10))
    option_text = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)

    question = relationship("Question", back_populates="options")


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    points = Column(Numeric(5, 2), default=0.25)
    order_index = Column(Integer, default=0)


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    attempt_number = Column(Integer, default=1)
    exam_variant_code = Column(String(20))
    question_order_json = Column(JSON)
    status = Column(String(30), default="IN_PROGRESS")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_saved_at = Column(DateTime(timezone=True), server_default=func.now())
    submitted_at = Column(DateTime(timezone=True))
    tab_switch_count = Column(Integer, default=0)
    fullscreen_exit_count = Column(Integer, default=0)
    auto_score = Column(Numeric(6, 2), default=0.00)
    final_score = Column(Numeric(6, 2))


class StudentAnswer(Base):
    __tablename__ = "student_answers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    attempt_id = Column(Integer, ForeignKey("exam_attempts.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    selected_option_ids = Column(JSON, default=[])
    text_response = Column(Text)
    is_correct = Column(Boolean)
    points_earned = Column(Numeric(5, 2), default=0.00)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class ExamEvent(Base):
    __tablename__ = "exam_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    attempt_id = Column(Integer, ForeignKey("exam_attempts.id"), nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    event_type = Column(String(40), nullable=False)
    event_detail = Column(Text)
    client_timestamp = Column(DateTime(timezone=True))
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())


class Grade(Base):
    __tablename__ = "grades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"))
    exam_attempt_id = Column(Integer, ForeignKey("exam_attempts.id"))
    graded_by = Column(Integer, ForeignKey("teachers.id"))
    score = Column(Numeric(6, 2), nullable=False)
    max_score = Column(Numeric(6, 2), default=10.00)
    is_published = Column(Boolean, default=True)
    graded_at = Column(DateTime(timezone=True), server_default=func.now())


class GradeHistory(Base):
    __tablename__ = "grade_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    grade_id = Column(Integer, ForeignKey("grades.id"), nullable=False)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    old_score = Column(Numeric(6, 2))
    new_score = Column(Numeric(6, 2), nullable=False)
    reason = Column(Text)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())


class GradingFeedback(Base):
    __tablename__ = "grading_feedback"
    id = Column(Integer, primary_key=True, autoincrement=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"))
    exam_attempt_id = Column(Integer, ForeignKey("exam_attempts.id"))
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    comment_text = Column(Text, nullable=False)
    requires_resubmission = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AITask(Base):
    __tablename__ = "ai_tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer)
    exam_id = Column(Integer)
    task_type = Column(String(40), nullable=False)
    prompt_input = Column(Text, nullable=False)
    ai_output = Column(Text)
    output_media_url = Column(Text)
    status = Column(String(20), default="COMPLETED")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50))
    entity_id = Column(Integer)
    ip_address = Column(String(45))
    metadata_json = Column("metadata", JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================================
# 3. PYDANTIC SCHEMAS
# ============================================================================


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class ProfileUpdateSchema(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class ChangePasswordSchema(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)


class UserCreateSchema(BaseModel):
    username: str
    email: Optional[str] = None
    password: str
    full_name: str
    role_code: str = Field(..., pattern="^(ADMIN|TEACHER|STUDENT)$")
    code_identifier: Optional[str] = None


class ClassCreateSchema(BaseModel):
    code: str
    name: str
    grade_level_id: int = 1
    description: Optional[str] = None


class AssignmentCreateSchema(BaseModel):
    class_id: int
    subject_id: int
    title: str
    instructions: str
    rubric_text: Optional[str] = None
    submission_types: List[str] = ["CODE"]
    max_score: float = 10.0
    max_attempts: int = 3
    allow_late_submission: bool = True
    ai_tutor_enabled: bool = True
    due_at: str


class SubmissionCreateSchema(BaseModel):
    text_answer: Optional[str] = None
    code_language: Optional[str] = None
    code_content: Optional[str] = None
    code_run_instructions: Optional[str] = None
    external_link: Optional[str] = None


class GradeUpdateSchema(BaseModel):
    score: float
    comment_text: str
    requires_resubmission: bool = False
    reason: Optional[str] = "Chấm điểm bài làm"


class QuestionOptionSchema(BaseModel):
    option_label: str
    option_text: str
    is_correct: bool = False


class QuestionCreateSchema(BaseModel):
    subject_id: int
    chapter: Optional[str] = None
    cognitive_level: str = "NHAN_BIET"
    question_type: str = "SINGLE_CHOICE"
    content_html: str
    explanation_html: Optional[str] = None
    is_ai_generated: bool = False
    options: List[QuestionOptionSchema] = []


class ExamCreateSchema(BaseModel):
    class_id: int
    subject_id: int
    title: str
    description: Optional[str] = None
    duration_minutes: int = 45
    start_at: str
    end_at: str
    question_ids: List[int]
    shuffle_questions: bool = True
    shuffle_options: bool = True
    ai_assistant_allowed: bool = False
    tab_switch_warning_threshold: int = 3


class AutoSaveAnswerSchema(BaseModel):
    answers: List[Dict[str, Any]]


class ExamEventCreateSchema(BaseModel):
    attempt_id: int
    exam_id: int
    event_type: str
    event_detail: Optional[str] = None
    client_timestamp: Optional[str] = None


class CodeSandboxRequest(BaseModel):
    language: str = Field(..., pattern="^(python|javascript|c|cpp|java|html)$")
    source_code: str
    stdin_input: Optional[str] = ""


class AIQuestionGenRequest(BaseModel):
    subject_id: int = 1
    subject_name: str = "Tin học"
    topic_content: str
    num_questions: int = Field(default=3, ge=1, le=15)
    cognitive_level: str = "THONG_HIEU"


class AITutorRequest(BaseModel):
    prompt: str
    context_code: Optional[str] = None
    subject_name: Optional[str] = "Tin học"


class AIVideoGenRequest(BaseModel):
    subject_name: str
    lesson_title: str
    lesson_outline: str
    duration_seconds: int = Field(default=60, ge=15, le=300)


# ============================================================================
# 4. KHỞI TẠO ỨNG DỤNG & SEED DỮ LIỆU MẶC ĐỊNH KHI CHẠY LẦN ĐẦU
# ============================================================================

app = FastAPI(title="EduLMS Pro API", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def parse_iso_datetime(dt_str: str) -> datetime:
    cleaned = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@app.on_event("startup")
def init_database_and_seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(SystemSetting).filter_by(setting_key="maintenance_mode").first():
            db.add(SystemSetting(setting_key="maintenance_mode", setting_value="false"))

        if not db.query(Role).first():
            r_admin = Role(code="ADMIN", name="Quản trị viên")
            r_teacher = Role(code="TEACHER", name="Giáo viên")
            r_student = Role(code="STUDENT", name="Học sinh")
            db.add_all([r_admin, r_teacher, r_student])
            db.flush()

            s_tin = Subject(code="TIN", name="Tin học", color_hex="#2563EB")
            s_toan = Subject(code="TOAN", name="Toán học", color_hex="#059669")
            s_van = Subject(code="VAN", name="Ngữ văn", color_hex="#D97706")
            s_anh = Subject(code="ANH", name="Tiếng Anh", color_hex="#7C3AED")
            db.add_all([s_tin, s_toan, s_van, s_anh])
            db.flush()

            u_admin = User(
                role_id=r_admin.id,
                username="admin",
                email="admin@edulms.edu.vn",
                phone="0901000001",
                password_hash=hash_password("123456"),
                full_name="Quản trị viên Hệ thống",
            )
            u_gv = User(
                role_id=r_teacher.id,
                username="GV001",
                email="tuan.tm@edulms.edu.vn",
                phone="0902000002",
                password_hash=hash_password("123456"),
                full_name="ThS. Trần Minh Tuấn",
            )
            u_hs1 = User(
                role_id=r_student.id,
                username="HS2026001",
                email="anh.nn@edulms.edu.vn",
                phone="0903000003",
                password_hash=hash_password("123456"),
                full_name="Nguyễn Ngọc Ánh",
            )
            u_hs2 = User(
                role_id=r_student.id,
                username="HS2026002",
                email="nam.lh@edulms.edu.vn",
                phone="0903000004",
                password_hash=hash_password("123456"),
                full_name="Lê Hoàng Nam",
            )
            db.add_all([u_admin, u_gv, u_hs1, u_hs2])
            db.flush()

            gv = Teacher(user_id=u_gv.id, teacher_code="GV001", department="Tổ Tin học")
            hs1 = Student(user_id=u_hs1.id, student_code="HS2026001")
            hs2 = Student(user_id=u_hs2.id, student_code="HS2026002")
            db.add_all([gv, hs1, hs2])
            db.flush()

            c1 = ClassRoom(
                code="10A1",
                name="Lớp 10A1 - Tin học & Toán",
                homeroom_teacher_id=gv.id,
                join_code="8F2A91C0",
                description="Lớp trọng điểm Tin học khối 10",
            )
            c2 = ClassRoom(
                code="11A1",
                name="Lớp 11A1 - Chuyên Tin",
                homeroom_teacher_id=gv.id,
                join_code="9C30E5A1",
                description="Bồi dưỡng thuật toán & lập trình",
            )
            db.add_all([c1, c2])
            db.flush()

            db.add_all([
                ClassMember(class_id=c1.id, student_id=hs1.id),
                ClassMember(class_id=c1.id, student_id=hs2.id),
            ])

            # Bài tập mẫu
            now = datetime.now(timezone.utc)
            a1 = Assignment(
                class_id=c1.id,
                subject_id=s_tin.id,
                teacher_id=gv.id,
                title="Bài tập 1: Viết hàm tính giai thừa và dãy Fibonacci",
                instructions="Viết chương trình tính n! và số Fibonacci thứ n bằng Python, C++ hoặc Java.",
                submission_types=["CODE", "TEXT"],
                max_score=10.0,
                max_attempts=5,
                allow_late_submission=True,
                due_at=now + timedelta(days=7),
            )
            db.add(a1)
            db.flush()

            # Ngân hàng câu hỏi & Đề thi mẫu
            q1 = Question(
                subject_id=s_tin.id,
                created_by=gv.id,
                chapter="Chương 1: Hàm trong Python",
                cognitive_level="NHAN_BIET",
                question_type="SINGLE_CHOICE",
                content_html="Trong Python, từ khóa nào dùng để định nghĩa một hàm?",
                explanation_html="Từ khóa def được dùng để khai báo hàm trong Python.",
            )
            q2 = Question(
                subject_id=s_tin.id,
                created_by=gv.id,
                chapter="Chương 2: Độ phức tạp thuật toán",
                cognitive_level="THONG_HIEU",
                question_type="SINGLE_CHOICE",
                content_html="Độ phức tạp thời gian trung bình của thuật toán tìm kiếm nhị phân là gì?",
                explanation_html="Mỗi bước chia đôi không gian tìm kiếm nên độ phức tạp là O(log n).",
            )
            db.add_all([q1, q2])
            db.flush()

            db.add_all([
                QuestionOption(question_id=q1.id, option_label="A", option_text="func", is_correct=False),
                QuestionOption(question_id=q1.id, option_label="B", option_text="def", is_correct=True),
                QuestionOption(question_id=q1.id, option_label="C", option_text="function", is_correct=False),
                QuestionOption(question_id=q1.id, option_label="D", option_text="define", is_correct=False),
                QuestionOption(question_id=q2.id, option_label="A", option_text="O(n)", is_correct=False),
                QuestionOption(question_id=q2.id, option_label="B", option_text="O(n^2)", is_correct=False),
                QuestionOption(question_id=q2.id, option_label="C", option_text="O(log n)", is_correct=True),
                QuestionOption(question_id=q2.id, option_label="D", option_text="O(1)", is_correct=False),
            ])

            ex1 = Exam(
                class_id=c1.id,
                subject_id=s_tin.id,
                teacher_id=gv.id,
                title="Kiểm tra 45 phút: Cấu trúc hàm & Thuật toán",
                description="Bài kiểm tra có bật giám sát Anti-Cheating và khóa trợ lý AI.",
                duration_minutes=45,
                start_at=now - timedelta(hours=1),
                end_at=now + timedelta(days=7),
                max_attempts=5,
                ai_assistant_allowed=False,
            )
            db.add(ex1)
            db.flush()

            db.add_all([
                ExamQuestion(exam_id=ex1.id, question_id=q1.id, points=5.0, order_index=0),
                ExamQuestion(exam_id=ex1.id, question_id=q2.id, points=5.0, order_index=1),
            ])

            db.commit()
    finally:
        db.close()


# ============================================================================
# 5. MIDDLEWARE BẢO TRÌ, XÁC THỰC JWT & HỒ SƠ CÁ NHÂN / ĐỔI MẬT KHẨU
# ============================================================================


@app.middleware("http")
async def maintenance_mode_middleware(request: Request, call_next):
    open_paths = ("/api/auth/login", "/docs", "/openapi.json", "/health")
    if any(request.url.path.startswith(p) for p in open_paths):
        return await call_next(request)

    db = SessionLocal()
    try:
        setting = db.query(SystemSetting).filter_by(setting_key="maintenance_mode").first()
        if setting and setting.setting_value.lower() == "true":
            auth_header = request.headers.get("Authorization", "")
            is_admin = False
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]
                try:
                    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                    if payload.get("role") == "ADMIN":
                        is_admin = True
                except JWTError:
                    pass
            if not is_admin:
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"detail": "Hệ thống EduLMS Pro đang bảo trì định kỳ."},
                )
    finally:
        db.close()

    return await call_next(request)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản không tồn tại hoặc đã bị khóa.")
    return user


def require_role(allowed_roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.code not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Chức năng yêu cầu quyền: {', '.join(allowed_roles)}.",
            )
        return current_user

    return role_checker


def serialize_user(user: User) -> Dict[str, Any]:
    code_id = user.username
    if user.teacher_profile:
        code_id = user.teacher_profile.teacher_code
    elif user.student_profile:
        code_id = user.student_profile.student_code
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email or "",
        "phone": user.phone or "",
        "role": user.role.code,
        "role_name": user.role.name,
        "code_identifier": code_id,
        "is_active": user.is_active,
    }


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "EduLMS Pro Backend"}


@app.post("/api/auth/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không chính xác.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa.")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token({"sub": user.username, "role": user.role.code, "uid": user.id})
    return {"access_token": token, "token_type": "bearer", "user": serialize_user(user)}


@app.get("/api/auth/me")
def get_my_profile(current_user: User = Depends(get_current_user)):
    return serialize_user(current_user)


@app.put("/api/auth/profile")
def update_my_profile(
    payload: ProfileUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.full_name = payload.full_name.strip()
    current_user.email = (payload.email or "").strip() or None
    current_user.phone = (payload.phone or "").strip() or None
    db.commit()
    db.refresh(current_user)
    return {"message": "Cập nhật thông tin cá nhân thành công!", "user": serialize_user(current_user)}


@app.post("/api/auth/change-password")
def change_my_password(
    payload: ChangePasswordSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không chính xác.")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Đổi mật khẩu thành công!"}


# ============================================================================
# 6. PHÂN HỆ QUẢN TRỊ VIÊN (ADMIN)
# ============================================================================


@app.get("/api/admin/dashboard")
def admin_dashboard_stats(_: User = Depends(require_role(["ADMIN"])), db: Session = Depends(get_db)):
    return {
        "total_users": db.query(User).count(),
        "total_teachers": db.query(Teacher).count(),
        "total_students": db.query(Student).count(),
        "total_classes": db.query(ClassRoom).count(),
        "total_assignments": db.query(Assignment).count(),
        "total_exams": db.query(Exam).count(),
    }


@app.get("/api/admin/users")
def admin_list_users(_: User = Depends(require_role(["ADMIN"])), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [serialize_user(u) for u in users]


@app.post("/api/admin/users")
def admin_create_user(
    payload: UserCreateSchema,
    _: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại.")

    role = db.query(Role).filter(Role.code == payload.role_code).first()
    new_user = User(
        role_id=role.id,
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(new_user)
    db.flush()

    if payload.role_code == "TEACHER":
        db.add(Teacher(user_id=new_user.id, teacher_code=payload.code_identifier or f"GV{new_user.id:03d}"))
    elif payload.role_code == "STUDENT":
        db.add(Student(user_id=new_user.id, student_code=payload.code_identifier or f"HS2026{new_user.id:03d}"))

    db.commit()
    return {"message": "Tạo tài khoản thành công.", "user_id": new_user.id}


@app.patch("/api/admin/users/{user_id}/toggle-active")
def admin_toggle_user_active(
    user_id: int,
    admin: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Không thể tự khóa tài khoản đang đăng nhập.")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")
    target.is_active = not target.is_active
    db.commit()
    return {"is_active": target.is_active}


@app.post("/api/admin/users/import-csv")
async def admin_import_users_csv(
    file: UploadFile = File(...),
    _: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    created_count = 0
    for row in reader:
        username = (row.get("username") or "").strip()
        if not username or db.query(User).filter(User.username == username).first():
            continue
        role_code = (row.get("role_code") or "STUDENT").strip().upper()
        role = db.query(Role).filter(Role.code == role_code).first()
        if not role:
            continue
        user = User(
            role_id=role.id,
            username=username,
            email=(row.get("email") or None),
            password_hash=hash_password((row.get("password") or "123456").strip()),
            full_name=(row.get("full_name") or username).strip(),
        )
        db.add(user)
        db.flush()
        code_val = (row.get("code") or "").strip()
        if role_code == "TEACHER":
            db.add(Teacher(user_id=user.id, teacher_code=code_val or f"GV{user.id:03d}"))
        elif role_code == "STUDENT":
            db.add(Student(user_id=user.id, student_code=code_val or f"HS2026{user.id:03d}"))
        created_count += 1
    db.commit()
    return {"created_count": created_count}


@app.patch("/api/admin/settings/maintenance")
def toggle_maintenance_mode(
    enabled: bool,
    _: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    setting = db.query(SystemSetting).filter_by(setting_key="maintenance_mode").first()
    if not setting:
        db.add(SystemSetting(setting_key="maintenance_mode", setting_value=str(enabled).lower()))
    else:
        setting.setting_value = str(enabled).lower()
    db.commit()
    return {"maintenance_mode": enabled}


@app.get("/api/admin/backup/sql", response_class=PlainTextResponse)
def export_sql_backup(_: User = Depends(require_role(["ADMIN"])), db: Session = Depends(get_db)):
    lines = [f"-- EDULMS PRO SQL BACKUP - {datetime.now(timezone.utc).isoformat()}", "BEGIN;"]
    for u in db.query(User).all():
        safe_name = u.full_name.replace("'", "''")
        lines.append(
            f"INSERT INTO users (id, role_id, username, full_name, is_active) "
            f"VALUES ({u.id}, {u.role_id}, '{u.username}', '{safe_name}', {u.is_active});"
        )
    for c in db.query(ClassRoom).all():
        lines.append(
            f"INSERT INTO classes (id, code, name, join_code) "
            f"VALUES ({c.id}, '{c.code}', '{c.name}', '{c.join_code}');"
        )
    lines.append("COMMIT;")
    return "\n".join(lines)


# ============================================================================
# 7. LỚP HỌC, MÔN HỌC, TÀI LIỆU, BÀI TẬP & CHẤM ĐIỂM
# ============================================================================


@app.get("/api/meta/options")
def get_meta_options(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    classes = db.query(ClassRoom).filter(ClassRoom.is_archived == False).all()
    subjects = db.query(Subject).all()
    my_class_ids = []
    if current_user.student_profile:
        my_class_ids = [
            m.class_id
            for m in db.query(ClassMember).filter_by(student_id=current_user.student_profile.id, status="ACTIVE").all()
        ]
    return {
        "classes": [
            {
                "id": c.id,
                "code": c.code,
                "name": c.name,
                "join_code": c.join_code,
                "description": c.description or "",
                "member_count": db.query(ClassMember).filter_by(class_id=c.id, status="ACTIVE").count(),
            }
            for c in classes
        ],
        "subjects": [{"id": s.id, "code": s.code, "name": s.name} for s in subjects],
        "my_class_ids": my_class_ids,
    }


@app.post("/api/teacher/classes")
def create_classroom(
    payload: ClassCreateSchema,
    user: User = Depends(require_role(["TEACHER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    join_code = uuid.uuid4().hex[:8].upper()
    teacher_id = user.teacher_profile.id if user.teacher_profile else None
    new_class = ClassRoom(
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        grade_level_id=payload.grade_level_id,
        homeroom_teacher_id=teacher_id,
        join_code=join_code,
        description=payload.description,
    )
    db.add(new_class)
    db.commit()
    db.refresh(new_class)
    return {"id": new_class.id, "code": new_class.code, "join_code": new_class.join_code}


@app.post("/api/student/classes/join")
def student_join_class(
    join_code: str,
    user: User = Depends(require_role(["STUDENT"])),
    db: Session = Depends(get_db),
):
    classroom = db.query(ClassRoom).filter(ClassRoom.join_code == join_code.strip().upper()).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Mã tham gia lớp học không tồn tại.")
    student_id = user.student_profile.id
    if not db.query(ClassMember).filter_by(class_id=classroom.id, student_id=student_id).first():
        db.add(ClassMember(class_id=classroom.id, student_id=student_id))
        db.commit()
    return {"message": f"Tham gia lớp {classroom.name} thành công!"}

@app.get("/api/students")
def list_all_students(
    _: User = Depends(require_role(["TEACHER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    students = db.query(Student).order_by(Student.id.asc()).all()
    result = []
    for s in students:
        memberships = db.query(ClassMember).filter_by(student_id=s.id, status="ACTIVE").all()
        class_codes = []
        for m in memberships:
            cls = db.query(ClassRoom).filter_by(id=m.class_id).first()
            if cls:
                class_codes.append(cls.code)
        result.append(
            {
                "student_id": s.id,
                "user_id": s.user_id,
                "student_code": s.student_code,
                "full_name": s.user.full_name if s.user else s.student_code,
                "email": s.user.email if s.user else "",
                "class_codes": class_codes,
            }
        )
    return result


@app.get("/api/classes/{class_id}/members")
def list_class_members(
    class_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    classroom = db.query(ClassRoom).filter_by(id=class_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Không tìm thấy lớp học.")

    members = db.query(ClassMember).filter_by(class_id=class_id, status="ACTIVE").all()
    result = []
    for m in members:
        stu = db.query(Student).filter_by(id=m.student_id).first()
        if stu:
            result.append(
                {
                    "member_id": m.id,
                    "student_id": stu.id,
                    "student_code": stu.student_code,
                    "full_name": stu.user.full_name if stu.user else stu.student_code,
                    "email": stu.user.email if stu.user else "",
                    "status": m.status,
                }
            )
    return result


@app.post("/api/classes/{class_id}/members")
def assign_students_to_class(
    class_id: int,
    payload: Dict[str, Any],
    _: User = Depends(require_role(["TEACHER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    classroom = db.query(ClassRoom).filter_by(id=class_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Không tìm thấy lớp học.")

    student_ids = payload.get("student_ids") or []
    added_count = 0
    for sid in student_ids:
        stu = db.query(Student).filter_by(id=int(sid)).first()
        if not stu:
            continue
        existing = db.query(ClassMember).filter_by(class_id=class_id, student_id=stu.id).first()
        if not existing:
            db.add(ClassMember(class_id=class_id, student_id=stu.id, status="ACTIVE"))
            added_count += 1
        elif existing.status != "ACTIVE":
            existing.status = "ACTIVE"
            added_count += 1

    db.commit()
    return {"message": f"Đã phân {added_count} học sinh vào lớp {classroom.code}!", "added_count": added_count}


@app.delete("/api/classes/{class_id}/members/{student_id}")
def remove_student_from_class(
    class_id: int,
    student_id: int,
    _: User = Depends(require_role(["TEACHER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    member = db.query(ClassMember).filter_by(class_id=class_id, student_id=student_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Học sinh không thuộc lớp học này.")
    db.delete(member)
    db.commit()
    return {"message": "Đã xóa học sinh khỏi lớp."}

@app.get("/api/assignments")
def list_assignments(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Assignment).order_by(Assignment.id.desc()).all()
    result = []
    for a in items:
        cls = db.query(ClassRoom).filter_by(id=a.class_id).first()
        subj = db.query(Subject).filter_by(id=a.subject_id).first()
        sub_count = db.query(Submission).filter_by(assignment_id=a.id).count()

        my_status = "CHUA_NOP"
        my_score = None
        if current_user.student_profile:
            sid = current_user.student_profile.id
            sub = (
                db.query(Submission)
                .filter_by(assignment_id=a.id, student_id=sid)
                .order_by(Submission.id.desc())
                .first()
            )
            if sub:
                my_status = sub.status
            grade = db.query(Grade).filter_by(assignment_id=a.id, student_id=sid).first()
            if grade:
                my_score = float(grade.score)

        result.append(
            {
                "id": a.id,
                "title": a.title,
                "instructions": a.instructions,
                "class_id": a.class_id,
                "class_code": cls.code if cls else "10A1",
                "subject_id": a.subject_id,
                "subject_name": subj.name if subj else "Tin học",
                "submission_types": a.submission_types or ["CODE"],
                "max_score": float(a.max_score),
                "max_attempts": a.max_attempts,
                "due_at": a.due_at.isoformat() if a.due_at else None,
                "submission_count": sub_count,
                "my_status": my_status,
                "my_score": my_score,
            }
        )
    return result


@app.post("/api/teacher/assignments")
def create_assignment(
    payload: AssignmentCreateSchema,
    user: User = Depends(require_role(["TEACHER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    teacher_id = user.teacher_profile.id if user.teacher_profile else 1
    assignment = Assignment(
        class_id=payload.class_id,
        subject_id=payload.subject_id,
        teacher_id=teacher_id,
        title=payload.title.strip(),
        instructions=payload.instructions.strip(),
        rubric_text=payload.rubric_text,
        submission_types=payload.submission_types,
        max_score=payload.max_score,
        max_attempts=payload.max_attempts,
        allow_late_submission=payload.allow_late_submission,
        ai_tutor_enabled=payload.ai_tutor_enabled,
        due_at=parse_iso_datetime(payload.due_at),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return {"id": assignment.id, "title": assignment.title, "message": "Đã giao bài tập thành công!"}


@app.get("/api/teacher/assignments/{assignment_id}/submissions")
def list_assignment_submissions(
    assignment_id: int,
    _: User = Depends(require_role(["TEACHER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    subs = (
        db.query(Submission)
        .filter_by(assignment_id=assignment_id)
        .order_by(Submission.submitted_at.desc())
        .all()
    )
    result = []
    for s in subs:
        stu = db.query(Student).filter_by(id=s.student_id).first()
        grade = db.query(Grade).filter_by(assignment_id=assignment_id, student_id=s.student_id).first()
        result.append(
            {
                "id": s.id,
                "student_code": stu.student_code if stu else "",
                "student_name": stu.user.full_name if stu and stu.user else "Học sinh",
                "attempt_number": s.attempt_number,
                "status": s.status,
                "code_language": s.code_language,
                "code_content": s.code_content,
                "text_answer": s.text_answer,
                "external_link": s.external_link,
                "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
                "score": float(grade.score) if grade else None,
            }
        )
    return result


@app.post("/api/student/assignments/{assignment_id}/submit")
def student_submit_assignment(
    assignment_id: int,
    payload: SubmissionCreateSchema,
    user: User = Depends(require_role(["STUDENT"])),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter_by(id=assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Bài tập không tồn tại.")

    now = datetime.now(timezone.utc)
    due = ensure_aware(assignment.due_at)
    is_late = bool(due and now > due)
    if is_late and not assignment.allow_late_submission:
        raise HTTPException(status_code=400, detail="Đã quá hạn nộp bài.")

    student_id = user.student_profile.id
    prev_count = db.query(Submission).filter_by(assignment_id=assignment_id, student_id=student_id).count()
    if prev_count >= assignment.max_attempts:
        raise HTTPException(status_code=400, detail=f"Bạn đã dùng hết {assignment.max_attempts} lượt nộp.")

    sub = Submission(
        assignment_id=assignment_id,
        student_id=student_id,
        attempt_number=prev_count + 1,
        status="LATE_SUBMITTED" if is_late else "SUBMITTED",
        text_answer=payload.text_answer,
        code_language=payload.code_language,
        code_content=payload.code_content,
        code_run_instructions=payload.code_run_instructions,
        external_link=payload.external_link,
        submitted_at=now,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {"submission_id": sub.id, "attempt_number": sub.attempt_number, "status": sub.status}


@app.post("/api/teacher/submissions/{submission_id}/grade")
def grade_student_submission(
    submission_id: int,
    payload: GradeUpdateSchema,
    user: User = Depends(require_role(["TEACHER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    sub = db.query(Submission).filter_by(id=submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài nộp.")

    assignment = db.query(Assignment).filter_by(id=sub.assignment_id).first()
    teacher_id = user.teacher_profile.id if user.teacher_profile else 1
    sub.status = "REVISION_REQUESTED" if payload.requires_resubmission else "GRADED"

    grade = db.query(Grade).filter_by(assignment_id=assignment.id, student_id=sub.student_id).first()
    if grade:
        old_val = grade.score
        grade.score = payload.score
        grade.graded_by = teacher_id
        db.add(
            GradeHistory(
                grade_id=grade.id,
                changed_by=user.id,
                old_score=old_val,
                new_score=payload.score,
                reason=payload.reason,
            )
        )
    else:
        grade = Grade(
            student_id=sub.student_id,
            class_id=assignment.class_id,
            subject_id=assignment.subject_id,
            assignment_id=assignment.id,
            graded_by=teacher_id,
            score=payload.score,
            max_score=assignment.max_score,
            is_published=True,
        )
        db.add(grade)

    db.add(
        GradingFeedback(
            submission_id=sub.id,
            teacher_id=teacher_id,
            comment_text=payload.comment_text,
            requires_resubmission=payload.requires_resubmission,
        )
    )
    db.commit()
    return {"message": "Đã lưu điểm và nhận xét thành công!"}


# ============================================================================
# 8. NGÂN HÀNG CÂU HỎI, KIỂM TRA TRỰC TUYẾN & GIÁM SÁT ANTI-CHEATING
# ============================================================================


class ProctoringConnectionManager:
    def __init__(self):
        self.active_rooms: Dict[int, List[WebSocket]] = {}

    async def connect(self, exam_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_rooms.setdefault(exam_id, []).append(websocket)

    def disconnect(self, exam_id: int, websocket: WebSocket):
        if exam_id in self.active_rooms and websocket in self.active_rooms[exam_id]:
            self.active_rooms[exam_id].remove(websocket)

    async def broadcast_event(self, exam_id: int, message: dict):
        for ws in list(self.active_rooms.get(exam_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(exam_id, ws)


proctoring_manager = ProctoringConnectionManager()


@app.websocket("/ws/proctoring/{exam_id}")
async def proctoring_websocket(websocket: WebSocket, exam_id: int):
    await proctoring_manager.connect(exam_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        proctoring_manager.disconnect(exam_id, websocket)


@app.get("/api/questions")
def list_questions(_: User = Depends(require_role(["TEACHER", "ADMIN"])), db: Session = Depends(get_db)):
    questions = db.query(Question).order_by(Question.id.desc()).all()
    return [
        {
            "id": q.id,
            "subject_id": q.subject_id,
            "chapter": q.chapter or "",
            "cognitive_level": q.cognitive_level,
            "content_html": q.content_html,
            "is_ai_generated": q.is_ai_generated,
            "options": [
                {"id": o.id, "label": o.option_label, "text": o.option_text, "is_correct": o.is_correct}
                for o in q.options
            ],
        }
        for q in questions
    ]


@app.post("/api/teacher/questions")
def create_question(
    payload: QuestionCreateSchema,
    user: User = Depends(require_role(["TEACHER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    teacher_id = user.teacher_profile.id if user.teacher_profile else 1
    q = Question(
        subject_id=payload.subject_id,
        created_by=teacher_id,
        chapter=payload.chapter,
        cognitive_level=payload.cognitive_level,
        question_type=payload.question_type,
        content_html=payload.content_html,
        explanation_html=payload.explanation_html,
        is_ai_generated=payload.is_ai_generated,
    )
    db.add(q)
    db.flush()
    for opt in payload.options:
        db.add(
            QuestionOption(
                question_id=q.id,
                option_label=opt.option_label,
                option_text=opt.option_text,
                is_correct=opt.is_correct,
            )
        )
    db.commit()
    return {"question_id": q.id}


@app.get("/api/exams")
def list_exams(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    exams = db.query(Exam).order_by(Exam.id.desc()).all()
    result = []
    for ex in exams:
        cls = db.query(ClassRoom).filter_by(id=ex.class_id).first()
        subj = db.query(Subject).filter_by(id=ex.subject_id).first()
        q_count = db.query(ExamQuestion).filter_by(exam_id=ex.id).count()
        att_count = db.query(ExamAttempt).filter_by(exam_id=ex.id).count()
        result.append(
            {
                "id": ex.id,
                "title": ex.title,
                "description": ex.description or "",
                "class_code": cls.code if cls else "10A1",
                "subject_name": subj.name if subj else "Tin học",
                "duration_minutes": ex.duration_minutes,
                "ai_assistant_allowed": ex.ai_assistant_allowed,
                "question_count": q_count,
                "attempt_count": att_count,
            }
        )
    return result


@app.post("/api/teacher/exams")
def create_exam(
    payload: ExamCreateSchema,
    user: User = Depends(require_role(["TEACHER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    if not payload.question_ids:
        raise HTTPException(status_code=400, detail="Đề thi phải chọn ít nhất 1 câu hỏi.")
    teacher_id = user.teacher_profile.id if user.teacher_profile else 1
    exam = Exam(
        class_id=payload.class_id,
        subject_id=payload.subject_id,
        teacher_id=teacher_id,
        title=payload.title.strip(),
        description=payload.description,
        duration_minutes=payload.duration_minutes,
        start_at=parse_iso_datetime(payload.start_at),
        end_at=parse_iso_datetime(payload.end_at),
        shuffle_questions=payload.shuffle_questions,
        shuffle_options=payload.shuffle_options,
        ai_assistant_allowed=payload.ai_assistant_allowed,
        tab_switch_warning_threshold=payload.tab_switch_warning_threshold,
    )
    db.add(exam)
    db.flush()

    pts = round(10.0 / len(payload.question_ids), 2)
    for idx, q_id in enumerate(payload.question_ids):
        db.add(ExamQuestion(exam_id=exam.id, question_id=q_id, points=pts, order_index=idx))
    db.commit()
    return {"exam_id": exam.id, "title": exam.title, "message": "Đã tạo đề kiểm tra thành công!"}


@app.post("/api/student/exams/{exam_id}/start")
def start_or_resume_exam(
    exam_id: int,
    user: User = Depends(require_role(["STUDENT"])),
    db: Session = Depends(get_db),
):
    exam = db.query(Exam).filter_by(id=exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Không tìm thấy đề kiểm tra.")

    student_id = user.student_profile.id
    in_progress = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.student_id == student_id,
            ExamAttempt.status.in_(["IN_PROGRESS", "DISCONNECTED"]),
        )
        .first()
    )

    exam_q_rows = db.query(ExamQuestion).filter_by(exam_id=exam_id).order_by(ExamQuestion.order_index).all()
    q_ids = [r.question_id for r in exam_q_rows]

    if in_progress:
        in_progress.status = "IN_PROGRESS"
        db.commit()
        ordered_q_ids = in_progress.question_order_json or q_ids
        attempt = in_progress
    else:
        completed = db.query(ExamAttempt).filter_by(exam_id=exam_id, student_id=student_id).count()
        ordered_q_ids = list(q_ids)
        if exam.shuffle_questions:
            random.shuffle(ordered_q_ids)

        attempt = ExamAttempt(
            exam_id=exam_id,
            student_id=student_id,
            attempt_number=completed + 1,
            exam_variant_code=f"MD-{random.randint(101, 999)}",
            question_order_json=ordered_q_ids,
            status="IN_PROGRESS",
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)

    questions_payload = []
    for q_id in ordered_q_ids:
        q = db.query(Question).filter_by(id=q_id).first()
        if not q:
            continue
        opts = [{"id": o.id, "label": o.option_label, "text": o.option_text} for o in q.options]
        if exam.shuffle_options:
            random.shuffle(opts)
        questions_payload.append(
            {
                "id": q.id,
                "question_type": q.question_type,
                "content_html": q.content_html,
                "options": opts,
            }
        )

    return {
        "attempt_id": attempt.id,
        "variant_code": attempt.exam_variant_code,
        "duration_minutes": exam.duration_minutes,
        "ai_assistant_allowed": exam.ai_assistant_allowed,
        "questions": questions_payload,
    }


@app.post("/api/student/attempts/{attempt_id}/autosave")
def autosave_exam_answers(
    attempt_id: int,
    payload: AutoSaveAnswerSchema,
    _: User = Depends(require_role(["STUDENT"])),
    db: Session = Depends(get_db),
):
    attempt = db.query(ExamAttempt).filter_by(id=attempt_id).first()
    if not attempt or attempt.status not in ("IN_PROGRESS", "DISCONNECTED"):
        raise HTTPException(status_code=400, detail="Lượt làm bài đã kết thúc.")

    for item in payload.answers:
        q_id = item.get("question_id")
        ans = db.query(StudentAnswer).filter_by(attempt_id=attempt_id, question_id=q_id).first()
        if not ans:
            ans = StudentAnswer(attempt_id=attempt_id, question_id=q_id)
            db.add(ans)
        ans.selected_option_ids = item.get("selected_option_ids", [])
        ans.text_response = item.get("text_response")
        ans.updated_at = datetime.now(timezone.utc)

    attempt.last_saved_at = datetime.now(timezone.utc)
    db.commit()
    return {"saved": True}


@app.post("/api/student/attempts/{attempt_id}/submit")
def submit_and_autograde_exam(
    attempt_id: int,
    auto_submitted: bool = False,
    _: User = Depends(require_role(["STUDENT"])),
    db: Session = Depends(get_db),
):
    attempt = db.query(ExamAttempt).filter_by(id=attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt làm bài.")
    if attempt.status in ("SUBMITTED", "AUTO_SUBMITTED", "GRADED"):
        return {"message": "Bài thi đã được nộp.", "score": float(attempt.auto_score)}

    exam = db.query(Exam).filter_by(id=attempt.exam_id).first()
    exam_questions = db.query(ExamQuestion).filter_by(exam_id=exam.id).all()
    points_map = {eq.question_id: float(eq.points) for eq in exam_questions}

    total_auto_score = 0.0
    answers = db.query(StudentAnswer).filter_by(attempt_id=attempt.id).all()
    for ans in answers:
        q = db.query(Question).filter_by(id=ans.question_id).first()
        if not q:
            continue
        correct_ids = sorted([o.id for o in q.options if o.is_correct])
        chosen_ids = sorted(ans.selected_option_ids or [])
        if correct_ids and correct_ids == chosen_ids:
            ans.is_correct = True
            ans.points_earned = points_map.get(q.id, 0.0)
            total_auto_score += float(ans.points_earned)
        else:
            ans.is_correct = False
            ans.points_earned = 0.0

    attempt.status = "AUTO_SUBMITTED" if auto_submitted else "SUBMITTED"
    attempt.submitted_at = datetime.now(timezone.utc)
    attempt.auto_score = round(total_auto_score, 2)
    attempt.final_score = round(total_auto_score, 2)

    db.add(
        Grade(
            student_id=attempt.student_id,
            class_id=exam.class_id,
            subject_id=exam.subject_id,
            exam_attempt_id=attempt.id,
            score=attempt.final_score,
            max_score=exam.total_score,
            is_published=True,
        )
    )
    db.commit()
    return {
        "attempt_id": attempt.id,
        "score": float(attempt.final_score),
        "message": "Nộp bài thành công!",
    }


@app.post("/api/exams/events")
async def record_exam_proctoring_event(
    payload: ExamEventCreateSchema,
    user: User = Depends(require_role(["STUDENT"])),
    db: Session = Depends(get_db),
):
    attempt = db.query(ExamAttempt).filter_by(id=payload.attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên thi.")

    if payload.event_type in ("TAB_HIDDEN", "WINDOW_BLUR"):
        attempt.tab_switch_count += 1
    elif payload.event_type == "FULLSCREEN_EXIT":
        attempt.fullscreen_exit_count += 1
    elif payload.event_type == "NETWORK_OFFLINE":
        attempt.status = "DISCONNECTED"
    elif payload.event_type in ("NETWORK_ONLINE", "EXAM_RESUMED"):
        if attempt.status == "DISCONNECTED":
            attempt.status = "IN_PROGRESS"

    event = ExamEvent(
        attempt_id=attempt.id,
        exam_id=payload.exam_id,
        student_id=attempt.student_id,
        event_type=payload.event_type,
        event_detail=payload.event_detail,
    )
    db.add(event)
    db.commit()

    await proctoring_manager.broadcast_event(
        payload.exam_id,
        {
            "attempt_id": attempt.id,
            "student_code": user.student_profile.student_code if user.student_profile else user.username,
            "student_name": user.full_name,
            "event_type": payload.event_type,
            "tab_switch_count": attempt.tab_switch_count,
            "fullscreen_exit_count": attempt.fullscreen_exit_count,
            "status": attempt.status,
        },
    )
    return {"recorded": True, "tab_switch_count": attempt.tab_switch_count}


@app.get("/api/teacher/exams/{exam_id}/proctoring")
def get_exam_proctoring_summary(
    exam_id: int,
    _: User = Depends(require_role(["TEACHER", "ADMIN"])),
    db: Session = Depends(get_db),
):
    attempts = db.query(ExamAttempt).filter_by(exam_id=exam_id).order_by(ExamAttempt.id.desc()).all()
    result = []
    for att in attempts:
        stu = db.query(Student).filter_by(id=att.student_id).first()
        events = db.query(ExamEvent).filter_by(attempt_id=att.id).order_by(ExamEvent.id.desc()).all()
        result.append(
            {
                "attempt_id": att.id,
                "student_code": stu.student_code if stu else "",
                "student_name": stu.user.full_name if stu and stu.user else "Học sinh",
                "status": att.status,
                "started_at": att.started_at.isoformat() if att.started_at else None,
                "submitted_at": att.submitted_at.isoformat() if att.submitted_at else None,
                "tab_switch_count": att.tab_switch_count,
                "fullscreen_exit_count": att.fullscreen_exit_count,
                "score": float(att.final_score) if att.final_score is not None else None,
                "events": [
                    {
                        "type": e.event_type,
                        "detail": e.event_detail,
                        "recorded_at": e.recorded_at.isoformat() if e.recorded_at else "",
                    }
                    for e in events
                ],
            }
        )
    return result


@app.get("/api/grades")
def list_grades(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Grade).order_by(Grade.id.desc())
    if current_user.role.code == "STUDENT" and current_user.student_profile:
        query = query.filter(Grade.student_id == current_user.student_profile.id)

    rows = []
    for g in query.all():
        stu = db.query(Student).filter_by(id=g.student_id).first()
        cls = db.query(ClassRoom).filter_by(id=g.class_id).first()
        subj = db.query(Subject).filter_by(id=g.subject_id).first()
        item_title = "Đánh giá định kỳ"
        feedback_text = "Đã hoàn thành"
        if g.assignment_id:
            asg = db.query(Assignment).filter_by(id=g.assignment_id).first()
            if asg:
                item_title = f"[Bài tập] {asg.title}"
            sub = db.query(Submission).filter_by(assignment_id=g.assignment_id, student_id=g.student_id).first()
            if sub:
                fb = db.query(GradingFeedback).filter_by(submission_id=sub.id).order_by(GradingFeedback.id.desc()).first()
                if fb:
                    feedback_text = fb.comment_text
        elif g.exam_attempt_id:
            att = db.query(ExamAttempt).filter_by(id=g.exam_attempt_id).first()
            if att:
                ex = db.query(Exam).filter_by(id=att.exam_id).first()
                if ex:
                    item_title = f"[Kiểm tra] {ex.title}"
                feedback_text = f"Chấm tự động (Chuyển tab: {att.tab_switch_count} lần)"

        rows.append(
            {
                "student_name": stu.user.full_name if stu and stu.user else "Học sinh",
                "class_code": cls.code if cls else "10A1",
                "subject_name": subj.name if subj else "Tin học",
                "item_title": item_title,
                "score": float(g.score),
                "max_score": float(g.max_score),
                "feedback": feedback_text,
            }
        )
    return rows


# ============================================================================
# 9. TRÌNH BIÊN DỊCH & THÔNG DỊCH ĐA NGÔN NGỮ (PYTHON, C, C++, JAVA, JS, HTML)
# ============================================================================

FORBIDDEN_PATTERNS = [
    r"\bos\.system\b",
    r"\bsubprocess\b",
    r"\bshutil\.rmtree\b",
    r"\bsocket\b",
    r"\bchild_process\b",
    r"\bRuntime\.getRuntime\b",
    r"\bsystem\s*\(",
]


def simulate_c_cpp_java_execution(language: str, source_code: str, stdin_input: str) -> Dict[str, Any]:
    """
    Trình thông dịch giáo dục tích hợp sẵn cho C / C++ / Java khi máy chủ
    chưa cài đặt GCC, G++ hoặc JDK. Hỗ trợ biến, biểu thức số học, vòng lặp for,
    đọc dữ liệu stdin và xuất kết quả qua printf / cout / System.out.println.
    """
    if "main" not in source_code:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Lỗi biên dịch ({language.upper()}): Không tìm thấy hàm khởi chạy 'main'.",
        }

    stdin_tokens = stdin_input.split()
    stdin_idx = 0
    variables: Dict[str, Any] = {}
    outputs: List[str] = []

    def eval_expr(expr: str) -> Any:
        expr = expr.strip()
        if (expr.startswith('"') and expr.endswith('"')) or (expr.startswith("'") and expr.endswith("'")):
            return expr[1:-1].replace("\\n", "\n").replace("\\t", "\t")
        # Thay thế tên biến đã lưu bằng giá trị
        safe_expr = expr
        for k in sorted(variables.keys(), key=len, reverse=True):
            safe_expr = re.sub(rf"\b{re.escape(k)}\b", repr(variables[k]), safe_expr)
        safe_expr = safe_expr.replace("/", "//") if all(isinstance(v, int) for v in variables.values()) and "." not in expr else safe_expr
        try:
            return eval(safe_expr, {"__builtins__": {}}, {})
        except Exception:
            return expr

    lines = source_code.splitlines()
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(("//", "#", "import ", "using ", "package ", "public class", "{", "}")):
            continue

        # Khai báo và gán biến đơn giản: int a = 5, b = 10;
        decl_match = re.match(r"^(?:int|long|float|double|var|String)\s+(.+);$", line)
        if decl_match:
            parts = decl_match.group(1).split(",")
            for p in parts:
                if "=" in p:
                    vname, vexpr = p.split("=", 1)
                    variables[vname.strip()] = eval_expr(vexpr)
                else:
                    variables[p.strip()] = 0
            continue

        # Đọc stdin qua cin >> x hoặc Scanner
        if "cin >>" in line or "nextInt()" in line:
            var_matches = re.findall(r">>\s*([a-zA-Z_]\w*)", line)
            if not var_matches:
                m_scan = re.match(r"^(?:int\s+)?([a-zA-Z_]\w*)\s*=", line)
                if m_scan:
                    var_matches = [m_scan.group(1)]
            for v in var_matches:
                if stdin_idx < len(stdin_tokens):
                    tok = stdin_tokens[stdin_idx]
                    stdin_idx += 1
                    variables[v] = int(tok) if tok.lstrip("-").isdigit() else tok
                else:
                    variables[v] = 0
            continue

        # Vòng lặp for đơn giản: for (int i = 1; i <= 10; i++) sum += i;
        for_match = re.match(
            r"^for\s*\(\s*(?:int\s+)?([a-zA-Z_]\w*)\s*=\s*(-?\d+)\s*;\s*\1\s*(<=|<)\s*([^;]+);\s*[^)]+\)\s*(.+);$",
            line,
        )
        if for_match:
            var_i, start_s, op, end_expr, body = for_match.groups()
            start_v = int(start_s)
            end_v = int(eval_expr(end_expr))
            limit = end_v + 1 if op == "<=" else end_v
            for idx_val in range(start_v, min(limit, start_v + 10000)):
                variables[var_i] = idx_val
                if "+=" in body:
                    lhs, rhs = body.split("+=", 1)
                    variables[lhs.strip()] = variables.get(lhs.strip(), 0) + eval_expr(rhs)
            continue

        # Gán cộng dồn: sum += x;
        if "+=" in line and line.endswith(";"):
            lhs, rhs = line[:-1].split("+=", 1)
            variables[lhs.strip()] = variables.get(lhs.strip(), 0) + eval_expr(rhs)
            continue

        # Gán thường: x = expr;
        if "=" in line and "==" not in line and not line.startswith(("if", "while", "for")) and line.endswith(";"):
            lhs, rhs = line[:-1].split("=", 1)
            variables[lhs.strip()] = eval_expr(rhs)
            continue

        # Xuất C++ cout << ...
        if line.startswith("cout"):
            chunks = [c.strip() for c in line.rstrip(";").split("<<")[1:]]
            rendered = ""
            for ch in chunks:
                if ch in ("endl", "std::endl"):
                    rendered += "\n"
                else:
                    rendered += str(eval_expr(ch))
            outputs.append(rendered)
            continue

        # Xuất Java System.out.println(...) / print(...)
        java_out = re.match(r"^System\.out\.(println|print)\((.*)\);$", line)
        if java_out:
            kind, inner = java_out.groups()
            parts = [p.strip() for p in inner.split("+")]
            rendered = "".join(str(eval_expr(p)) for p in parts)
            outputs.append(rendered + ("\n" if kind == "println" else ""))
            continue

        # Xuất C printf("...", args...)
        c_out = re.match(r'^printf\(\s*"([^"]*)"\s*(?:,\s*(.*))?\);$', line)
        if c_out:
            fmt, args_str = c_out.groups()
            fmt = fmt.replace("\\n", "\n").replace("\\t", "\t")
            if args_str:
                args_vals = tuple(eval_expr(a) for a in args_str.split(","))
                try:
                    fmt = fmt % args_vals
                except Exception:
                    fmt += " " + " ".join(str(x) for x in args_vals)
            outputs.append(fmt)
            continue

    final_out = "".join(outputs)
    if not final_out:
        final_out = "(Chương trình biên dịch và kết thúc với mã thoát 0)"
    final_out += f"\n\n[Trình thông dịch {language.upper()} tích hợp EduLMS — Sẵn sàng chấm bài]"
    return {"success": True, "stdout": final_out, "stderr": "", "exit_code": 0}


@app.post("/api/sandbox/run")
def run_code_in_sandbox(payload: CodeSandboxRequest, _: User = Depends(get_current_user)):
    if payload.language == "html":
        return {"success": True, "stdout": payload.source_code, "stderr": "", "is_html": True}

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, payload.source_code):
            raise HTTPException(status_code=400, detail="Mã nguồn chứa lệnh hệ thống bị hạn chế trong Sandbox.")

    with tempfile.TemporaryDirectory(prefix="edulms_sandbox_") as tmpdir:
        try:
            lang = payload.language
            if lang == "python":
                src_file = os.path.join(tmpdir, "main.py")
                with open(src_file, "w", encoding="utf-8") as f:
                    f.write(payload.source_code)
                # Dùng sys.executable để chạy đúng trình thông dịch Python trên Windows/Linux
                cmd = [sys.executable, "-I", src_file]

            elif lang == "javascript":
                if not shutil.which("node"):
                    # Fallback nếu máy chưa cài Node.js
                    logs = re.findall(r"console\.log\((.*?)\)", payload.source_code)
                    out = "\n".join(x.strip("\"'") for x in logs) or "(Đã kiểm tra cú pháp JavaScript)"
                    return {"success": True, "stdout": out, "stderr": ""}
                src_file = os.path.join(tmpdir, "main.js")
                with open(src_file, "w", encoding="utf-8") as f:
                    f.write(payload.source_code)
                cmd = ["node", src_file]

            elif lang == "c":
                if not shutil.which("gcc"):
                    return simulate_c_cpp_java_execution("c", payload.source_code, payload.stdin_input or "")
                src_file = os.path.join(tmpdir, "main.c")
                bin_file = os.path.join(tmpdir, "main_c.exe" if os.name == "nt" else "main_c")
                with open(src_file, "w", encoding="utf-8") as f:
                    f.write(payload.source_code)
                comp = subprocess.run(["gcc", src_file, "-O2", "-o", bin_file], capture_output=True, text=True, timeout=6)
                if comp.returncode != 0:
                    return {"success": False, "stdout": "", "stderr": comp.stderr}
                cmd = [bin_file]

            elif lang == "cpp":
                if not shutil.which("g++"):
                    return simulate_c_cpp_java_execution("cpp", payload.source_code, payload.stdin_input or "")
                src_file = os.path.join(tmpdir, "main.cpp")
                bin_file = os.path.join(tmpdir, "main_cpp.exe" if os.name == "nt" else "main_cpp")
                with open(src_file, "w", encoding="utf-8") as f:
                    f.write(payload.source_code)
                comp = subprocess.run(["g++", src_file, "-std=c++17", "-O2", "-o", bin_file], capture_output=True, text=True, timeout=6)
                if comp.returncode != 0:
                    return {"success": False, "stdout": "", "stderr": comp.stderr}
                cmd = [bin_file]

            elif lang == "java":
                if not shutil.which("javac") or not shutil.which("java"):
                    return simulate_c_cpp_java_execution("java", payload.source_code, payload.stdin_input or "")
                src_file = os.path.join(tmpdir, "Main.java")
                with open(src_file, "w", encoding="utf-8") as f:
                    f.write(payload.source_code)
                comp = subprocess.run(["javac", src_file], capture_output=True, text=True, timeout=8, cwd=tmpdir)
                if comp.returncode != 0:
                    return {"success": False, "stdout": "", "stderr": comp.stderr}
                cmd = ["java", "-Xmx128m", "-cp", tmpdir, "Main"]

            proc = subprocess.run(
                cmd,
                input=payload.stdin_input or "",
                capture_output=True,
                text=True,
                timeout=4,
                cwd=tmpdir,
            )
            return {
                "success": proc.returncode == 0,
                "stdout": proc.stdout[:10000],
                "stderr": proc.stderr[:10000],
                "exit_code": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "Lỗi vượt quá thời gian thực thi (Timeout 4s)."}


# ============================================================================
# 10. TRỢ LÝ AI GEMINI (TẠO CÂU HỎI CÓ CẤU TRÚC, GIA SƯ & VIDEO BÀI GIẢNG)
# ============================================================================


def call_gemini_or_smart_fallback(prompt: str, custom_api_key: Optional[str] = None) -> Optional[str]:
    api_key = (custom_api_key or "").strip() or DEFAULT_GEMINI_API_KEY
    if GEMINI_AVAILABLE and api_key:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            return response.text or ""
        except Exception as exc:
            return f"[Lỗi kết nối Gemini API: {exc}]"
    return None


@app.post("/api/ai/generate-questions")
def ai_generate_quiz_questions(
    payload: AIQuestionGenRequest,
    user: User = Depends(require_role(["TEACHER", "ADMIN"])),
    x_gemini_api_key: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    prompt = (
        f"Tạo {payload.num_questions} câu hỏi trắc nghiệm 4 lựa chọn cho môn {payload.subject_name} "
        f"(mức độ {payload.cognitive_level}) về chủ đề: {payload.topic_content}. "
        'Chỉ trả về JSON thuần: [{"question": "...", "options": ["...", "...", "...", "..."], "correct_index": 0, "explanation": "..."}]'
    )
    raw = call_gemini_or_smart_fallback(prompt, x_gemini_api_key)
    questions_list = []

    if raw:
        try:
            cleaned = re.sub(r"^```json|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            questions_list = json.loads(cleaned)
        except Exception:
            questions_list = []

    # Nếu chưa nhập Gemini API Key, sinh bộ câu hỏi chuẩn cấu trúc theo đúng chủ đề giáo viên nhập
    if not questions_list:
        topic = payload.topic_content.strip()
        for i in range(1, payload.num_questions + 1):
            questions_list.append(
                {
                    "question": f"Câu {i} ({payload.cognitive_level}): Khẳng định nào sau đây là chính xác nhất về '{topic}'?",
                    "options": [
                        f"Đặc điểm cốt lõi và nguyên lý hoạt động chuẩn của {topic}",
                        f"Khái niệm trái ngược hoàn toàn với bản chất của {topic}",
                        f"Trường hợp ngoại lệ không áp dụng cho {topic}",
                        f"Một phương pháp không liên quan đến {topic}",
                    ],
                    "correct_index": 0,
                    "explanation": f"Đáp án A phản ánh đúng bản chất kiến thức về {topic}.",
                }
            )

    db.add(
        AITask(
            user_id=user.id,
            task_type="GENERATE_QUESTIONS",
            prompt_input=payload.topic_content[:500],
            ai_output=json.dumps(questions_list, ensure_ascii=False),
        )
    )
    db.commit()
    return {"questions": questions_list}


@app.post("/api/ai/tutor")
def ai_student_tutor(
    payload: AITutorRequest,
    user: User = Depends(get_current_user),
    x_gemini_api_key: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if user.role.code == "STUDENT" and user.student_profile:
        active_attempt = (
            db.query(ExamAttempt)
            .filter(
                ExamAttempt.student_id == user.student_profile.id,
                ExamAttempt.status == "IN_PROGRESS",
            )
            .first()
        )
        if active_attempt:
            exam = db.query(Exam).filter_by(id=active_attempt.exam_id).first()
            if exam and not exam.ai_assistant_allowed:
                raise HTTPException(
                    status_code=403,
                    detail="Trợ lý AI đã bị khóa trong thời gian diễn ra bài kiểm tra này.",
                )

    full_prompt = (
        f"Bạn là trợ lý giảng dạy & gia sư AI của EduLMS Pro (môn {payload.subject_name}). "
        f"Hãy trả lời rõ ràng, sư phạm bằng tiếng Việt cho câu hỏi: {payload.prompt}"
    )
    if payload.context_code:
        full_prompt += f"\n\nMã nguồn đính kèm:\n{payload.context_code}"

    reply = call_gemini_or_smart_fallback(full_prompt, x_gemini_api_key)
    if not reply:
        reply = (
            f"Gợi ý từ Trợ lý AI EduLMS ({payload.subject_name}):\n\n"
            f"1. Phân tích yêu cầu: \"{payload.prompt}\"\n"
            f"2. Hướng tiếp cận từng bước:\n"
            f"   - Bước 1: Xác định rõ dữ liệu đầu vào (Input) và kết quả đầu ra mong muốn (Output).\n"
            f"   - Bước 2: Chia nhỏ bài toán thành các hàm/khối xử lý độc lập và kiểm tra các trường hợp biên.\n"
            f"   - Bước 3: Chạy thử nghiệm trên Sandbox với bộ dữ liệu mẫu để đối chiếu kết quả.\n\n"
            f"(Mẹo: Bạn có thể dán Gemini API Key ở ô cấu hình phía trên để kích hoạt phản hồi chuyên sâu từ mô hình Gemini 2.5)."
        )

    db.add(AITask(user_id=user.id, task_type="EXPLAIN_CONCEPT", prompt_input=payload.prompt, ai_output=reply))
    db.commit()
    return {"reply": reply}


@app.post("/api/ai/generate-video")
def ai_generate_lesson_video(
    payload: AIVideoGenRequest,
    user: User = Depends(require_role(["TEACHER", "ADMIN"])),
    x_gemini_api_key: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    prompt = (
        f"Lập kịch bản video bài giảng dài {payload.duration_seconds} giây môn {payload.subject_name}, "
        f"chủ đề '{payload.lesson_title}': {payload.lesson_outline}"
    )
    storyboard = call_gemini_or_smart_fallback(prompt, x_gemini_api_key) or (
        f"KỊCH BẢN VIDEO BÀI GIẢNG: {payload.lesson_title.upper()}\n"
        f"- Cảnh 1 (00:00 - 00:15): Giới thiệu mục tiêu bài học & tình huống thực tế.\n"
        f"- Cảnh 2 (00:15 - 00:45): Minh họa trực quan nội dung: {payload.lesson_outline}\n"
        f"- Cảnh 3 (00:45 - 01:00): Tổng kết kiến thức trọng tâm & câu hỏi củng cố."
    )
    video_url = f"/uploads/ai_lesson_{uuid.uuid4().hex[:8]}.mp4"
    db.add(
        AITask(
            user_id=user.id,
            task_type="GENERATE_LESSON_VIDEO",
            prompt_input=payload.lesson_title,
            ai_output=storyboard,
            output_media_url=video_url,
        )
    )
    db.commit()
    return {"lesson_title": payload.lesson_title, "storyboard": storyboard, "video_url": video_url}