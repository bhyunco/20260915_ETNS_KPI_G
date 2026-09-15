"""데이터베이스 모델(테이블) 정의.

이 시스템은 4개의 테이블로 이루어진다.

    Department (부서)  1 ──< User (조직원)  1 ──< Kpi (KPI)  1 ──< KpiUpdate (실적 입력 이력)

읽는 순서는 위에서 아래로, Department → User → Kpi → KpiUpdate 가 자연스럽다.
"""
from datetime import date, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager

# --------------------------------------------------------------------------
# 상수 정의
# 문자열을 코드 여기저기에 직접 쓰면 오타가 나기 쉬워서 한 곳에 모아 둔다.
# --------------------------------------------------------------------------

ROLE_ADMIN = "admin"  # 관리자
ROLE_MEMBER = "member"  # 조직원

ROLE_LABELS = {
    ROLE_ADMIN: "관리자",
    ROLE_MEMBER: "조직원",
}

# KPI 상태 4가지. 상태는 사람이 고르는 것이 아니라 실적과 날짜로 자동 판정한다.
STATUS_ACHIEVED = "achieved"  # 달성
STATUS_ON_TRACK = "on_track"  # 진행중
STATUS_DELAYED = "delayed"  # 지연
STATUS_FAILED = "failed"  # 미달

STATUS_LABELS = {
    STATUS_ACHIEVED: "달성",
    STATUS_ON_TRACK: "진행중",
    STATUS_DELAYED: "지연",
    STATUS_FAILED: "미달",
}

# 화면에서 상태별 색을 입힐 때 쓰는 부트스트랩 색상 이름.
STATUS_COLORS = {
    STATUS_ACHIEVED: "success",
    STATUS_ON_TRACK: "primary",
    STATUS_DELAYED: "warning",
    STATUS_FAILED: "danger",
}

# 차트(Chart.js)에서 쓸 실제 색상 코드.
STATUS_CHART_COLORS = {
    STATUS_ACHIEVED: "#198754",
    STATUS_ON_TRACK: "#0d6efd",
    STATUS_DELAYED: "#ffc107",
    STATUS_FAILED: "#dc3545",
}

# KPI 단위 선택지. 요청서의 "%, 건, 원, 점 등" 을 그대로 반영했다.
UNIT_CHOICES = ["%", "건", "원", "점", "명", "시간", "개"]


class Department(db.Model):
    """부서 테이블.

    부서를 문자열로 조직원 테이블에 직접 적지 않고 별도 테이블로 뺀 이유는,
    부서 이름이 바뀌었을 때 한 곳만 고치면 되고 부서별 집계가 정확해지기 때문이다.
    """

    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)  # 부서명 (중복 불가)
    description = db.Column(db.String(200))  # 부서 설명 (선택)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    # 이 부서에 속한 조직원 목록. User.department 로 반대 방향도 접근할 수 있다.
    members = db.relationship("User", back_populates="department", lazy="selectin")

    def __repr__(self):
        return f"<Department {self.name}>"


class User(db.Model, UserMixin):
    """조직원(사용자) 테이블.

    UserMixin 을 함께 상속하면 Flask-Login 이 요구하는 is_authenticated,
    get_id() 같은 속성을 자동으로 갖추게 된다.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    employee_no = db.Column(db.String(30), nullable=False, unique=True)  # 사번
    name = db.Column(db.String(50), nullable=False)  # 이름
    email = db.Column(db.String(120), nullable=False, unique=True)  # 이메일
    position = db.Column(db.String(50))  # 직급

    username = db.Column(db.String(50), nullable=False, unique=True)  # 로그인 아이디
    password_hash = db.Column(db.String(255), nullable=False)  # 비밀번호 해시

    role = db.Column(db.String(20), nullable=False, default=ROLE_MEMBER)  # 권한
    is_active_user = db.Column(db.Boolean, nullable=False, default=True)  # 활성/비활성

    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"))
    department = db.relationship("Department", back_populates="members")

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    # 이 조직원에게 배정된 KPI 목록.
    # cascade 설정으로, 조직원을 지우면 그 사람의 KPI 와 이력도 함께 지워진다.
    kpis = db.relationship(
        "Kpi",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ----- 비밀번호 처리 -------------------------------------------------
    # 비밀번호는 절대 평문으로 저장하지 않는다. 해시만 저장하고, 로그인할 때는
    # 입력값을 같은 방식으로 해시해서 비교한다. 해시는 되돌릴 수 없으므로
    # DB 가 유출되어도 원래 비밀번호를 알 수 없다.

    def set_password(self, raw_password):
        """평문 비밀번호를 받아 해시로 바꿔 저장한다."""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        """입력한 비밀번호가 맞는지 확인한다."""
        return check_password_hash(self.password_hash, raw_password)

    # ----- 권한 판별 -----------------------------------------------------

    @property
    def is_admin(self):
        """관리자인지 여부."""
        return self.role == ROLE_ADMIN

    @property
    def role_label(self):
        """화면에 보여줄 권한 이름(관리자/조직원)."""
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def department_name(self):
        """부서가 없을 수도 있으므로 안전하게 이름을 꺼낸다."""
        return self.department.name if self.department else "미지정"

    # ----- Flask-Login 연동 ----------------------------------------------

    @property
    def is_active(self):
        """Flask-Login 은 이 값이 False 인 계정의 로그인을 거부한다.

        비활성 처리된 계정이 곧바로 로그인할 수 없게 되는 지점이다.
        컬럼 이름을 is_active_user 로 따로 둔 것은, 이 속성 이름이
        Flask-Login 예약어라 컬럼과 이름이 겹치면 안 되기 때문이다.
        """
        return self.is_active_user

    # ----- KPI 요약 -------------------------------------------------------

    @property
    def kpi_count(self):
        """배정된 KPI 개수."""
        return len(self.kpis)

    @property
    def average_progress(self):
        """이 조직원의 가중치 반영 평균 진행률.

        가중치가 큰 KPI 일수록 평균에 더 크게 반영된다.
        KPI 가 하나도 없으면 0 을 돌려준다.
        """
        return weighted_average_progress(self.kpis)

    def __repr__(self):
        return f"<User {self.username} ({self.name})>"


class Kpi(db.Model):
    """KPI 테이블. 조직원 한 명에게 여러 개가 배정될 수 있다."""

    __tablename__ = "kpis"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    owner = db.relationship("User", back_populates="kpis")

    title = db.Column(db.String(150), nullable=False)  # KPI명
    description = db.Column(db.Text)  # KPI 설명

    target_value = db.Column(db.Float, nullable=False)  # 목표값
    current_value = db.Column(db.Float, nullable=False, default=0.0)  # 현재값
    unit = db.Column(db.String(20), nullable=False, default="%")  # 단위

    start_date = db.Column(db.Date, nullable=False)  # 시작일
    end_date = db.Column(db.Date, nullable=False)  # 종료일

    weight = db.Column(db.Float, nullable=False, default=1.0)  # 가중치(중요도)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(  # 최종 업데이트 일시
        db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    # 실적 입력 이력. 최신 기록이 먼저 오도록 정렬해 둔다.
    updates = db.relationship(
        "KpiUpdate",
        back_populates="kpi",
        cascade="all, delete-orphan",
        order_by="KpiUpdate.created_at.desc()",
        lazy="selectin",
    )

    # ----- 자동 계산 항목 --------------------------------------------------
    # 진행률과 상태는 DB 에 저장하지 않고 그때그때 계산한다.
    # 저장해 두면 현재값만 바뀌고 진행률은 옛날 값이 남는 불일치가 생길 수 있는데,
    # 계산해서 쓰면 그런 문제가 원천적으로 없다.

    @property
    def progress(self):
        """진행률(%) = 현재값 / 목표값 × 100.

        - 목표값이 0 이면 나눗셈을 할 수 없으므로 0 으로 처리한다.
        - 목표를 초과 달성할 수 있으므로 100 을 넘는 값도 그대로 돌려준다.
          (막대그래프에서만 100 으로 잘라 그린다)
        """
        if not self.target_value:
            return 0.0
        return round(self.current_value / self.target_value * 100, 1)

    @property
    def progress_capped(self):
        """진행률을 0~100 사이로 자른 값. 진행바 너비를 정할 때 쓴다."""
        return max(0.0, min(self.progress, 100.0))

    @property
    def expected_progress(self):
        """오늘 시점에 '이 정도는 진행되어 있어야 하는' 기준 진행률(%).

        전체 기간 중 지금까지 흘러간 비율을 그대로 쓴다.
        예를 들어 1월 1일~12월 31일 KPI 를 6월 30일에 보면 약 50% 가 된다.
        이 값과 실제 진행률을 비교해 '지연' 여부를 판정한다.
        """
        today = date.today()
        total_days = (self.end_date - self.start_date).days
        if total_days <= 0:
            # 시작일과 종료일이 같은 하루짜리 KPI.
            return 100.0 if today >= self.end_date else 0.0
        elapsed_days = (today - self.start_date).days
        ratio = elapsed_days / total_days * 100
        return max(0.0, min(ratio, 100.0))

    @property
    def status(self):
        """KPI 상태를 자동 판정한다.

        판정 순서가 중요하다. 위에서부터 차례로 확인한다.

        1. 진행률 100% 이상          -> 달성
        2. 종료일이 지났는데 100% 미만 -> 미달 (더 만회할 기간이 없다)
        3. 기대 진행률보다 10%p 넘게 뒤처짐 -> 지연 (아직 기간은 남았지만 속도가 느리다)
        4. 그 외                      -> 진행중

        3번의 '10%p' 는 약간의 들쭉날쭉함까지 지연으로 보지 않기 위한 여유값이다.
        """
        if self.progress >= 100:
            return STATUS_ACHIEVED
        if date.today() > self.end_date:
            return STATUS_FAILED
        if self.progress < self.expected_progress - 10:
            return STATUS_DELAYED
        return STATUS_ON_TRACK

    @property
    def status_label(self):
        """화면에 보여줄 상태 이름(달성/진행중/지연/미달)."""
        return STATUS_LABELS[self.status]

    @property
    def status_color(self):
        """상태에 대응하는 부트스트랩 색상 이름."""
        return STATUS_COLORS[self.status]

    @property
    def days_left(self):
        """종료일까지 남은 일수. 이미 지났으면 음수가 된다."""
        return (self.end_date - date.today()).days

    def apply_progress(self, new_value, note, actor):
        """현재값을 바꾸고 그 기록을 이력에 남긴다.

        현재값 수정과 이력 기록이 항상 함께 일어나야 하므로 한 메서드로 묶었다.
        따로 호출하게 두면 한쪽을 빠뜨려 이력이 비는 일이 생긴다.

        인자
            new_value : 새로 입력할 실적값
            note      : 입력 메모(선택)
            actor     : 입력을 수행한 사용자(User 객체)
        """
        previous = self.current_value
        self.current_value = new_value
        self.updated_at = datetime.now()

        history = KpiUpdate(
            kpi=self,
            previous_value=previous,
            new_value=new_value,
            note=note,
            updated_by_id=actor.id,
        )
        db.session.add(history)
        return history

    def to_dict(self):
        """API(JSON) 응답에 쓰는 형태로 변환한다."""
        return {
            "id": self.id,
            "title": self.title,
            "owner": self.owner.name,
            "department": self.owner.department_name,
            "target_value": self.target_value,
            "current_value": self.current_value,
            "unit": self.unit,
            "progress": self.progress,
            "status": self.status,
            "status_label": self.status_label,
            "weight": self.weight,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M"),
        }

    def __repr__(self):
        return f"<Kpi {self.title}>"


class KpiUpdate(db.Model):
    """KPI 실적 입력 이력 테이블.

    '누가, 언제, 얼마에서 얼마로 바꿨는지' 를 남긴다.
    실적은 사람이 직접 입력하는 값이라 나중에 근거를 확인할 수 있어야 한다.
    """

    __tablename__ = "kpi_updates"

    id = db.Column(db.Integer, primary_key=True)

    kpi_id = db.Column(db.Integer, db.ForeignKey("kpis.id"), nullable=False)
    kpi = db.relationship("Kpi", back_populates="updates")

    previous_value = db.Column(db.Float, nullable=False)  # 변경 전 값
    new_value = db.Column(db.Float, nullable=False)  # 변경 후 값
    note = db.Column(db.String(300))  # 입력 메모

    # 입력한 사람. 조직원 본인일 수도 있고 관리자가 대신 입력할 수도 있다.
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    @property
    def delta(self):
        """이번 입력으로 얼마나 올랐는지(내렸는지)."""
        return round(self.new_value - self.previous_value, 2)

    def __repr__(self):
        return f"<KpiUpdate kpi={self.kpi_id} {self.previous_value}->{self.new_value}>"


# --------------------------------------------------------------------------
# 여러 곳에서 함께 쓰는 계산 함수
# --------------------------------------------------------------------------


def weighted_average_progress(kpis):
    """KPI 목록의 가중치 반영 평균 진행률(%)을 구한다.

        평균 = Σ(진행률 × 가중치) / Σ(가중치)

    단순 평균이 아니라 가중 평균을 쓰는 이유는, 요청서에 KPI 마다 '중요도'
    가중치가 있기 때문이다. 중요한 KPI 가 조직 성과에 더 크게 반영되어야 한다.

    진행률은 100% 로 잘라서 계산한다. 한 KPI 를 300% 달성했다고 해서
    다른 미달 KPI 를 가려서는 안 되기 때문이다.
    """
    if not kpis:
        return 0.0

    total_weight = sum(k.weight for k in kpis)
    if total_weight <= 0:
        return 0.0

    weighted_sum = sum(k.progress_capped * k.weight for k in kpis)
    return round(weighted_sum / total_weight, 1)


def status_breakdown(kpis):
    """KPI 목록을 상태별로 세어 돌려준다.

    돌려주는 형태: {"achieved": 3, "on_track": 5, "delayed": 1, "failed": 0}
    KPI 가 하나도 없는 상태도 0 으로 나와야 차트가 깨지지 않으므로 모든 키를 채운다.
    """
    counts = {key: 0 for key in STATUS_LABELS}
    for kpi in kpis:
        counts[kpi.status] += 1
    return counts


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login 이 세션에 저장된 사용자 ID로 사용자를 다시 불러올 때 쓴다.

    요청이 들어올 때마다 호출되므로 여기서 무거운 작업을 하면 안 된다.
    """
    return db.session.get(User, int(user_id))
