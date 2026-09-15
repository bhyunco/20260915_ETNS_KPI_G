"""애플리케이션 설정 값 모음.

설정을 클래스로 분리해 두면 개발용/운영용 설정을 바꿔 끼우기 쉽다.
지금은 SQLite 를 쓰지만, DATABASE_URL 환경변수만 바꾸면 PostgreSQL 이나
MySQL 로 그대로 옮겨갈 수 있도록 데이터베이스 주소를 밖에서 주입받는다.
"""
import os
from datetime import timedelta

# 이 파일이 있는 폴더(= 프로젝트 최상위)의 절대경로.
# 상대경로를 쓰면 실행 위치에 따라 DB 파일이 엉뚱한 곳에 생기므로 절대경로를 쓴다.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _normalize_db_url(url):
    """DATABASE_URL 을 SQLAlchemy 가 이해하는 형태로 다듬는다.

    Supabase 를 비롯한 많은 서비스가 접속 주소를 `postgresql://...` 또는
    `postgres://...` 로 알려준다. 그대로 쓰면 SQLAlchemy 가 psycopg2(2.x)를
    찾다가 실패한다. 우리는 psycopg 3 을 쓰므로 드라이버 이름을 붙여 준다.

    주소를 손으로 고쳐 넣게 하지 않고 코드에서 처리하는 이유는, 나중에
    비밀번호를 바꿔 주소를 다시 붙여넣을 때 드라이버 이름을 빠뜨리기 쉽기 때문이다.
    """
    if not url:
        return None

    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _engine_options(url):
    """데이터베이스 종류에 맞는 SQLAlchemy 엔진 옵션을 만든다."""
    # SQLite(로컬 개발)는 특별한 설정이 필요 없다.
    if not url or url.startswith("sqlite"):
        return {"pool_pre_ping": True}

    from sqlalchemy.pool import NullPool

    return {
        # 서버리스 환경에서는 함수 인스턴스가 수시로 생겼다 사라진다.
        # 커넥션 풀을 들고 있어 봐야 다음 요청에서 쓰이지 않고, 오히려
        # 데이터베이스의 연결 수만 잡아먹는다. 그래서 풀을 쓰지 않는다.
        # (연결 재사용은 Supabase 쪽 풀러가 대신해 준다)
        "poolclass": NullPool,
        "pool_pre_ping": True,
        "connect_args": {
            # Supabase 풀러(Supavisor)는 transaction 모드로 동작해서
            # 세션에 걸친 prepared statement 를 재사용할 수 없다.
            # psycopg 의 자동 prepare 를 꺼야 간헐적인 오류가 나지 않는다.
            "prepare_threshold": None,
        },
    }


class Config:
    """모든 환경에서 공통으로 쓰는 기본 설정."""

    # 세션 쿠키와 CSRF 토큰에 서명할 때 쓰는 비밀 키.
    # 운영에서는 반드시 환경변수로 주입해야 한다. 키가 바뀌면 로그인 세션이 모두 풀린다.
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-secret-key-change-me"

    # SQLAlchemy 가 접속할 데이터베이스 주소.
    # 환경변수가 없으면 프로젝트 폴더 안의 kpi.db(SQLite 파일)를 사용한다.
    # PostgreSQL 로 옮길 때는 DATABASE_URL 에
    #   postgresql+psycopg://사용자:비밀번호@호스트:5432/DB이름
    # 형태의 값을 넣어주기만 하면 된다. 코드는 고칠 필요가 없다.
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.environ.get("DATABASE_URL")) or (
        "sqlite:///" + os.path.join(BASE_DIR, "kpi.db")
    )

    # 변경 추적 기능은 메모리만 더 쓰고 쓸 일이 없어 끈다.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 접속 대상에 맞는 엔진 옵션. 아래 _engine_options() 참고.
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)

    # 로그인 상태(세션 쿠키)를 유지하는 기간.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    # 자바스크립트에서 쿠키를 읽지 못하게 막는다(XSS 로 세션이 탈취되는 것을 줄여 준다).
    SESSION_COOKIE_HTTPONLY = True

    # 다른 사이트에서 폼을 보내는 것을 제한한다.
    SESSION_COOKIE_SAMESITE = "Lax"

    # CSRF 토큰 유효시간(초). None 이면 세션이 살아 있는 동안 계속 유효하다.
    # 대시보드를 오래 열어두고 폼을 제출하는 경우가 많아 만료를 두지 않는다.
    WTF_CSRF_TIME_LIMIT = None


class DevelopmentConfig(Config):
    """로컬 개발용 설정."""

    DEBUG = True


class ProductionConfig(Config):
    """운영 배포용 설정."""

    DEBUG = False

    # HTTPS 로만 쿠키를 전송한다.
    SESSION_COOKIE_SECURE = True


# 설정 이름 -> 설정 클래스 맵. create_app() 에서 이 이름으로 골라 쓴다.
config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
