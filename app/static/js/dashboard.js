/* =========================================================================
   관리자 대시보드 차트.

   하는 일
     1. 서버에서 차트 데이터(JSON)를 받아온다
     2. Chart.js 로 차트 3개를 그린다
     3. 30초마다 데이터를 다시 받아 차트를 갱신한다 (= '실시간' 대시보드)

   페이지 전체를 새로고침하지 않는 이유는, 새로고침하면 화면이 깜빡이고
   보고 있던 스크롤 위치가 맨 위로 돌아가 버리기 때문이다.
   숫자만 바꿔 끼우면 사용자가 보던 자리를 유지한 채 값만 바뀐다.
   ========================================================================= */

// 갱신 주기(밀리초). 30초.
// 너무 짧게 잡으면 서버에 부담이 되고, 너무 길면 '실시간' 느낌이 나지 않는다.
const REFRESH_INTERVAL = 30000;

// 템플릿이 data 속성으로 넘겨준 API 주소를 읽는다.
const config = document.getElementById("dashboardConfig");
const CHART_URL = config.dataset.url;

// 그려 둔 차트 객체를 보관한다. 갱신할 때 기존 객체를 재사용해야
// 차트가 중복으로 쌓이지 않는다.
const charts = {};

/* ----- 차트 공통 옵션 -------------------------------------------------
   maintainAspectRatio: false 로 두어야 부모 요소 크기에 맞춰 늘어난다.
   이게 true 면 화면을 줄였을 때 차트가 넘쳐서 반응형이 깨진다. */
const baseOptions = {
  responsive: true,
  maintainAspectRatio: false,
};

/** 막대그래프를 만든다 (가로 막대). */
function createBarChart(canvasId, labels, values, color) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;

  return new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [{
        label: "진행률(%)",
        data: values,
        backgroundColor: color,
        borderRadius: 4,
        maxBarThickness: 28,
      }],
    },
    options: {
      ...baseOptions,
      // 이름이 길어도 잘리지 않도록 가로 막대로 그린다.
      indexAxis: "y",
      scales: {
        x: {
          beginAtZero: true,
          max: 100,
          ticks: { callback: (value) => value + "%" },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: (item) => item.parsed.x + "%" },
        },
      },
    },
  });
}

/** 도넛그래프를 만든다 (상태 분포). */
function createDoughnutChart(canvasId, labels, values, colors) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;

  return new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderWidth: 2,
        borderColor: "#fff",
      }],
    },
    options: {
      ...baseOptions,
      cutout: "58%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 12, padding: 12, font: { size: 11 } },
        },
        tooltip: {
          callbacks: { label: (item) => item.label + " " + item.parsed + "건" },
        },
      },
    },
  });
}

/** 상단 요약 카드의 숫자를 갱신한다. */
function updateSummary(summary) {
  const map = {
    cardTotalKpi: summary.total_kpi + "건",
    cardProgress: summary.overall_progress + "%",
    cardAchieved: summary.achieved_rate + "%",
    cardAttention: summary.attention_count + "건",
  };

  for (const [id, text] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }
}

/** 마지막 갱신 시각을 화면에 표시한다. */
function markUpdated(text) {
  const el = document.getElementById("lastUpdated");
  if (el) el.textContent = text;
}

/** 서버에서 차트 데이터를 받아와 화면에 반영한다. */
async function loadCharts(isFirstLoad) {
  try {
    const res = await fetch(CHART_URL, {
      // 브라우저가 이전 응답을 캐시해서 옛날 숫자를 보여주는 것을 막는다.
      headers: { "Cache-Control": "no-cache" },
    });

    // 세션이 만료되면 로그인 화면 HTML 이 돌아온다. JSON 파싱이 깨지기 전에
    // 상태 코드로 먼저 걸러내고 로그인 화면으로 보낸다.
    if (res.status === 401 || res.status === 403) {
      location.href = "/login";
      return;
    }
    if (!res.ok) throw new Error("응답 오류 " + res.status);

    const data = await res.json();

    if (isFirstLoad) {
      // 첫 호출에서는 차트를 새로 만든다.
      charts.department = createBarChart(
        "departmentChart", data.department.labels, data.department.values, "#0dcaf0"
      );
      charts.status = createDoughnutChart(
        "statusChart", data.status.labels, data.status.values, data.status.colors
      );
      charts.member = createBarChart(
        "memberChart", data.member.labels, data.member.values, "#6610f2"
      );
    } else {
      // 이후에는 기존 차트의 데이터만 바꿔 끼운다.
      // 차트를 새로 만들면 매번 애니메이션이 처음부터 재생되어 산만해진다.
      applyData(charts.department, data.department.labels, data.department.values);
      applyData(charts.status, data.status.labels, data.status.values);
      applyData(charts.member, data.member.labels, data.member.values);
    }

    updateSummary(data.summary);

    const now = new Date();
    markUpdated(
      "최근 갱신 " +
      String(now.getHours()).padStart(2, "0") + ":" +
      String(now.getMinutes()).padStart(2, "0") + ":" +
      String(now.getSeconds()).padStart(2, "0")
    );
  } catch (err) {
    // 네트워크가 잠깐 끊겨도 대시보드는 계속 떠 있어야 한다.
    // 실패를 화면에 알리기만 하고, 다음 주기에 다시 시도한다.
    markUpdated("갱신 실패 (다시 시도합니다)");
    console.error("대시보드 데이터를 불러오지 못했습니다:", err);
  }
}

/** 이미 만들어진 차트의 데이터만 교체한다. */
function applyData(chart, labels, values) {
  if (!chart) return;
  chart.data.labels = labels;
  chart.data.datasets[0].data = values;
  chart.update();
}

// ----- 시작 -------------------------------------------------------------
loadCharts(true);
setInterval(() => loadCharts(false), REFRESH_INTERVAL);
