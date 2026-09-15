"""애플리케이션 실행 진입점.

사용법
    python run.py

처음 실행하면 데이터베이스 파일(kpi.db)이 없으므로 테이블을 자동으로 만든다.
그리고 관리자 계정이 하나도 없으면 초기 관리자 계정을 만들어 준다.
계정이 없으면 아무도 로그인할 수 없어 시스템을 시작할 수조차 없기 때문이다.
"""
from app import create_app
from app.extensions import db

# 앱 객체를 모듈 수준에 두면 `flask --app run.py ...` 명령에서도 찾을 수 있다.
app = create_app()


def bootstrap():
    """테이블을 만들고, 관리자 계정이 없으면 기본 계정을 만든다."""
    from app.models import ROLE_ADMIN, User

    with app.app_context():
        db.create_all()

        # 관리자가 한 명이라도 있으면 아무것도 하지 않는다.
        if User.query.filter_by(role=ROLE_ADMIN).first():
            return

        admin = User(
            employee_no="ADMIN001",
            name="시스템 관리자",
            email="admin@etns.local",
            position="관리자",
            username="admin",
            role=ROLE_ADMIN,
            is_active_user=True,
        )
        admin.set_password("admin1234")

        db.session.add(admin)
        db.session.commit()

        print("=" * 58)
        print("  초기 관리자 계정을 생성했습니다.")
        print("    아이디  : admin")
        print("    비밀번호 : admin1234")
        print("  로그인 후 반드시 비밀번호를 변경하세요.")
        print("=" * 58)


if __name__ == "__main__":
    bootstrap()

    # host="0.0.0.0" 으로 두면 같은 사무실 네트워크의 태블릿에서도 접속할 수 있다.
    # 이 서버는 개발용이다. 실제 운영에서는 gunicorn 등 WSGI 서버를 써야 한다.
    app.run(host="0.0.0.0", port=5000, debug=True)
