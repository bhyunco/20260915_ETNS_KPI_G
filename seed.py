"""샘플 데이터 생성 스크립트.

빈 화면으로는 대시보드가 제대로 동작하는지 확인할 수 없다.
부서 4개, 조직원 10명, KPI 20여 개와 실적 입력 이력을 만들어
차트와 상태 판정(달성/진행중/지연/미달)이 모두 나오도록 구성한다.

사용법
    python seed.py

주의: 이미 들어 있는 데이터를 모두 지우고 다시 만든다.
"""
import random
from datetime import date, datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import Department, Kpi, KpiUpdate, User

# 매번 같은 샘플이 나오도록 난수 씨앗을 고정한다.
# 실행할 때마다 숫자가 바뀌면 "아까 본 화면" 과 달라져 확인하기 불편하다.
random.seed(20260915)


DEPARTMENTS = [
    ("영업본부", "국내외 영업 및 고객 관리"),
    ("개발본부", "제품 개발 및 기술 지원"),
    ("경영지원본부", "인사, 재무, 총무"),
    ("마케팅본부", "브랜드 및 디지털 마케팅"),
]

# (사번, 이름, 부서 인덱스, 직급, 아이디)
MEMBERS = [
    ("2024001", "김서준", 0, "부장", "seojun"),
    ("2024002", "이하윤", 0, "대리", "hayoon"),
    ("2024003", "박도현", 1, "차장", "dohyun"),
    ("2024004", "최시우", 1, "사원", "siwoo"),
    ("2024005", "정예린", 1, "대리", "yerin"),
    ("2024006", "강민재", 2, "과장", "minjae"),
    ("2024007", "조수아", 2, "사원", "sua"),
    ("2024008", "윤지호", 3, "팀장", "jiho"),
    ("2024009", "임채원", 3, "대리", "chaewon"),
    ("2024010", "한도윤", 3, "사원", "doyoon"),
]

# (KPI명, 설명, 목표값, 단위, 가중치)
KPI_POOL = [
    ("신규 고객 유치", "올해 신규 계약을 체결한 고객사 수", 24, "건", 3.0),
    ("매출 목표 달성", "담당 영역 연간 매출", 1200000000, "원", 3.0),
    ("고객 만족도", "분기별 고객 설문 평균 점수", 90, "점", 2.0),
    ("기능 배포 건수", "운영 환경에 배포 완료한 기능", 36, "건", 2.5),
    ("장애 대응 시간 단축", "장애 평균 대응 시간", 30, "시간", 2.0),
    ("코드 리뷰 참여", "동료 코드 리뷰 참여 횟수", 120, "건", 1.5),
    ("단위 테스트 커버리지", "담당 모듈 테스트 커버리지", 80, "%", 2.0),
    ("채용 목표 달성", "연간 신규 입사자", 12, "명", 2.5),
    ("교육 이수 시간", "직무 교육 이수 시간", 40, "시간", 1.0),
    ("비용 절감", "운영비 절감액", 50000000, "원", 2.0),
    ("콘텐츠 발행", "블로그 및 SNS 콘텐츠 발행", 60, "건", 2.0),
    ("리드 확보", "마케팅 경로 유입 잠재고객", 500, "명", 2.5),
    ("브랜드 인지도", "브랜드 인지도 조사 점수", 75, "점", 1.5),
    ("프로세스 개선 과제", "업무 개선 과제 완료", 8, "건", 1.5),
]


def run_seed():
    """샘플 데이터를 만든다. 기존 데이터는 모두 지운다."""
    app = create_app()

    with app.app_context():
        db.create_all()

        print("기존 데이터를 정리합니다...")
        # 자식 테이블부터 지워야 외래키 제약에 걸리지 않는다.
        KpiUpdate.query.delete()
        Kpi.query.delete()
        User.query.delete()
        Department.query.delete()
        db.session.commit()

        # ----- 부서 -----
        departments = []
        for name, desc in DEPARTMENTS:
            dept = Department(name=name, description=desc)
            db.session.add(dept)
            departments.append(dept)
        db.session.commit()
        print(f"부서 {len(departments)}개 생성")

        # ----- 관리자 -----
        admin = User(
            employee_no="ADMIN001",
            name="시스템 관리자",
            email="admin@etns.local",
            position="관리자",
            username="admin",
            role="admin",
            is_active_user=True,
            department_id=departments[2].id,  # 경영지원본부 소속
        )
        admin.set_password("admin1234")
        db.session.add(admin)

        # ----- 조직원 -----
        users = []
        for emp_no, name, dept_idx, position, username in MEMBERS:
            user = User(
                employee_no=emp_no,
                name=name,
                email=f"{username}@etns.local",
                position=position,
                username=username,
                role="member",
                is_active_user=True,
                department_id=departments[dept_idx].id,
            )
            user.set_password("test1234")
            db.session.add(user)
            users.append(user)

        db.session.commit()
        print(f"조직원 {len(users)}명 + 관리자 1명 생성")

        # ----- KPI -----
        today = date.today()
        kpi_count = 0

        for user in users:
            # 한 사람당 2~3개의 KPI 를 배정한다.
            for title, desc, target, unit, weight in random.sample(KPI_POOL, random.randint(2, 3)):
                # 기간을 다양하게 만들어 '지연' 과 '미달' 상태가 모두 나오게 한다.
                #   - 일부는 이미 끝난 KPI (종료일이 과거 -> 미달 판정 대상)
                #   - 나머지는 진행 중
                if random.random() < 0.2:
                    start = today - timedelta(days=random.randint(200, 300))
                    end = today - timedelta(days=random.randint(5, 40))
                else:
                    start = today - timedelta(days=random.randint(30, 180))
                    end = today + timedelta(days=random.randint(20, 200))

                # 달성률을 넓게 퍼뜨려 4가지 상태가 골고루 나오도록 한다.
                ratio = random.choice([0.15, 0.3, 0.45, 0.6, 0.75, 0.85, 0.95, 1.0, 1.15])
                current = round(target * ratio, 2)

                kpi = Kpi(
                    user_id=user.id,
                    title=title,
                    description=desc,
                    target_value=float(target),
                    current_value=0.0,  # 이력을 만들며 올릴 것이므로 0 에서 시작
                    unit=unit,
                    start_date=start,
                    end_date=end,
                    weight=weight,
                )
                db.session.add(kpi)
                db.session.flush()  # kpi.id 를 얻기 위해 먼저 반영

                # ----- 실적 입력 이력 -----
                # 0 에서 목표치까지 2~4번에 걸쳐 나눠 올린 것처럼 만든다.
                steps = random.randint(2, 4)
                previous = 0.0
                for step in range(1, steps + 1):
                    new_value = round(current * step / steps, 2)
                    days_ago = (steps - step) * random.randint(7, 20)

                    db.session.add(
                        KpiUpdate(
                            kpi_id=kpi.id,
                            previous_value=previous,
                            new_value=new_value,
                            note=f"{step}차 실적 반영",
                            updated_by_id=user.id,
                            created_at=datetime.now() - timedelta(days=days_ago),
                        )
                    )
                    previous = new_value

                kpi.current_value = current
                kpi.updated_at = datetime.now() - timedelta(days=random.randint(0, 10))
                kpi_count += 1

        db.session.commit()
        print(f"KPI {kpi_count}건 + 입력 이력 생성")

        print()
        print("=" * 58)
        print("  샘플 데이터 생성 완료")
        print()
        print("  관리자   아이디: admin      비밀번호: admin1234")
        print("  조직원   아이디: seojun     비밀번호: test1234")
        print("           (그 외 hayoon, dohyun, siwoo, yerin,")
        print("            minjae, sua, jiho, chaewon, doyoon)")
        print("=" * 58)


if __name__ == "__main__":
    run_seed()
