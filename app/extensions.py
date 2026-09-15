"""확장(extension) 객체를 한 곳에 모아 두는 파일.

Flask 확장은 "객체를 먼저 만들고, 앱이 만들어질 때 연결한다(init_app)"는
2단계 방식을 쓴다. 이렇게 분리해 두면 모델 파일이 app/__init__.py 를
불러오지 않아도 되어 순환 참조(circular import)가 생기지 않는다.
"""
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

# 데이터베이스 ORM. 모델 클래스는 db.Model 을 상속해서 만든다.
db = SQLAlchemy()

# 로그인 세션 관리. 누가 로그인했는지 기억하고 @login_required 를 제공한다.
login_manager = LoginManager()

# 모든 POST 요청에 CSRF 토큰을 요구해, 다른 사이트가 사용자 몰래
# 우리 서버로 요청을 보내는 공격(CSRF)을 막는다.
csrf = CSRFProtect()

# 로그인하지 않은 사용자가 보호된 페이지에 들어오면 보낼 화면.
# "auth" 블루프린트의 "login" 함수라는 뜻이다.
login_manager.login_view = "auth.login"
login_manager.login_message = "로그인이 필요합니다."
login_manager.login_message_category = "warning"

# 세션을 얼마나 강하게 검증할지. "strong" 이면 접속 환경이 바뀌면 세션을 버린다.
login_manager.session_protection = "strong"
