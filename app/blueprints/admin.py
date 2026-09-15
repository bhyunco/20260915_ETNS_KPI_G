"""관리자 기능 블루프린트.

담당 범위
    - 대시보드 (조직 전체 / 부서별 / 조직원별 현황)
    - 조직원 관리 (등록 / 수정 / 삭제)
    - 부서 관리 (등록 / 수정 / 삭제)
    - KPI 관리 (등록 / 수정 / 삭제 / 실적 입력)

이 파일의 모든 라우트에는 @login_required 와 @admin_required 가 함께 붙는다.
하나라도 빠지면 조직원이 관리자 화면에 들어올 수 있으므로 주의해야 한다.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..forms import DepartmentForm, KpiForm, KpiProgressForm, UserForm
from ..models import Department, Kpi, KpiUpdate, User, status_breakdown
from ..utils import (
    admin_required,
    build_chart_payload,
    build_dashboard_summary,
    build_department_stats,
    build_member_stats,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


# url_prefix 덕분에 이 파일의 주소는 모두 /admin 으로 시작한다.
# 아래 before_request 는 이 블루프린트의 모든 라우트에 공통으로 먼저 실행된다.
@bp.before_request
@login_required
@admin_required
def require_admin():
    """관리자 화면 전체에 대한 공통 권한 검사.

    라우트마다 데코레이터를 붙이면 새 기능을 추가할 때 깜빡하기 쉽다.
    여기서 한 번에 막아 두면 이 파일에 무엇을 추가하든 자동으로 보호된다.
    """
    return None


# ==========================================================================
# 대시보드
# ==========================================================================


@bp.route("/")
@bp.route("/dashboard")
def dashboard():
    """관리자 대시보드. 조직 전체 현황을 한 화면에 모아 보여준다."""
    return render_template(
        "admin/dashboard.html",
        summary=build_dashboard_summary(),
        departments=build_department_stats(),
        members=build_member_stats(),
        # 최근에 입력된 실적 10건. 조직이 지금 움직이고 있는지 보여주는 지표다.
        recent_updates=KpiUpdate.query.order_by(KpiUpdate.created_at.desc()).limit(10).all(),
    )


@bp.route("/departments/stats")
def department_stats():
    """부서별 KPI 현황 상세 화면."""
    return render_template("admin/department_stats.html", departments=build_department_stats())


@bp.route("/members/stats")
def member_stats():
    """조직원별 KPI 현황 상세 화면."""
    return render_template("admin/member_stats.html", members=build_member_stats())


# ==========================================================================
# 조직원 관리
# ==========================================================================


@bp.route("/users")
def user_list():
    """조직원 목록. 요청서 5-2 의 표 항목을 모두 보여준다."""
    keyword = (request.args.get("q") or "").strip()

    query = User.query
    if keyword:
        # 이름, 사번, 아이디 중 아무 데나 걸리면 보여준다.
        like = f"%{keyword}%"
        query = query.filter(
            db.or_(
                User.name.like(like),
                User.employee_no.like(like),
                User.username.like(like),
            )
        )

    users = query.order_by(User.employee_no).all()
    return render_template("admin/user_list.html", users=users, keyword=keyword)


@bp.route("/users/new", methods=["GET", "POST"])
def user_create():
    """조직원 등록."""
    departments = Department.query.order_by(Department.name).all()
    form = UserForm(departments=departments, is_edit=False)

    if form.validate_on_submit():
        # 아이디/사번/이메일은 중복될 수 없다. DB 에도 unique 제약이 걸려 있지만,
        # 여기서 먼저 확인해야 사용자에게 어떤 항목이 문제인지 알려줄 수 있다.
        # (DB 제약만 믿으면 "저장 실패" 같은 불친절한 오류만 뜬다)
        error = _check_duplicates(form)
        if error:
            flash(error, "danger")
            return render_template("admin/user_form.html", form=form, mode="create")

        user = User(
            employee_no=form.employee_no.data.strip(),
            name=form.name.data.strip(),
            email=form.email.data.strip().lower(),
            position=(form.position.data or "").strip(),
            username=form.username.data.strip(),
            role=form.role.data,
            is_active_user=form.is_active_user.data,
            # 부서 선택에서 0 은 '미지정' 이므로 None 으로 바꿔 저장한다.
            department_id=form.department_id.data or None,
        )
        user.set_password(form.password.data)

        db.session.add(user)
        db.session.commit()

        flash(f"조직원 '{user.name}' 을(를) 등록했습니다.", "success")
        return redirect(url_for("admin.user_list"))

    return render_template("admin/user_form.html", form=form, mode="create")


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
def user_edit(user_id):
    """조직원 정보 수정."""
    user = User.query.get_or_404(user_id)
    departments = Department.query.order_by(Department.name).all()

    # obj=user 를 넘기면 폼의 각 칸이 기존 값으로 채워진 채 열린다.
    form = UserForm(obj=user, departments=departments, is_edit=True)

    # GET 요청일 때만 부서 선택값을 채운다. POST 때 덮어쓰면 사용자가 바꾼
    # 선택이 원래 값으로 되돌아가 버린다.
    if request.method == "GET":
        form.department_id.data = user.department_id or 0

    if form.validate_on_submit():
        error = _check_duplicates(form, exclude_id=user.id)
        if error:
            flash(error, "danger")
            return render_template("admin/user_form.html", form=form, mode="edit", user=user)

        # 마지막 남은 관리자의 권한을 조직원으로 내리면 아무도 관리자 화면에
        # 들어갈 수 없게 된다. 복구할 방법이 없으므로 미리 막는다.
        if user.is_admin and form.role.data != "admin" and _active_admin_count() <= 1:
            flash("마지막 관리자의 권한은 변경할 수 없습니다.", "warning")
            return render_template("admin/user_form.html", form=form, mode="edit", user=user)

        # 같은 이유로 마지막 관리자를 비활성화하는 것도 막는다.
        if user.is_admin and not form.is_active_user.data and _active_admin_count() <= 1:
            flash("마지막 관리자는 비활성화할 수 없습니다.", "warning")
            return render_template("admin/user_form.html", form=form, mode="edit", user=user)

        user.employee_no = form.employee_no.data.strip()
        user.name = form.name.data.strip()
        user.email = form.email.data.strip().lower()
        user.position = (form.position.data or "").strip()
        user.username = form.username.data.strip()
        user.role = form.role.data
        user.is_active_user = form.is_active_user.data
        user.department_id = form.department_id.data or None

        # 비밀번호 칸을 비워 두면 기존 비밀번호를 그대로 유지한다.
        if form.password.data:
            user.set_password(form.password.data)

        db.session.commit()
        flash(f"조직원 '{user.name}' 정보를 수정했습니다.", "success")
        return redirect(url_for("admin.user_list"))

    return render_template("admin/user_form.html", form=form, mode="edit", user=user)


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
def user_delete(user_id):
    """조직원 삭제.

    GET 이 아니라 POST 로만 받는 이유는, 주소만 눌러도 지워지면 곤란하기 때문이다.
    (검색엔진이나 브라우저가 링크를 미리 열어보는 것만으로 데이터가 사라질 수 있다)
    """
    user = User.query.get_or_404(user_id)

    # 자기 자신을 지우면 그 즉시 로그인 상태가 깨진다.
    if user.id == current_user.id:
        flash("본인 계정은 삭제할 수 없습니다.", "warning")
        return redirect(url_for("admin.user_list"))

    # 마지막 관리자를 지우면 시스템에 들어갈 수 있는 사람이 없어진다.
    if user.is_admin and _active_admin_count() <= 1:
        flash("마지막 관리자는 삭제할 수 없습니다.", "warning")
        return redirect(url_for("admin.user_list"))

    name = user.name
    # 모델의 cascade 설정에 따라 이 사람의 KPI 와 입력 이력도 함께 삭제된다.
    db.session.delete(user)
    db.session.commit()

    flash(f"조직원 '{name}' 을(를) 삭제했습니다.", "success")
    return redirect(url_for("admin.user_list"))


def _check_duplicates(form, exclude_id=None):
    """아이디/사번/이메일 중복을 확인한다.

    exclude_id : 수정 모드에서 '자기 자신' 은 중복으로 보지 않기 위해 제외할 ID.
                 이걸 빼먹으면 아무것도 안 바꾸고 저장해도 중복이라고 나온다.

    중복이 있으면 안내 문구를, 없으면 None 을 돌려준다.
    """
    checks = [
        (User.username, form.username.data.strip(), "이미 사용 중인 아이디입니다."),
        (User.employee_no, form.employee_no.data.strip(), "이미 등록된 사번입니다."),
        (User.email, form.email.data.strip().lower(), "이미 등록된 이메일입니다."),
    ]

    for column, value, message in checks:
        query = User.query.filter(column == value)
        if exclude_id is not None:
            query = query.filter(User.id != exclude_id)
        if query.first():
            return message

    return None


def _active_admin_count():
    """활성 상태인 관리자 수를 센다."""
    return User.query.filter_by(role="admin", is_active_user=True).count()


# ==========================================================================
# 부서 관리
# ==========================================================================


@bp.route("/departments", methods=["GET", "POST"])
def department_list():
    """부서 목록 + 등록. 부서는 항목이 적어 목록과 등록 폼을 한 화면에 둔다."""
    form = DepartmentForm()

    if form.validate_on_submit():
        name = form.name.data.strip()
        if Department.query.filter_by(name=name).first():
            flash("이미 등록된 부서명입니다.", "danger")
        else:
            db.session.add(
                Department(name=name, description=(form.description.data or "").strip())
            )
            db.session.commit()
            flash(f"부서 '{name}' 을(를) 등록했습니다.", "success")
            return redirect(url_for("admin.department_list"))

    return render_template(
        "admin/department_list.html",
        form=form,
        departments=Department.query.order_by(Department.name).all(),
    )


@bp.route("/departments/<int:dept_id>/edit", methods=["GET", "POST"])
def department_edit(dept_id):
    """부서 정보 수정."""
    dept = Department.query.get_or_404(dept_id)
    form = DepartmentForm(obj=dept)

    if form.validate_on_submit():
        name = form.name.data.strip()
        duplicate = Department.query.filter(
            Department.name == name, Department.id != dept.id
        ).first()
        if duplicate:
            flash("이미 등록된 부서명입니다.", "danger")
        else:
            dept.name = name
            dept.description = (form.description.data or "").strip()
            db.session.commit()
            flash("부서 정보를 수정했습니다.", "success")
            return redirect(url_for("admin.department_list"))

    return render_template("admin/department_form.html", form=form, dept=dept)


@bp.route("/departments/<int:dept_id>/delete", methods=["POST"])
def department_delete(dept_id):
    """부서 삭제."""
    dept = Department.query.get_or_404(dept_id)

    # 소속 조직원이 남아 있는 부서를 지우면 그 사람들의 소속이 사라진다.
    # 조직원을 먼저 다른 부서로 옮기도록 안내한다.
    if dept.members:
        flash(
            f"'{dept.name}' 부서에 소속된 조직원이 {len(dept.members)}명 있습니다. "
            "먼저 소속을 변경해 주세요.",
            "warning",
        )
        return redirect(url_for("admin.department_list"))

    name = dept.name
    db.session.delete(dept)
    db.session.commit()
    flash(f"부서 '{name}' 을(를) 삭제했습니다.", "success")
    return redirect(url_for("admin.department_list"))


# ==========================================================================
# KPI 관리
# ==========================================================================


@bp.route("/kpis")
def kpi_list():
    """전체 KPI 목록. 부서/상태로 걸러 볼 수 있다."""
    dept_id = request.args.get("department", type=int)
    status = request.args.get("status")

    kpis = Kpi.query.join(User).order_by(User.name, Kpi.end_date).all()

    # 부서 필터는 DB 질의로 거를 수 있지만, 상태는 계산해서 나오는 값이라
    # DB 에 없다. 그래서 두 필터 모두 파이썬에서 처리해 규칙을 한곳에 모았다.
    # (KPI 수가 수만 건을 넘어가면 상태를 컬럼으로 저장하는 방식으로 바꿔야 한다)
    if dept_id:
        kpis = [k for k in kpis if k.owner.department_id == dept_id]
    if status:
        kpis = [k for k in kpis if k.status == status]

    return render_template(
        "admin/kpi_list.html",
        kpis=kpis,
        departments=Department.query.order_by(Department.name).all(),
        selected_dept=dept_id,
        selected_status=status,
        status_counts=status_breakdown(kpis),
    )


@bp.route("/kpis/new", methods=["GET", "POST"])
def kpi_create():
    """KPI 등록."""
    users = _assignable_users()
    form = KpiForm(users=users)

    # 조직원이 한 명도 없으면 KPI 를 배정할 대상이 없다.
    if not users:
        flash("먼저 조직원을 등록해 주세요. KPI를 배정할 대상이 없습니다.", "warning")
        return redirect(url_for("admin.user_list"))

    if form.validate_on_submit():
        kpi = Kpi(
            user_id=form.user_id.data,
            title=form.title.data.strip(),
            description=(form.description.data or "").strip(),
            # DecimalField 는 Decimal 타입을 주는데, 모델 컬럼은 Float 이므로 변환한다.
            target_value=float(form.target_value.data),
            current_value=float(form.current_value.data or 0),
            unit=form.unit.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            weight=float(form.weight.data),
        )
        db.session.add(kpi)
        db.session.commit()

        flash(f"KPI '{kpi.title}' 을(를) 등록했습니다.", "success")
        return redirect(url_for("admin.kpi_list"))

    return render_template("admin/kpi_form.html", form=form, mode="create")


@bp.route("/kpis/<int:kpi_id>/edit", methods=["GET", "POST"])
def kpi_edit(kpi_id):
    """KPI 수정."""
    kpi = Kpi.query.get_or_404(kpi_id)
    form = KpiForm(obj=kpi, users=_assignable_users())

    if form.validate_on_submit():
        new_value = float(form.current_value.data or 0)

        # 관리자가 현재값을 바꿨다면 그것도 실적 변경이므로 이력에 남긴다.
        # 이력을 남기지 않으면 나중에 "숫자가 왜 바뀌었지?" 를 추적할 수 없다.
        if new_value != kpi.current_value:
            kpi.apply_progress(new_value, "관리자 수정", current_user)

        kpi.user_id = form.user_id.data
        kpi.title = form.title.data.strip()
        kpi.description = (form.description.data or "").strip()
        kpi.target_value = float(form.target_value.data)
        kpi.current_value = new_value
        kpi.unit = form.unit.data
        kpi.start_date = form.start_date.data
        kpi.end_date = form.end_date.data
        kpi.weight = float(form.weight.data)

        db.session.commit()
        flash(f"KPI '{kpi.title}' 을(를) 수정했습니다.", "success")
        return redirect(url_for("admin.kpi_detail", kpi_id=kpi.id))

    return render_template("admin/kpi_form.html", form=form, mode="edit", kpi=kpi)


@bp.route("/kpis/<int:kpi_id>")
def kpi_detail(kpi_id):
    """KPI 상세. 진행 상황과 입력 이력을 함께 보여준다."""
    kpi = Kpi.query.get_or_404(kpi_id)
    return render_template(
        "admin/kpi_detail.html",
        kpi=kpi,
        progress_form=KpiProgressForm(current_value=kpi.current_value),
    )


@bp.route("/kpis/<int:kpi_id>/progress", methods=["POST"])
def kpi_progress(kpi_id):
    """관리자가 KPI 실적을 대신 입력한다."""
    kpi = Kpi.query.get_or_404(kpi_id)
    form = KpiProgressForm()

    if form.validate_on_submit():
        kpi.apply_progress(
            float(form.current_value.data),
            (form.note.data or "").strip() or "관리자 입력",
            current_user,
        )
        db.session.commit()
        flash("실적을 반영했습니다.", "success")
    else:
        flash("실적 입력값을 확인해 주세요.", "danger")

    return redirect(url_for("admin.kpi_detail", kpi_id=kpi.id))


@bp.route("/kpis/<int:kpi_id>/delete", methods=["POST"])
def kpi_delete(kpi_id):
    """KPI 삭제. 입력 이력도 함께 삭제된다."""
    kpi = Kpi.query.get_or_404(kpi_id)
    title = kpi.title

    db.session.delete(kpi)
    db.session.commit()

    flash(f"KPI '{title}' 을(를) 삭제했습니다.", "success")
    return redirect(url_for("admin.kpi_list"))


def _assignable_users():
    """KPI 를 배정할 수 있는 조직원 목록(활성 계정만)."""
    return User.query.filter_by(is_active_user=True).order_by(User.name).all()


# ==========================================================================
# 대시보드 자동 갱신용 데이터
# ==========================================================================


@bp.route("/api/chart-data")
def chart_data():
    """대시보드 차트가 주기적으로 불러가는 JSON 데이터.

    페이지 전체를 새로고침하면 화면이 깜빡이고 스크롤 위치도 초기화된다.
    숫자만 받아와서 차트를 갈아끼우면 '실시간' 처럼 매끄럽게 갱신된다.
    """
    return build_chart_payload()
