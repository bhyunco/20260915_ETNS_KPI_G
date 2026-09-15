"""애플리케이션 팩토리.

Flask 앱을 모듈 최상단에서 만들지 않고 create_app() 함수 안에서 만드는 방식을
'애플리케이션 팩토리 패턴' 이라고 한다. 이렇게 하면

    - 설정을 바꿔가며 앱을 여러 개 만들 수 있다 (개발용/테스트용)
    - 테스트에서 앱을 매번 새로 만들어 서로 간섭하지 않게 할 수 있다
    - 순환 참조가 잘 생기지 않는다

는 장점이 있다. 규모가 커질수록 차이가 커진다.
"""
import os

from flask import Flask, redirect, render_template, url_for
from flask_login import current_user

from config import config_by_name

from .extensions import csrf, db, login_manager


def create_app(config_name=None):
    """Flask 앱을 만들어 돌려준다.

    config_name : "development" 또는 "production".
                  주지 않으면 FLASK_CONFIG 환경변수를 보고, 그것도 없으면 개발용.
    """
    app = Flask(__name__)

    # ----- 1. 설정 적용 --------------------------------------------------
    config_name = config_name or os.environ.get("FLASK_CONFIG", "default")
    app.config.from_object(config_by_name[config_name])

    # ----- 2. 확장 연결 --------------------------------------------------
    # extensions.py 에서 만들어 둔 객체들을 이 앱에 붙인다.
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # ----- 3. 블루프린트 등록 --------------------------------------------
    # import 를 함수 안에서 하는 이유: 블루프린트가 models 를 불러오고
    # models 가 extensions 를 불러오는데, 파일 맨 위에서 import 하면
    # 순서가 꼬여 순환 참조가 날 수 있다.
    from .blueprints.admin import bp as admin_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.member import bp as member_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(member_bp)

    # ----- 4. 기본 주소 처리 ---------------------------------------------
    @app.route("/")
    def home():
        """사이트 첫 주소. 로그인 여부와 권한에 따라 알맞은 화면으로 보낸다."""
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("member.my_kpi"))

    # ----- 5. 오류 화면 --------------------------------------------------
    # 기본 오류 화면은 흰 바탕에 영문 메시지만 나와 사용자가 당황한다.
    # 우리 레이아웃을 입힌 한국어 안내 화면으로 바꾼다.

    @app.errorhandler(403)
    def forbidden(error):
        return render_template(
            "error.html",
            code=403,
            title="접근 권한이 없습니다",
            message="이 화면은 관리자만 볼 수 있습니다.",
        ), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template(
            "error.html",
            code=404,
            title="페이지를 찾을 수 없습니다",
            message="주소가 잘못되었거나 접근할 수 없는 자료입니다.",
        ), 404

    @app.errorhandler(500)
    def server_error(error):
        # 오류가 난 채로 트랜잭션이 남아 있으면 이후 요청까지 줄줄이 실패한다.
        # 되돌려 놓고 나가야 다음 요청이 정상 동작한다.
        db.session.rollback()
        return render_template(
            "error.html",
            code=500,
            title="서버 오류가 발생했습니다",
            message="잠시 후 다시 시도해 주세요.",
        ), 500

    # ----- 6. 템플릿 공통 값 ---------------------------------------------
    @app.context_processor
    def inject_common():
        """모든 템플릿에서 별도 전달 없이 쓸 수 있는 값들.

        화면마다 넘겨주는 것을 빠뜨리면 그 화면만 깨지므로, 어디서나 쓰는 값은
        여기에 모아 둔다.
        """
        from datetime import date

        from .models import STATUS_COLORS, STATUS_LABELS

        return {
            "STATUS_LABELS": STATUS_LABELS,
            "STATUS_COLORS": STATUS_COLORS,
            "today": date.today(),
            "app_name": "ETNS KPI 관리 시스템",
        }

    # ----- 7. CLI 명령 ---------------------------------------------------
    register_commands(app)

    return app


def register_commands(app):
    """터미널에서 쓸 수 있는 명령을 등록한다.

    사용 예:
        flask --app run.py init-db     (테이블 생성)
        flask --app run.py seed        (샘플 데이터 넣기)
    """

    @app.cli.command("init-db")
    def init_db_command():
        """데이터베이스 테이블을 만든다."""
        db.create_all()
        print("데이터베이스 테이블을 생성했습니다.")

    @app.cli.command("seed")
    def seed_command():
        """초기 관리자 계정과 샘플 데이터를 넣는다."""
        from seed import run_seed

        run_seed()
