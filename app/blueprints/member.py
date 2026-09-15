"""조직원 기능 블루프린트.

담당 범위
    - 본인 정보 확인
    - 본인 KPI 목록 / 상세 조회
    - KPI 현재 실적 입력
    - KPI 업데이트 이력 확인

이 파일에서 가장 중요한 원칙은 요청서 3-2 의 마지막 문장이다.

    "조직원은 다른 조직원의 KPI 정보를 조회하거나 수정할 수 없어야 한다."

이를 지키는 방법은 하나뿐이다. 화면에 링크를 안 그리는 것으로는 부족하고,
KPI 를 꺼내는 모든 지점에서 서버가 소유자를 직접 확인해야 한다.
그 확인은 utils.get_owned_kpi_or_404() 한 곳에 모아 두었다.
"""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..forms import KpiProgressForm
from ..models import KpiUpdate, status_breakdown, weighted_average_progress
from ..utils import get_owned_kpi_or_404

bp = Blueprint("member", __name__, url_prefix="/my")


@bp.before_request
@login_required
def require_login():
    """조직원 화면은 로그인만 하면 누구나(관리자 포함) 볼 수 있다.

    관리자도 본인에게 배정된 KPI 가 있을 수 있으므로 막지 않는다.
    다만 보이는 내용은 어디까지나 '로그인한 본인의 KPI' 뿐이다.
    """
    return None


@bp.route("/")
@bp.route("/kpi")
def my_kpi():
    """본인 KPI 목록. 조직원이 로그인하면 가장 먼저 보는 화면이다."""
    # current_user.kpis 는 로그인한 본인의 KPI 만 담고 있다.
    # DB 질의에 남의 것이 섞일 여지 자체가 없는 구조다.
    kpis = sorted(current_user.kpis, key=lambda k: (k.end_date, k.title))

    return render_template(
        "member/my_kpi.html",
        kpis=kpis,
        # 상단 요약: 본인 전체 진행률과 상태별 개수
        overall_progress=weighted_average_progress(kpis),
        status_counts=status_breakdown(kpis),
    )


@bp.route("/kpi/<int:kpi_id>")
def kpi_detail(kpi_id):
    """본인 KPI 상세 + 실적 입력 폼 + 업데이트 이력."""
    # 남의 KPI 번호를 주소창에 직접 넣으면 여기서 404 가 난다.
    kpi = get_owned_kpi_or_404(kpi_id, current_user)

    return render_template(
        "member/kpi_detail.html",
        kpi=kpi,
        # 폼에 현재값을 미리 채워 둔다. 대부분 기존 값에서 조금 올리는 식으로
        # 입력하므로, 빈 칸보다 현재값이 들어 있는 편이 쓰기 편하다.
        form=KpiProgressForm(current_value=kpi.current_value),
    )


@bp.route("/kpi/<int:kpi_id>/progress", methods=["POST"])
def update_progress(kpi_id):
    """KPI 현재 실적 입력."""
    kpi = get_owned_kpi_or_404(kpi_id, current_user)
    form = KpiProgressForm()

    if form.validate_on_submit():
        new_value = float(form.current_value.data)

        # 값이 그대로면 이력만 늘어나고 의미가 없으므로 저장하지 않는다.
        if new_value == kpi.current_value:
            flash("현재값과 동일하여 변경하지 않았습니다.", "info")
            return redirect(url_for("member.kpi_detail", kpi_id=kpi.id))

        kpi.apply_progress(new_value, (form.note.data or "").strip(), current_user)
        db.session.commit()

        flash(f"실적을 반영했습니다. 현재 진행률 {kpi.progress}%", "success")
    else:
        # 폼 검증에 걸린 이유를 그대로 보여준다.
        for errors in form.errors.values():
            for message in errors:
                flash(message, "danger")

    return redirect(url_for("member.kpi_detail", kpi_id=kpi.id))


@bp.route("/history")
def history():
    """본인이 입력한 KPI 업데이트 이력 전체."""
    # KpiUpdate 를 곧바로 조회하므로, 본인 KPI 의 이력만 나오도록
    # kpi_id 조건을 반드시 걸어야 한다.
    my_kpi_ids = [k.id for k in current_user.kpis]

    # KPI 가 하나도 없으면 IN () 조건이 되어 DB 마다 동작이 다를 수 있다.
    # 빈 목록이면 질의하지 않고 바로 빈 결과를 쓴다.
    if my_kpi_ids:
        updates = (
            KpiUpdate.query.filter(KpiUpdate.kpi_id.in_(my_kpi_ids))
            .order_by(KpiUpdate.created_at.desc())
            .all()
        )
    else:
        updates = []

    return render_template("member/history.html", updates=updates)


@bp.route("/profile")
def profile():
    """본인 정보 확인 화면."""
    kpis = current_user.kpis
    return render_template(
        "member/profile.html",
        overall_progress=weighted_average_progress(kpis),
        status_counts=status_breakdown(kpis),
    )
