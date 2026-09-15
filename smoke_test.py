"""기능 점검 스크립트.

요청서의 주요 요구사항이 실제로 지켜지는지 확인한다.
특히 3-2 의 "조직원은 다른 조직원의 KPI를 조회하거나 수정할 수 없어야 한다"를
여러 각도에서 확인한다.

사용법
    python smoke_test.py
"""
import sys

from app import create_app
from app.extensions import db
from app.models import Department, Kpi, KpiUpdate, User

PASS, FAIL = [], []


def check(label, condition, detail=""):
    """조건이 참이면 통과, 아니면 실패로 기록한다."""
    if condition:
        PASS.append(label)
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} {detail}")
        print(f"  [FAIL] {label} {detail}")


def login(client, username, password):
    """테스트 클라이언트로 로그인한다."""
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def main():
    app = create_app()
    # 테스트에서는 CSRF 토큰을 꺼야 폼을 직접 POST 할 수 있다.
    # 실제 서비스에서는 절대 끄면 안 된다.
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        member_a = User.query.filter_by(username="seojun").first()
        member_b = User.query.filter_by(username="dohyun").first()

        if not (admin and member_a and member_b):
            print("샘플 데이터가 없습니다. 먼저 `python seed.py` 를 실행하세요.")
            sys.exit(1)

        a_kpi_id = member_a.kpis[0].id
        b_kpi_id = member_b.kpis[0].id
        b_kpi_before = member_b.kpis[0].current_value
        member_b_id = member_b.id
        dept_count = Department.query.count()

    # ================================================================
    print("\n[1] 로그인 / 권한별 화면 분기")
    # ================================================================
    with app.test_client() as c:
        r = c.get("/", follow_redirects=False)
        check("비로그인 시 로그인 화면으로 이동", r.status_code == 302 and "/login" in r.headers["Location"])

        r = login(c, "admin", "wrong-password")
        check("잘못된 비밀번호는 로그인 실패", r.status_code == 200)

        r = login(c, "admin", "admin1234")
        check("관리자 로그인 시 관리자 대시보드로 이동",
              r.status_code == 302 and "/admin/dashboard" in r.headers["Location"],
              r.headers.get("Location", ""))

    with app.test_client() as c:
        r = login(c, "seojun", "test1234")
        check("조직원 로그인 시 내 KPI 화면으로 이동",
              r.status_code == 302 and "/my/kpi" in r.headers["Location"],
              r.headers.get("Location", ""))

    # ================================================================
    print("\n[2] 관리자 화면 접근")
    # ================================================================
    with app.test_client() as c:
        login(c, "admin", "admin1234")
        for path, label in [
            ("/admin/dashboard", "대시보드"),
            ("/admin/users", "조직원 목록"),
            ("/admin/users/new", "조직원 등록 폼"),
            ("/admin/departments", "부서 관리"),
            ("/admin/kpis", "KPI 목록"),
            ("/admin/kpis/new", "KPI 등록 폼"),
            ("/admin/departments/stats", "부서별 현황"),
            ("/admin/members/stats", "조직원별 현황"),
        ]:
            r = c.get(path)
            check(f"관리자 {label} 열림", r.status_code == 200, f"(status {r.status_code})")

        r = c.get("/admin/api/chart-data")
        data = r.get_json()
        check("차트 데이터 API 응답", r.status_code == 200 and "summary" in data)
        check("차트에 부서 데이터 포함", len(data["department"]["labels"]) >= dept_count)
        check("차트에 상태 4종 포함", len(data["status"]["values"]) == 4)

    # ================================================================
    print("\n[3] 조직원의 관리자 화면 접근 차단")
    # ================================================================
    with app.test_client() as c:
        login(c, "seojun", "test1234")
        for path in ["/admin/dashboard", "/admin/users", "/admin/kpis",
                     "/admin/departments", "/admin/api/chart-data"]:
            r = c.get(path)
            check(f"조직원 {path} 차단(403)", r.status_code == 403, f"(status {r.status_code})")

        r = c.post("/admin/users/1/delete")
        check("조직원의 계정 삭제 시도 차단", r.status_code == 403, f"(status {r.status_code})")

    # ================================================================
    print("\n[4] 조직원 간 KPI 격리 (요청서 3-2 핵심)")
    # ================================================================
    with app.test_client() as c:
        login(c, "seojun", "test1234")

        r = c.get(f"/my/kpi/{a_kpi_id}")
        check("본인 KPI 상세 열림", r.status_code == 200, f"(status {r.status_code})")

        r = c.get(f"/my/kpi/{b_kpi_id}")
        check("남의 KPI 조회 차단(404)", r.status_code == 404, f"(status {r.status_code})")

        r = c.post(f"/my/kpi/{b_kpi_id}/progress",
                   data={"current_value": "99999", "note": "침입 시도"})
        check("남의 KPI 실적 입력 차단(404)", r.status_code == 404, f"(status {r.status_code})")

    with app.app_context():
        after = db.session.get(Kpi, b_kpi_id).current_value
        check("차단된 시도로 남의 KPI 값이 바뀌지 않음", after == b_kpi_before,
              f"({b_kpi_before} -> {after})")

    # ================================================================
    print("\n[5] 조직원 본인 기능")
    # ================================================================
    with app.test_client() as c:
        login(c, "seojun", "test1234")

        for path, label in [("/my/kpi", "내 KPI 목록"), ("/my/history", "입력 이력"),
                            ("/my/profile", "내 정보")]:
            r = c.get(path)
            check(f"{label} 열림", r.status_code == 200, f"(status {r.status_code})")

        with app.app_context():
            before = db.session.get(Kpi, a_kpi_id).current_value
            hist_before = KpiUpdate.query.filter_by(kpi_id=a_kpi_id).count()

        new_value = before + 3
        c.post(f"/my/kpi/{a_kpi_id}/progress",
               data={"current_value": str(new_value), "note": "테스트 입력"},
               follow_redirects=True)

        with app.app_context():
            kpi = db.session.get(Kpi, a_kpi_id)
            hist_after = KpiUpdate.query.filter_by(kpi_id=a_kpi_id).count()
            check("본인 KPI 실적 입력 반영", kpi.current_value == new_value,
                  f"({before} -> {kpi.current_value})")
            check("실적 입력 시 이력 1건 추가", hist_after == hist_before + 1,
                  f"({hist_before} -> {hist_after})")

            expected = round(new_value / kpi.target_value * 100, 1)
            check("진행률 = 현재값/목표값×100 계산 일치", kpi.progress == expected,
                  f"({kpi.progress} vs {expected})")

        # 같은 값을 다시 넣으면 이력이 늘지 않아야 한다.
        c.post(f"/my/kpi/{a_kpi_id}/progress",
               data={"current_value": str(new_value), "note": "중복"},
               follow_redirects=True)
        with app.app_context():
            check("같은 값 재입력 시 이력 증가 없음",
                  KpiUpdate.query.filter_by(kpi_id=a_kpi_id).count() == hist_after)

    # ================================================================
    print("\n[6] 관리자 CRUD")
    # ================================================================
    with app.test_client() as c:
        login(c, "admin", "admin1234")

        # --- 부서 등록 ---
        c.post("/admin/departments", data={"name": "품질보증본부", "description": "QA"},
               follow_redirects=True)
        with app.app_context():
            dept = Department.query.filter_by(name="품질보증본부").first()
            check("부서 등록", dept is not None)
            new_dept_id = dept.id if dept else 0

        # --- 조직원 등록 ---
        c.post("/admin/users/new", data={
            "employee_no": "2024099", "name": "테스트직원",
            "email": "tester@etns.local", "department_id": str(new_dept_id),
            "position": "사원", "username": "tester",
            "password": "test1234", "password_confirm": "test1234",
            "role": "member", "is_active_user": "y",
        }, follow_redirects=True)
        with app.app_context():
            tester = User.query.filter_by(username="tester").first()
            check("조직원 등록", tester is not None)
            tester_id = tester.id if tester else 0

        # --- 중복 아이디 거부 ---
        c.post("/admin/users/new", data={
            "employee_no": "2024100", "name": "중복테스트",
            "email": "dup@etns.local", "department_id": "0", "position": "사원",
            "username": "tester",  # 이미 있는 아이디
            "password": "test1234", "password_confirm": "test1234",
            "role": "member", "is_active_user": "y",
        }, follow_redirects=True)
        with app.app_context():
            check("중복 아이디 등록 거부",
                  User.query.filter_by(username="tester").count() == 1)

        # --- KPI 등록 ---
        c.post("/admin/kpis/new", data={
            "user_id": str(tester_id), "title": "테스트 KPI",
            "description": "점검용", "target_value": "100", "current_value": "40",
            "unit": "건", "start_date": "2026-01-01", "end_date": "2026-12-31",
            "weight": "2.0",
        }, follow_redirects=True)
        with app.app_context():
            kpi = Kpi.query.filter_by(title="테스트 KPI").first()
            check("KPI 등록", kpi is not None)
            check("등록 직후 진행률 40%", kpi is not None and kpi.progress == 40.0,
                  f"({kpi.progress if kpi else '-'})")
            test_kpi_id = kpi.id if kpi else 0

        # --- 종료일이 시작일보다 앞선 KPI 거부 ---
        c.post("/admin/kpis/new", data={
            "user_id": str(tester_id), "title": "잘못된 기간 KPI",
            "description": "", "target_value": "10", "current_value": "0",
            "unit": "건", "start_date": "2026-12-31", "end_date": "2026-01-01",
            "weight": "1.0",
        }, follow_redirects=True)
        with app.app_context():
            check("종료일 < 시작일 KPI 거부",
                  Kpi.query.filter_by(title="잘못된 기간 KPI").first() is None)

        # --- 목표값 0 거부 ---
        c.post("/admin/kpis/new", data={
            "user_id": str(tester_id), "title": "목표0 KPI",
            "description": "", "target_value": "0", "current_value": "0",
            "unit": "건", "start_date": "2026-01-01", "end_date": "2026-12-31",
            "weight": "1.0",
        }, follow_redirects=True)
        with app.app_context():
            check("목표값 0 KPI 거부",
                  Kpi.query.filter_by(title="목표0 KPI").first() is None)

        # --- 관리자 대리 실적 입력 ---
        c.post(f"/admin/kpis/{test_kpi_id}/progress",
               data={"current_value": "75", "note": "관리자 대리 입력"},
               follow_redirects=True)
        with app.app_context():
            kpi = db.session.get(Kpi, test_kpi_id)
            check("관리자 대리 실적 입력", kpi.current_value == 75.0, f"({kpi.current_value})")
            check("대리 입력도 이력에 기록",
                  KpiUpdate.query.filter_by(kpi_id=test_kpi_id).count() >= 1)

        # --- 소속 조직원이 있는 부서 삭제 방지 ---
        c.post(f"/admin/departments/{new_dept_id}/delete", follow_redirects=True)
        with app.app_context():
            check("소속 인원이 있는 부서는 삭제되지 않음",
                  db.session.get(Department, new_dept_id) is not None)

        # --- 마지막 관리자 삭제 방지 ---
        with app.app_context():
            admin_id = User.query.filter_by(username="admin").first().id
        c.post(f"/admin/users/{admin_id}/delete", follow_redirects=True)
        with app.app_context():
            check("마지막 관리자 삭제 방지",
                  db.session.get(User, admin_id) is not None)

        # --- 조직원 삭제 시 KPI/이력 연쇄 삭제 ---
        c.post(f"/admin/users/{tester_id}/delete", follow_redirects=True)
        with app.app_context():
            check("조직원 삭제", db.session.get(User, tester_id) is None)
            check("삭제 시 KPI 연쇄 삭제", db.session.get(Kpi, test_kpi_id) is None)
            check("삭제 시 입력 이력 연쇄 삭제",
                  KpiUpdate.query.filter_by(kpi_id=test_kpi_id).count() == 0)

        # --- 뒷정리: 테스트용 부서 삭제 ---
        c.post(f"/admin/departments/{new_dept_id}/delete", follow_redirects=True)
        with app.app_context():
            check("인원이 빠진 부서는 삭제 가능",
                  db.session.get(Department, new_dept_id) is None)

    # ================================================================
    print("\n[7] 상태 자동 판정")
    # ================================================================
    with app.app_context():
        from datetime import date, timedelta

        today = date.today()

        cases = [
            ("달성", 100, 100, today - timedelta(days=10), today + timedelta(days=10), "achieved"),
            ("미달", 50, 100, today - timedelta(days=60), today - timedelta(days=1), "failed"),
            ("진행중", 50, 100, today - timedelta(days=50), today + timedelta(days=50), "on_track"),
            ("지연", 5, 100, today - timedelta(days=80), today + timedelta(days=20), "delayed"),
            ("초과달성", 150, 100, today - timedelta(days=10), today + timedelta(days=10), "achieved"),
        ]

        owner = User.query.filter_by(username="seojun").first()
        for label, current, target, start, end, expected in cases:
            kpi = Kpi(user_id=owner.id, title=f"판정테스트-{label}", target_value=target,
                      current_value=current, unit="건", start_date=start, end_date=end, weight=1.0)
            check(f"상태 판정: {label}", kpi.status == expected,
                  f"(진행률 {kpi.progress}%, 기대진행률 {kpi.expected_progress:.0f}% -> {kpi.status})")

    # ================================================================
    print("\n[8] 로그아웃 / 비활성 계정")
    # ================================================================
    with app.test_client() as c:
        login(c, "seojun", "test1234")
        c.get("/logout")
        r = c.get("/my/kpi", follow_redirects=False)
        check("로그아웃 후 접근 차단", r.status_code == 302 and "/login" in r.headers["Location"])

    with app.app_context():
        user = User.query.filter_by(username="doyoon").first()
        user.is_active_user = False
        db.session.commit()

    with app.test_client() as c:
        r = login(c, "doyoon", "test1234")
        check("비활성 계정 로그인 차단", r.status_code == 200)
        r = c.get("/my/kpi", follow_redirects=False)
        check("비활성 계정은 세션이 생기지 않음", r.status_code == 302)

    with app.app_context():
        user = User.query.filter_by(username="doyoon").first()
        user.is_active_user = True
        db.session.commit()

    # ================================================================
    print("\n" + "=" * 58)
    print(f"  통과 {len(PASS)}건 / 실패 {len(FAIL)}건")
    if FAIL:
        print("\n  실패 항목:")
        for item in FAIL:
            print(f"    - {item}")
    print("=" * 58)

    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
