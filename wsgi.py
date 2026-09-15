"""배포용 진입점 (Vercel 서버리스 / gunicorn 공용).

`run.py` 는 로컬 개발용이라 개발 서버를 직접 띄우고 초기 계정까지 만들지만,
배포 환경에서는 WSGI 앱 객체 하나만 있으면 된다. 그래서 파일을 나눠 두었다.

Vercel 은 이 파일의 `app` 변수를 찾아 요청을 넘겨준다.
gunicorn 으로 띄울 때는 다음과 같이 쓴다.

    gunicorn wsgi:app
"""
import os

from app import create_app

# 배포 환경에서는 운영용 설정(쿠키 Secure, 디버그 끄기)을 쓴다.
# Vercel 은 VERCEL 환경변수를 자동으로 넣어 주므로 그것으로 판별한다.
config_name = "production" if os.environ.get("VERCEL") else "default"

app = create_app(config_name)
