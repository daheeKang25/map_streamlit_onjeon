from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Dict

import altair as alt
import folium
import pandas as pd
import streamlit as st
from branca.colormap import linear
from folium.features import GeoJsonTooltip
from streamlit_folium import st_folium


st.set_page_config(
    page_title="서울시 고령 취약성 지표 비교",
    page_icon="📊",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

SOURCE_FILENAMES = {
    "elderly_native": "고령자현황_내국인_구별_2024.csv",
    "elderly_basic": "2024_서울시_국민기초생활수급자_일반+생계+의료+구별_65세이상.csv",
    "alone_low": "독거노인_저소득.csv",
    "alone_total": "독거노인_총.csv",
    "alone_basic": "독거노인_기초수급.csv",
    "geojson": "seoul_municipalities_geo_simple.json",
}

INDICATORS = {
    "고령자 경제취약 비중": {
        "formula": "65세 이상 기초생활수급자 수 / 65세 이상 내국인 수 × 100",
        "description": "전체 고령자 중 경제적으로 취약한 고령자의 비율",
        "count_col": "elderly_basic",
        "count_label": "65세 이상 기초생활수급자 수",
    },
    "경제취약 독거노인 비중(기초생활수급자)": {
        "formula": "기초생활수급 독거노인 수 / 65세 이상 내국인 수 × 100",
        "description": "전체 고령자 중 기초생활수급 독거노인의 비율",
        "count_col": "alone_basic",
        "count_label": "기초생활수급 독거노인 수",
    },
    "경제취약 독거노인 비중(저소득층)": {
        "formula": "저소득 독거노인 수 / 65세 이상 내국인 수 × 100",
        "description": "전체 고령자 중 저소득 독거노인의 비율",
        "count_col": "alone_low",
        "count_label": "저소득 독거노인 수",
    },
    "경제취약 독거노인 통합비중": {
        "formula": "(기초생활수급 독거노인 수 + 저소득 독거노인 수) / 65세 이상 내국인 수 × 100",
        "description": "경제취약 독거노인을 종합적으로 반영한 통합 지표",
        "count_col": "통합지표",
        "count_label": "경제취약 독거노인 수(통합)",
    },
}

RAW_COLUMNS = ["자치구", "elderly_native", "elderly_basic", "alone_basic", "alone_low", "alone_total"]
DISPLAY_COLUMNS = [
    "자치구",
    "elderly_native",
    "elderly_basic",
    "alone_basic",
    "alone_low",
    "alone_total",
    "고령자 경제취약 비중",
    "경제취약 독거노인 비중(기초생활수급자)",
    "경제취약 독거노인 비중(저소득층)",
    "통합지표",
    "경제취약 독거노인 통합비중",
]
BASE_INDICATORS = [
    "고령자 경제취약 비중",
    "경제취약 독거노인 비중(기초생활수급자)",
    "경제취약 독거노인 비중(저소득층)",
]


# Altair row limit 해제
alt.data_transformers.disable_max_rows()


def normalize_district(value: str) -> str:
    if pd.isna(value):
        return value
    value = str(value).strip()
    mapping = {
        "동대문": "동대문구",
    }
    return mapping.get(value, value)


def resolve_data_path(filename: str) -> Path:
    preferred = DATA_DIR / filename
    if preferred.exists():
        return preferred

    fallback = BASE_DIR / filename
    if fallback.exists():
        return fallback

    return preferred


@st.cache_data(show_spinner=False)
def read_csv_auto(path_str: str) -> pd.DataFrame:
    path = Path(path_str)
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    last_error: Exception | None = None

    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    raise ValueError(f"CSV 파일을 읽지 못했습니다: {path.name} / 상세: {last_error}")


@st.cache_data(show_spinner=False)
def build_result_df() -> pd.DataFrame:
    missing_files = []
    for key, filename in SOURCE_FILENAMES.items():
        if key == "geojson":
            continue
        path = resolve_data_path(filename)
        if not path.exists():
            missing_files.append(path.as_posix())

    if missing_files:
        raise FileNotFoundError(
            "아래 데이터 파일이 없어 앱을 실행할 수 없습니다.\n- " + "\n- ".join(missing_files)
        )

    elderly_df = read_csv_auto(str(resolve_data_path(SOURCE_FILENAMES["elderly_native"]))).rename(
        columns={"고령자(내국인)수": "elderly_native"}
    )[["자치구", "elderly_native"]]

    basic_df = read_csv_auto(str(resolve_data_path(SOURCE_FILENAMES["elderly_basic"]))).rename(
        columns={"총 수급자수": "elderly_basic"}
    )[["자치구", "elderly_basic"]]

    alone_basic_df = read_csv_auto(str(resolve_data_path(SOURCE_FILENAMES["alone_basic"])))
    alone_basic_df = (
        alone_basic_df.assign(자치구=alone_basic_df["시군구"].map(normalize_district))
        .groupby("자치구", as_index=False)["전체수"]
        .sum()
        .rename(columns={"전체수": "alone_basic"})
    )

    alone_low_df = read_csv_auto(str(resolve_data_path(SOURCE_FILENAMES["alone_low"])))
    alone_low_df = (
        alone_low_df.assign(자치구=alone_low_df["시군구"].map(normalize_district))
        .groupby("자치구", as_index=False)["전체수"]
        .sum()
        .rename(columns={"전체수": "alone_low"})
    )

    alone_total_df = read_csv_auto(str(resolve_data_path(SOURCE_FILENAMES["alone_total"])))
    alone_total_df = (
        alone_total_df.assign(자치구=alone_total_df["시군구"].map(normalize_district))
        .groupby("자치구", as_index=False)["전체수"]
        .sum()
        .rename(columns={"전체수": "alone_total"})
    )

    result_df = elderly_df.merge(basic_df, on="자치구", how="left")
    result_df = result_df.merge(alone_basic_df, on="자치구", how="left")
    result_df = result_df.merge(alone_low_df, on="자치구", how="left")
    result_df = result_df.merge(alone_total_df, on="자치구", how="left")

    result_df["자치구"] = result_df["자치구"].map(normalize_district)

    for col in RAW_COLUMNS[1:]:
        result_df[col] = pd.to_numeric(result_df[col], errors="coerce").fillna(0)

    denominator = result_df["elderly_native"].replace(0, pd.NA)
    result_df["고령자 경제취약 비중"] = (result_df["elderly_basic"] / denominator) * 100
    result_df["경제취약 독거노인 비중(기초생활수급자)"] = (result_df["alone_basic"] / denominator) * 100
    result_df["경제취약 독거노인 비중(저소득층)"] = (result_df["alone_low"] / denominator) * 100
    result_df["통합지표"] = result_df["alone_basic"] + result_df["alone_low"]
    result_df["경제취약 독거노인 통합비중"] = (result_df["통합지표"] / denominator) * 100

    result_df = result_df.fillna(0)
    result_df = result_df.sort_values("자치구").reset_index(drop=True)
    return result_df[DISPLAY_COLUMNS].copy()


@st.cache_data(show_spinner=False)
def load_geojson() -> tuple[dict, str, Path]:
    path = resolve_data_path(SOURCE_FILENAMES["geojson"])
    if not path.exists():
        raise FileNotFoundError(
            f"서울시 GeoJSON 파일을 찾지 못했습니다: {path.as_posix()}\n"
            f"저장소에 'data/{SOURCE_FILENAMES['geojson']}' 파일을 추가해주세요."
        )

    with path.open("r", encoding="utf-8") as f:
        geojson = json.load(f)

    if not geojson.get("features"):
        raise ValueError("GeoJSON features가 비어 있습니다.")

    candidate_keys = ["name", "NAME", "SIG_KOR_NM", "sggnm", "sgg_nm", "SIGUNGU_NM"]
    first_properties = geojson["features"][0].get("properties", {})
    name_key = next((key for key in candidate_keys if key in first_properties), None)

    if name_key is None:
        raise ValueError("GeoJSON에서 자치구명 컬럼을 찾지 못했습니다.")

    return geojson, name_key, path


@st.cache_data(show_spinner=False)
def build_seoul_summary(df: pd.DataFrame) -> pd.Series:
    totals = {
        "자치구": "서울시 전체(합계 기준)",
        "elderly_native": df["elderly_native"].sum(),
        "elderly_basic": df["elderly_basic"].sum(),
        "alone_basic": df["alone_basic"].sum(),
        "alone_low": df["alone_low"].sum(),
        "alone_total": df["alone_total"].sum(),
    }
    totals["고령자 경제취약 비중"] = (totals["elderly_basic"] / totals["elderly_native"] * 100) if totals["elderly_native"] else 0
    totals["경제취약 독거노인 비중(기초생활수급자)"] = (totals["alone_basic"] / totals["elderly_native"] * 100) if totals["elderly_native"] else 0
    totals["경제취약 독거노인 비중(저소득층)"] = (totals["alone_low"] / totals["elderly_native"] * 100) if totals["elderly_native"] else 0
    totals["통합지표"] = totals["alone_basic"] + totals["alone_low"]
    totals["경제취약 독거노인 통합비중"] = (totals["통합지표"] / totals["elderly_native"] * 100) if totals["elderly_native"] else 0
    return pd.Series(totals)


def make_map(data: pd.DataFrame, column: str) -> folium.Map:
    geojson, name_key, _ = load_geojson()
    geojson_copy = copy.deepcopy(geojson)

    value_map: Dict[str, float] = data.set_index("자치구")[column].to_dict()
    top3_names = set(data.nlargest(3, column)["자치구"].tolist())
    min_val = float(data[column].min())
    max_val = float(data[column].max())

    if min_val == max_val:
        max_val = min_val + 1e-9

    color_scale = linear.YlOrRd_09.scale(min_val, max_val)
    color_scale.caption = f"{column} (%)"

    for feature in geojson_copy["features"]:
        district = normalize_district(feature["properties"].get(name_key, ""))
        value = value_map.get(district)
        feature["properties"]["자치구"] = district
        feature["properties"]["지표값"] = None if value is None else round(float(value), 2)
        feature["properties"]["is_top3"] = district in top3_names

    def style_function(feature):
        value = feature["properties"].get("지표값")
        is_top3 = feature["properties"].get("is_top3", False)
        return {
            "fillColor": "#d9d9d9" if value is None else color_scale(value),
            "color": "#0b3d91" if is_top3 else "white",
            "weight": 3 if is_top3 else 1.2,
            "fillOpacity": 0.85,
        }

    m = folium.Map(
        location=[37.55, 126.98],
        zoom_start=10.4,
        tiles="CartoDB positron",
        control_scale=True,
    )

    tooltip = GeoJsonTooltip(
        fields=["자치구", "지표값"],
        aliases=["자치구", "지표값(%)"],
        localize=True,
        sticky=False,
        labels=True,
        style=(
            "background-color: white; border: 1px solid #cccccc; border-radius: 6px; "
            "box-shadow: 0 2px 6px rgba(0,0,0,0.15); padding: 10px; font-size: 13px; color: #222222;"
        ),
    )

    folium.GeoJson(
        geojson_copy,
        style_function=style_function,
        highlight_function=lambda _: {"weight": 3, "color": "#222", "fillOpacity": 0.95},
        tooltip=tooltip,
    ).add_to(m)

    color_scale.add_to(m)
    return m


def kpi_card(title: str, value: str) -> None:
    st.markdown(
        f"""
        <div style="
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 14px;
            padding: 16px 18px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        ">
            <div style="font-size:13px; color:#6b7280; margin-bottom:8px;">{title}</div>
            <div style="font-size:28px; font-weight:700; color:#111827;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def make_donut_chart(target_count: float, total_count: float, count_label: str) -> alt.Chart:
    remainder = max(float(total_count) - float(target_count), 0)
    chart_df = pd.DataFrame(
        {
            "구성": [count_label, "기타 고령인구"],
            "인구수": [float(target_count), remainder],
        }
    )
    chart_df["비중"] = chart_df["인구수"] / float(total_count) * 100 if total_count else 0

    chart = (
        alt.Chart(chart_df)
        .mark_arc(innerRadius=60, outerRadius=95)
        .encode(
            theta=alt.Theta("인구수:Q"),
            color=alt.Color(
                "구성:N",
                scale=alt.Scale(domain=[count_label, "기타 고령인구"], range=["#2563eb", "#e5e7eb"]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("구성:N"),
                alt.Tooltip("인구수:Q", format=",.0f"),
                alt.Tooltip("비중:Q", format=".2f"),
            ],
        )
        .properties(height=240)
    )
    return chart


def render_indicator_block(df: pd.DataFrame, indicator: str, key_prefix: str) -> None:
    st.markdown(f"### {indicator}")
    st.caption(f"계산식: {INDICATORS[indicator]['formula']}")
    st.caption(INDICATORS[indicator]["description"])

    top3 = df[["자치구", indicator]].sort_values(indicator, ascending=False).head(3).copy()
    top3.columns = ["자치구", "지표값(%)"]
    top3["지표값(%)"] = top3["지표값(%)"].round(2)

    st_folium(make_map(df, indicator), height=430, use_container_width=True, key=f"{key_prefix}_{indicator}")
    st.dataframe(top3, use_container_width=True, hide_index=True)


def render_population_compare_section(df: pd.DataFrame) -> None:
    st.markdown("## 선택 자치구 인구 비교")
    st.caption("기본지표 1~3의 실제 인구수와 비중을 도넛차트로 비교합니다.")
    st.caption("서울시 비교 차트는 실제 인구수 표기를 위해 서울시 전체 합계 기준으로 계산했습니다.")

    district = st.selectbox("자치구 선택", sorted(df["자치구"].tolist()), key="district_compare")
    district_row = df.loc[df["자치구"] == district].iloc[0]
    seoul_row = build_seoul_summary(df)

    top_left, top_mid, top_right = st.columns(3)
    with top_left:
        kpi_card("선택 자치구", district)
    with top_mid:
        kpi_card("선택 자치구 고령자 수", f"{int(district_row['elderly_native']):,}명")
    with top_right:
        kpi_card("서울시 전체 고령자 수", f"{int(seoul_row['elderly_native']):,}명")

    for indicator in BASE_INDICATORS:
        config = INDICATORS[indicator]
        count_col = config["count_col"]
        count_label = config["count_label"]

        st.markdown(f"### {indicator}")
        st.caption(f"계산식: {config['formula']}")

        left, right = st.columns(2)

        district_rate = float(district_row[indicator])
        seoul_rate = float(seoul_row[indicator])
        district_count = float(district_row[count_col])
        seoul_count = float(seoul_row[count_col])
        district_total = float(district_row["elderly_native"])
        seoul_total = float(seoul_row["elderly_native"])

        with left:
            st.markdown(f"#### {district}")
            st.altair_chart(make_donut_chart(district_count, district_total, count_label), use_container_width=True)
            m1, m2 = st.columns(2)
            with m1:
                st.metric("비중", f"{district_rate:.2f}%", delta=f"{district_rate - seoul_rate:+.2f}%p")
            with m2:
                st.metric("인구수", f"{int(district_count):,}명")
            st.caption(f"{count_label}: {int(district_count):,}명 / 전체 고령자: {int(district_total):,}명")

        with right:
            st.markdown("#### 서울시 전체(합계 기준)")
            st.altair_chart(make_donut_chart(seoul_count, seoul_total, count_label), use_container_width=True)
            m1, m2 = st.columns(2)
            with m1:
                st.metric("비중", f"{seoul_rate:.2f}%")
            with m2:
                st.metric("인구수", f"{int(seoul_count):,}명")
            st.caption(f"{count_label}: {int(seoul_count):,}명 / 전체 고령자: {int(seoul_total):,}명")

        st.divider()


def render_file_status() -> None:
    rows = []
    for key, filename in SOURCE_FILENAMES.items():
        path = resolve_data_path(filename)
        label = "서울시 GeoJSON" if key == "geojson" else filename
        rows.append(
            {
                "파일": label,
                "경로": path.as_posix(),
                "상태": "존재" if path.exists() else "없음",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


st.title("서울시 고령 취약성 지표 통합 비교 대시보드")
st.markdown("내장된 원천 데이터 5종과 서울시 GeoJSON을 자동으로 불러와 4개 지표를 계산하고 비교합니다.")

with st.sidebar:
    st.header("내장 데이터 정보")
    render_file_status()
    st.caption("배포 전 아래 파일들이 저장소에 포함되어 있어야 합니다.")
    st.code(
        "data/고령자현황_내국인_구별_2024.csv\n"
        "data/2024_서울시_국민기초생활수급자_일반+생계+의료+구별_65세이상.csv\n"
        "data/독거노인_기초수급.csv\n"
        "data/독거노인_저소득.csv\n"
        "data/독거노인_총.csv\n"
        "data/seoul_municipalities_geo_simple.json",
        language="text",
    )

try:
    result_df = build_result_df()
    _, _, _ = load_geojson()
except Exception as e:  # noqa: BLE001
    st.error(f"내장 데이터 로딩 중 오류가 발생했습니다.\n\n{e}")
    st.info("저장소 루트 기준으로 data 폴더 안에 원천 CSV 5개와 서울시 GeoJSON 파일을 추가한 뒤 다시 배포해주세요.")
    st.stop()

with st.sidebar:
    csv_data = result_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "계산 결과 CSV 다운로드",
        data=csv_data,
        file_name="서울시_고령취약성_통합지표.csv",
        mime="text/csv",
    )

comparison_mode = st.radio(
    "비교 방식",
    ["4개 지표 동시 비교", "지표별 상세 보기"],
    horizontal=True,
)

st.divider()

if comparison_mode == "4개 지표 동시 비교":
    row1_col1, row1_col2 = st.columns(2)
    row2_col1, row2_col2 = st.columns(2)

    with row1_col1:
        render_indicator_block(result_df, "고령자 경제취약 비중", "map1")
    with row1_col2:
        render_indicator_block(result_df, "경제취약 독거노인 비중(기초생활수급자)", "map2")
    with row2_col1:
        render_indicator_block(result_df, "경제취약 독거노인 비중(저소득층)", "map3")
    with row2_col2:
        render_indicator_block(result_df, "경제취약 독거노인 통합비중", "map4")
else:
    selected_indicator = st.selectbox("지표 선택", list(INDICATORS.keys()))
    sorted_df = result_df[["자치구", selected_indicator]].sort_values(selected_indicator, ascending=False).copy()
    sorted_df["순위"] = range(1, len(sorted_df) + 1)
    sorted_df = sorted_df[["순위", "자치구", selected_indicator]]
    sorted_df[selected_indicator] = sorted_df[selected_indicator].round(2)

    max_row = sorted_df.iloc[0]
    min_row = sorted_df.iloc[-1]
    avg_val = result_df[selected_indicator].mean()

    k1, k2, k3 = st.columns(3)
    with k1:
        kpi_card("최고 자치구", f"{max_row['자치구']} ({max_row[selected_indicator]:.2f}%)")
    with k2:
        kpi_card("최저 자치구", f"{min_row['자치구']} ({min_row[selected_indicator]:.2f}%)")
    with k3:
        kpi_card("자치구 평균", f"{avg_val:.2f}%")

    left, right = st.columns([1.4, 1])
    with left:
        st.markdown(f"### {selected_indicator}")
        st.caption(f"계산식: {INDICATORS[selected_indicator]['formula']}")
        st_folium(make_map(result_df, selected_indicator), height=560, use_container_width=True, key="detail_map")
    with right:
        st.markdown("### 자치구 순위")
        st.dataframe(sorted_df, use_container_width=True, hide_index=True, height=560)

st.divider()
render_population_compare_section(result_df)

st.divider()
st.markdown("### 전체 데이터")
show_cols = [
    "자치구",
    "elderly_native",
    "elderly_basic",
    "alone_basic",
    "alone_low",
    "alone_total",
    "고령자 경제취약 비중",
    "경제취약 독거노인 비중(기초생활수급자)",
    "경제취약 독거노인 비중(저소득층)",
    "경제취약 독거노인 통합비중",
]
preview_df = result_df[show_cols].copy()
preview_df = preview_df.rename(
    columns={
        "elderly_native": "65세 이상 내국인 수",
        "elderly_basic": "65세 이상 기초생활수급자 수",
        "alone_basic": "기초생활수급 독거노인 수",
        "alone_low": "저소득 독거노인 수",
        "alone_total": "독거노인 총수",
    }
)
for col in preview_df.columns[1:6]:
    preview_df[col] = preview_df[col].map(lambda x: f"{int(x):,}")
for col in preview_df.columns[6:]:
    preview_df[col] = preview_df[col].round(2)

st.dataframe(preview_df, use_container_width=True, hide_index=True)
