"""입력 폼 정의 (Flask-WTF).

폼을 클래스로 만들어 두면 세 가지를 한 번에 얻는다.

1. CSRF 토큰이 자동으로 들어간다 (다른 사이트가 몰래 요청을 보내는 것을 막는다)
2. 검증 규칙을 한 곳에 모아 둘 수 있다 (필수값, 길이, 범위 등)
3. 템플릿에서 입력칸과 오류 메시지를 짧게 그릴 수 있다

중요: 검증은 반드시 서버에서 해야 한다. 브라우저의 required 속성만으로는
개발자 도구로 얼마든지 우회할 수 있다.
"""
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    DecimalField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    EqualTo,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

from .models import ROLE_ADMIN, ROLE_MEMBER, UNIT_CHOICES

# 이메일 형식 검사에 쓰는 정규식.
#
# WTForms 의 Email 검증기(email-validator 패키지)를 쓰지 않는 이유가 있다.
# 그 패키지는 .local, .internal 같은 '특수 용도 도메인' 을 거부하는데,
# 사내 전용 시스템에서는 admin@etns.local 처럼 내부 도메인을 쓰는 일이 흔하다.
# 여기서 필요한 것은 오타를 걸러내는 수준의 형식 검사이므로 정규식으로 충분하다.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginForm(FlaskForm):
    """로그인 폼. 요청서대로 아이디와 비밀번호만 받는다."""

    username = StringField("아이디", validators=[DataRequired(message="아이디를 입력하세요.")])
    password = PasswordField("비밀번호", validators=[DataRequired(message="비밀번호를 입력하세요.")])
    remember = BooleanField("로그인 상태 유지")
    submit = SubmitField("로그인")


class DepartmentForm(FlaskForm):
    """부서 등록/수정 폼."""

    name = StringField(
        "부서명",
        validators=[DataRequired(message="부서명을 입력하세요."), Length(max=80)],
    )
    description = StringField("설명", validators=[Optional(), Length(max=200)])
    submit = SubmitField("저장")


class UserForm(FlaskForm):
    """조직원 등록/수정 공용 폼.

    등록과 수정은 입력 항목이 거의 같고, 비밀번호 처리만 다르다.
    - 등록: 초기 비밀번호가 반드시 필요하다
    - 수정: 비워두면 기존 비밀번호를 그대로 둔다

    그래서 폼 하나로 두고, is_edit 플래그로 비밀번호 필수 여부만 바꾼다.
    """

    employee_no = StringField(
        "사번", validators=[DataRequired(message="사번을 입력하세요."), Length(max=30)]
    )
    name = StringField(
        "이름", validators=[DataRequired(message="이름을 입력하세요."), Length(max=50)]
    )
    email = StringField(
        "이메일",
        validators=[
            DataRequired(message="이메일을 입력하세요."),
            Regexp(EMAIL_PATTERN, message="이메일 형식이 올바르지 않습니다."),
            Length(max=120),
        ],
    )
    # 부서 선택지는 DB 에서 읽어와야 하므로 __init__ 에서 채운다.
    department_id = SelectField("부서", coerce=int, validators=[Optional()])
    position = StringField("직급", validators=[Optional(), Length(max=50)])

    username = StringField(
        "아이디", validators=[DataRequired(message="아이디를 입력하세요."), Length(min=3, max=50)]
    )
    password = PasswordField(
        "비밀번호",
        validators=[Optional(), Length(min=6, message="비밀번호는 6자 이상이어야 합니다.")],
    )
    password_confirm = PasswordField(
        "비밀번호 확인",
        validators=[Optional(), EqualTo("password", message="비밀번호가 서로 다릅니다.")],
    )

    role = SelectField(
        "권한",
        choices=[(ROLE_MEMBER, "조직원"), (ROLE_ADMIN, "관리자")],
        validators=[DataRequired()],
    )
    is_active_user = BooleanField("활성 상태", default=True)
    submit = SubmitField("저장")

    def __init__(self, *args, departments=None, is_edit=False, **kwargs):
        """
        departments : 선택 가능한 부서 목록(Department 객체 리스트)
        is_edit     : 수정 모드인지 여부. 등록 모드면 비밀번호를 필수로 만든다.
        """
        super().__init__(*args, **kwargs)
        self.is_edit = is_edit

        # 부서 선택지를 만든다. 0 은 '미지정' 을 뜻하는 특별한 값이다.
        choices = [(0, "-- 부서 미지정 --")]
        for dept in departments or []:
            choices.append((dept.id, dept.name))
        self.department_id.choices = choices

    def validate_password(self, field):
        """등록 모드에서는 비밀번호를 반드시 입력해야 한다."""
        if not self.is_edit and not field.data:
            raise ValidationError("초기 비밀번호를 입력하세요.")


class KpiForm(FlaskForm):
    """KPI 등록/수정 폼 (관리자용)."""

    user_id = SelectField("담당 조직원", coerce=int, validators=[DataRequired()])
    title = StringField(
        "KPI명", validators=[DataRequired(message="KPI명을 입력하세요."), Length(max=150)]
    )
    description = TextAreaField("KPI 설명", validators=[Optional(), Length(max=1000)])

    target_value = DecimalField(
        "목표값",
        places=2,
        validators=[
            DataRequired(message="목표값을 입력하세요."),
            # 목표값이 0 이면 진행률을 계산할 수 없으므로 0 보다 커야 한다.
            NumberRange(min=0.01, message="목표값은 0보다 커야 합니다."),
        ],
    )
    current_value = DecimalField(
        "현재값",
        places=2,
        default=0,
        validators=[
            Optional(),
            NumberRange(min=0, message="현재값은 0 이상이어야 합니다."),
        ],
    )
    unit = SelectField(
        "단위", choices=[(u, u) for u in UNIT_CHOICES], validators=[DataRequired()]
    )

    start_date = DateField("시작일", validators=[DataRequired(message="시작일을 선택하세요.")])
    end_date = DateField("종료일", validators=[DataRequired(message="종료일을 선택하세요.")])

    weight = DecimalField(
        "가중치",
        places=1,
        default=1.0,
        validators=[
            DataRequired(message="가중치를 입력하세요."),
            NumberRange(min=0.1, max=10, message="가중치는 0.1 ~ 10 사이여야 합니다."),
        ],
    )
    submit = SubmitField("저장")

    def __init__(self, *args, users=None, **kwargs):
        """users : 선택 가능한 조직원 목록(User 객체 리스트)."""
        super().__init__(*args, **kwargs)
        self.user_id.choices = [
            (u.id, f"{u.name} ({u.department_name} / {u.employee_no})") for u in users or []
        ]

    def validate_end_date(self, field):
        """종료일이 시작일보다 앞서면 기간 계산이 음수가 되므로 막는다."""
        if self.start_date.data and field.data and field.data < self.start_date.data:
            raise ValidationError("종료일은 시작일보다 뒤여야 합니다.")


class KpiProgressForm(FlaskForm):
    """실적 입력 폼 (조직원이 본인 KPI 실적을 올릴 때 쓴다).

    조직원은 목표값이나 기간을 바꿀 수 없고 현재값만 입력할 수 있다.
    그래서 KpiForm 을 재사용하지 않고 별도의 작은 폼을 둔다.
    폼을 나누는 것 자체가 '조직원은 이 항목만 바꿀 수 있다' 는 안전장치가 된다.
    """

    current_value = DecimalField(
        "현재 실적",
        places=2,
        validators=[
            DataRequired(message="실적값을 입력하세요."),
            NumberRange(min=0, message="실적은 0 이상이어야 합니다."),
        ],
    )
    note = StringField("메모 (선택)", validators=[Optional(), Length(max=300)])
    submit = SubmitField("실적 반영")


class PasswordChangeForm(FlaskForm):
    """본인 비밀번호 변경 폼."""

    current_password = PasswordField(
        "현재 비밀번호", validators=[DataRequired(message="현재 비밀번호를 입력하세요.")]
    )
    new_password = PasswordField(
        "새 비밀번호",
        validators=[
            DataRequired(message="새 비밀번호를 입력하세요."),
            Length(min=6, message="비밀번호는 6자 이상이어야 합니다."),
        ],
    )
    new_password_confirm = PasswordField(
        "새 비밀번호 확인",
        validators=[
            DataRequired(message="새 비밀번호를 한 번 더 입력하세요."),
            EqualTo("new_password", message="비밀번호가 서로 다릅니다."),
        ],
    )
    submit = SubmitField("비밀번호 변경")
