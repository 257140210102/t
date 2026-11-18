import pathlib

# 1. Chuyển cấu hình main.py sang dùng tệp cơ sở dữ liệu SQLite cục bộ
main_path = pathlib.Path("main.py")
code = main_path.read_text(encoding="utf-8")
code = code.replace(
    "from sqlalchemy.dialects.postgresql import JSONB",
    "from sqlalchemy import JSON as JSONB",
)
code = code.replace(
    "postgresql://postgres:postgres@localhost:5432/edulms_pro",
    "sqlite:///./edulms_pro.db",
)
code = code.replace(
    "create_engine(DATABASE_URL, pool_pre_ping=True)",
    'create_engine(DATABASE_URL, connect_args={"check_same_thread": False})',
)
main_path.write_text(code, encoding="utf-8")

# 2. Khởi tạo toàn bộ bảng và dữ liệu tài khoản mặc định
from main import (
    Base,
    ClassRoom,
    Role,
    SessionLocal,
    Student,
    Subject,
    Teacher,
    User,
    engine,
    hash_password,
)

Base.metadata.create_all(bind=engine)
db = SessionLocal()

if not db.query(Role).first():
    r_admin = Role(code="ADMIN", name="Quản trị viên")
    r_teacher = Role(code="TEACHER", name="Giáo viên")
    r_student = Role(code="STUDENT", name="Học sinh")
    db.add_all([r_admin, r_teacher, r_student])
    db.flush()

    db.add_all([
        Subject(code="TIN", name="Tin học", color_hex="#2563EB"),
        Subject(code="TOAN", name="Toán học", color_hex="#059669"),
        Subject(code="VAN", name="Ngữ văn", color_hex="#D97706"),
        Subject(code="ANH", name="Tiếng Anh", color_hex="#7C3AED"),
    ])

    u_admin = User(
        role_id=r_admin.id,
        username="admin",
        email="admin@edulms.edu.vn",
        password_hash=hash_password("123456"),
        full_name="Quản trị viên Hệ thống",
    )
    u_gv = User(
        role_id=r_teacher.id,
        username="GV001",
        email="gv001@edulms.edu.vn",
        password_hash=hash_password("123456"),
        full_name="ThS. Trần Minh Tuấn",
    )
    u_hs = User(
        role_id=r_student.id,
        username="HS2026001",
        email="hs001@edulms.edu.vn",
        password_hash=hash_password("123456"),
        full_name="Nguyễn Ngọc Ánh",
    )
    db.add_all([u_admin, u_gv, u_hs])
    db.flush()

    gv_profile = Teacher(user_id=u_gv.id, teacher_code="GV001", department="Tổ Tin học")
    hs_profile = Student(user_id=u_hs.id, student_code="HS2026001")
    db.add_all([gv_profile, hs_profile])
    db.flush()

    db.add(
        ClassRoom(
            code="10A1",
            name="Lớp 10A1 - Năm học 2026-2027",
            homeroom_teacher_id=gv_profile.id,
            join_code="8F2A91C0",
        )
    )
    db.commit()

db.close()
print("HOÀN TẤT! Đã tạo tệp database 'edulms_pro.db' và 3 tài khoản mẫu (mật khẩu: 123456).")