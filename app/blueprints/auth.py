"""로그인 / 로그아웃 / 비밀번호 변경 담당 블루프린트."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..forms import LoginForm, PasswordChangeForm
from ..models import User

# 블루프린트는 '기능 단위로 묶은 라우트 모음' 이다.
# 파일이 커지는 것을 막고, 기능별로 코드를 찾기 쉽게 해 준다.
bp = Blueprint("auth", __name__)


def redirect_after_login(user):
    """로그인한 사용자의 권한에 맞는 첫 화면으로 보낸다.

    요청서 4-1 의 '권한에 따라 자동으로 화면을 분기한다' 부분이다.
    이 판단이 여러 곳에 흩어지면 나중에 화면 주소가 바뀔 때 빠뜨리기 쉬우므로
    함수 하나로 모아 두고 필요한 곳에서 불러 쓴다.
    """
    if user.is_admin:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("member.my_kpi"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    """로그인 화면과 로그인 처리."""
    # 이미 로그인한 사용자가 로그인 화면에 오면 각자의 첫 화면으로 돌려보낸다.
    if current_user.is_authenticated:
        return redirect_after_login(current_user)

    form = LoginForm()

    # validate_on_submit() 은 'POST 요청이고 + 검증을 모두 통과했을 때' 만 참이다.
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()

        # 아이디가 없는 경우와 비밀번호가 틀린 경우를 하나의 문구로 처리한다.
        # 문구를 나누면 "그 아이디는 존재한다" 는 정보가 새어나가, 공격자가
        # 유효한 아이디 목록을 만들 수 있게 된다.
        if user is None or not user.check_password(form.password.data):
            flash("아이디 또는 비밀번호가 올바르지 않습니다.", "danger")
            return render_template("auth/login.html", form=form)

        # 비활성 처리된 계정은 로그인시키지 않는다.
        # 이때는 원인을 알려주는 편이 낫다. 본인은 비밀번호를 맞게 입력했는데
        # 계속 실패하면 어디에 문의해야 할지 모르기 때문이다.
        if not user.is_active_user:
            flash("비활성 처리된 계정입니다. 관리자에게 문의하세요.", "warning")
            return render_template("auth/login.html", form=form)

        # 여기까지 왔으면 인증 성공. 세션에 로그인 정보를 기록한다.
        login_user(user, remember=form.remember.data)
        flash(f"{user.name}님, 환영합니다.", "success")

        # 로그인하지 않은 상태로 특정 페이지에 접근했다가 여기로 온 경우,
        # 원래 가려던 곳으로 되돌려 보낸다.
        next_page = request.args.get("next")

        # next 값은 사용자가 주소창에서 마음대로 바꿀 수 있는 값이다.
        # "/" 로 시작하는 우리 사이트 내부 주소만 허용해서, 외부 사이트로
        # 튕겨 보내는 공격(오픈 리다이렉트)을 막는다.
        # "//evil.com" 도 브라우저는 외부 주소로 해석하므로 함께 걸러낸다.
        if next_page and next_page.startswith("/") and not next_page.startswith("//"):
            return redirect(next_page)

        return redirect_after_login(user)

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    """로그아웃 처리."""
    logout_user()
    flash("로그아웃되었습니다.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    """본인 비밀번호 변경. 관리자와 조직원 모두 사용한다."""
    form = PasswordChangeForm()

    if form.validate_on_submit():
        # 현재 비밀번호를 다시 확인한다. 자리를 비운 사이 남이 비밀번호를
        # 바꿔버리는 것을 막기 위한 절차다.
        if not current_user.check_password(form.current_password.data):
            flash("현재 비밀번호가 올바르지 않습니다.", "danger")
            return render_template("auth/change_password.html", form=form)

        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash("비밀번호가 변경되었습니다.", "success")
        return redirect_after_login(current_user)

    return render_template("auth/change_password.html", form=form)
