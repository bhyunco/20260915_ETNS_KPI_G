"""여러 화면에서 함께 쓰는 보조 기능 모음.

- 권한 검사 데코레이터
- 대시보드 집계 함수
"""
from functools import wraps

from flask import abort
from flask_login import current_user

from .models import (
    STATUS_CHART_COLORS,
    STATUS_LABELS,
    Department,
    Kpi,
    User,
    status_breakdown,
    weighted_average_progress,
)


def admin_required(view):
    """관리자만 들어갈 수 있는 화면에 붙이는 데코레이터.

    사용법:
        @bp.route("/users")
        @login_required      # 먼저 로그인 여부를 확인하고
        @admin_required      # 그 다음 관리자인지 확인한다
        def user_list():
            ...

    순서가 중요하다. @login_required 가 위에 있어야 로그인하지 않은 사용자가
    403(권한 없음) 대신 로그인 화면으로 안내된다.

    권한이 없으면 403 을 낸다. 404 가 아니라 403 을 쓰는 이유는, 관리자 화면의
    주소는 숨겨야 할 비밀이 아니고 '권한이 부족하다' 는 사실을 알려주는 편이
    사용자에게 더 친절하기 때문이다.
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def get_owned_kpi_or_404(kpi_id, user):
    """KPI 를 가져오되, 볼 권한이 없으면 404 를 낸다.

    조직원이 주소창에 남의 KPI 번호를 직접 쳐 넣는 경우를 막는 핵심 장치다.
    화면에 링크를 안 그리는 것만으로는 전혀 막을 수 없기 때문에,
    서버에서 매번 소유자를 확인해야 한다.

    403 이 아니라 404 를 쓰는 이유는, 403 을 주면 '그 번호의 KPI 는 존재한다'
    는 사실이 드러나기 때문이다. 없는 것처럼 보이게 하는 편이 안전하다.
    """
    kpi = Kpi.query.get_or_404(kpi_id)

    # 관리자는 모든 KPI 를 볼 수 있다.
    if user.is_admin:
        return kpi

    # 조직원은 본인 KPI 만 볼 수 있다.
    if kpi.user_id != user.id:
        abort(404)

    return kpi


def build_dashboard_summary():
    """관리자 대시보드 상단의 요약 숫자들을 계산한다.

    돌려주는 값은 템플릿에서 바로 쓸 수 있는 딕셔너리다.
    """
    kpis = Kpi.query.all()
    users = User.query.filter_by(is_active_user=True).all()

    counts = status_breakdown(kpis)

    return {
        "total_kpi": len(kpis),
        "total_member": len(users),
        "total_department": Department.query.count(),
        "overall_progress": weighted_average_progress(kpis),
        "status_counts": counts,
        # 달성률 = 달성한 KPI 수 / 전체 KPI 수
        "achieved_rate": round(counts["achieved"] / len(kpis) * 100, 1) if kpis else 0.0,
        # 주의가 필요한 KPI = 지연 + 미달
        "attention_count": counts["delayed"] + counts["failed"],
    }


def build_department_stats():
    """부서별 KPI 현황을 계산한다.

    '부서 미지정' 조직원의 KPI 도 빠뜨리지 않도록 마지막에 따로 모아 붙인다.
    빠뜨리면 부서별 합계와 전체 합계가 맞지 않아 보는 사람이 혼란스러워진다.
    """
    stats = []

    for dept in Department.query.order_by(Department.name).all():
        # 이 부서 소속 조직원들의 KPI 를 모두 모은다.
        kpis = [kpi for member in dept.members for kpi in member.kpis]
        stats.append(
            {
                "name": dept.name,
                "member_count": len(dept.members),
                "kpi_count": len(kpis),
                "progress": weighted_average_progress(kpis),
                "status_counts": status_breakdown(kpis),
            }
        )

    # 부서가 지정되지 않은 조직원 처리.
    orphan_members = User.query.filter(User.department_id.is_(None)).all()
    if orphan_members:
        kpis = [kpi for member in orphan_members for kpi in member.kpis]
        stats.append(
            {
                "name": "미지정",
                "member_count": len(orphan_members),
                "kpi_count": len(kpis),
                "progress": weighted_average_progress(kpis),
                "status_counts": status_breakdown(kpis),
            }
        )

    return stats


def build_member_stats():
    """조직원별 KPI 현황을 계산한다. 진행률이 낮은 사람이 위로 오도록 정렬한다.

    낮은 순으로 정렬하는 이유는, 관리자가 대시보드에서 가장 먼저 봐야 할 대상이
    '잘하고 있는 사람' 이 아니라 '도움이 필요한 사람' 이기 때문이다.
    """
    members = []

    for user in User.query.filter_by(is_active_user=True).all():
        # KPI 가 하나도 없는 조직원은 진행률 0% 로 표시되어 오해를 부르므로 제외한다.
        if not user.kpis:
            continue
        members.append(
            {
                "id": user.id,
                "name": user.name,
                "employee_no": user.employee_no,
                "department": user.department_name,
                "position": user.position or "-",
                "kpi_count": len(user.kpis),
                "progress": user.average_progress,
                "status_counts": status_breakdown(user.kpis),
            }
        )

    members.sort(key=lambda m: m["progress"])
    return members


def build_chart_payload():
    """Chart.js 가 바로 쓸 수 있는 형태로 차트 데이터를 만든다.

    화면(자바스크립트)에서 계산하지 않고 서버에서 미리 만들어 내려보내는 이유는,
    집계 규칙(가중 평균 등)이 한 곳에만 있어야 화면과 통계가 어긋나지 않기 때문이다.
    """
    dept_stats = build_department_stats()
    member_stats = build_member_stats()
    summary = build_dashboard_summary()

    return {
        # 1) 부서별 평균 진행률 (막대그래프)
        "department": {
            "labels": [d["name"] for d in dept_stats],
            "values": [d["progress"] for d in dept_stats],
        },
        # 2) 상태 분포 (도넛그래프)
        "status": {
            "labels": [STATUS_LABELS[key] for key in STATUS_LABELS],
            "values": [summary["status_counts"][key] for key in STATUS_LABELS],
            "colors": [STATUS_CHART_COLORS[key] for key in STATUS_LABELS],
        },
        # 3) 조직원별 진행률 (막대그래프) - 하위 10명만 보여준다.
        #    전체를 다 그리면 조직이 커질수록 읽을 수 없는 그래프가 된다.
        "member": {
            "labels": [m["name"] for m in member_stats[:10]],
            "values": [m["progress"] for m in member_stats[:10]],
        },
        # 상단 요약 숫자. 자동 새로고침 때 함께 갱신한다.
        "summary": {
            "total_kpi": summary["total_kpi"],
            "overall_progress": summary["overall_progress"],
            "achieved_rate": summary["achieved_rate"],
            "attention_count": summary["attention_count"],
        },
    }
