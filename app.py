import streamlit as st
import pandas as pd
from datetime import datetime
import re
import traceback
import plotly.express as px

# =====================================================================
# [0단계] 고급 디자인 커스텀 CSS (입체감 및 카드형 UI 강화)
# =====================================================================
def apply_custom_css():
    st.markdown("""
        <style>
            /* 메인 배경색 (부드러운 아이보리 톤) */
            .stApp {
                background-color: #F9F9F6;
            }
            
            /* KPI 메트릭 카드 디자인 (입체감 강화) */
            [data-testid="stMetric"] {
                background-color: #FFFFFF;
                padding: 20px 25px;
                border-radius: 12px;
                box-shadow: 0px 6px 15px rgba(0, 0, 0, 0.08); /* 그림자 깊이 증가 */
                border: 1px solid #EAEAEA;
                border-left: 6px solid #2C3E50; /* 전문적인 다크 네이비 포인트 */
                transition: transform 0.2s ease;
            }
            
            [data-testid="stMetric"]:hover {
                transform: translateY(-3px);
                box-shadow: 0px 8px 20px rgba(0, 0, 0, 0.12);
            }
            
            /* 접었다 펼치는 보드(Expander) 컨테이너 입체감 디자인 */
            [data-testid="stExpander"] {
                background-color: #FFFFFF;
                border-radius: 12px;
                box-shadow: 0px 4px 12px rgba(0, 0, 0, 0.06);
                border: 1px solid #E5E5E5;
                margin-bottom: 15px;
            }
            
            /* 텍스트 폰트 컬러 최적화 */
            h1, h2, h3, h4 {
                color: #2C3E50 !important;
                font-weight: 700 !important;
            }
        </style>
    """, unsafe_allow_html=True)

# =====================================================================
# [1단계] 철저한 예외 처리를 위한 데이터 정제 전용 도우미 함수 모음
# =====================================================================

def clean_string(val):
    """셀의 모든 공백, 줄바꿈, 탭 등 불순물을 완벽히 제거하여 순수 텍스트만 반환"""
    if pd.isna(val): 
        return ""
    return str(val).replace(" ", "").replace("\n", "").replace("\t", "").replace("\r", "").strip()

def parse_date_robustly(val, fallback_year):
    """엑셀의 날짜 데이터가 문자열, Datetime, 일련번호 등 어떤 형태이든 에러 없이 완벽하게 연도와 월로 변환"""
    if pd.isna(val):
        return None, fallback_year
        
    if isinstance(val, (datetime, pd.Timestamp)):
        return pd.Timestamp(val.year, val.month, 1), val.year
        
    if isinstance(val, (int, float)) and 30000 < val < 70000:
        try:
            dt = pd.to_datetime(val, unit='D', origin='1899-12-30')
            return pd.Timestamp(dt.year, dt.month, 1), dt.year
        except Exception:
            pass

    str_val = clean_string(val)
    if not str_val:
        return None, fallback_year
        
    nums = re.findall(r'\d+', str_val)
    if len(nums) >= 2:
        try:
            y = int(nums[0])
            m = int(nums[1]) 
            if y < 100: 
                y += 2000
            if 2000 <= y <= 2100 and 1 <= m <= 12:
                return pd.Timestamp(y, m, 1), y
        except Exception:
            pass
            
    elif len(nums) == 1:
        try:
            m = int(nums[0])
            if 1 <= m <= 12:
                return pd.Timestamp(fallback_year, m, 1), fallback_year
        except Exception:
            pass

    return None, fallback_year

def extract_numeric_value(val):
    """엑셀 셀에서 특수기호, 텍스트가 섞여 있어도 순수 수치(Float)만 추출"""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
        
    str_val = str(val).replace(",", "").strip()
    match = re.search(r'[-+]?\d*\.?\d+', str_val)
    if match:
        try:
            return float(match.group())
        except Exception:
            return 0.0
    return 0.0

def standardize_metric_name(raw_name):
    """어떤 형태로 지표명이 적혀있든 시스템 표준 명칭으로 강제 통합"""
    clean_name = clean_string(raw_name)
    if not clean_name:
        return None
        
    if '접수' in clean_name and ('비' in clean_name or '比' in clean_name or '율' in clean_name or '률' in clean_name): 
        return '성공율'
    if '성공' in clean_name and ('율' in clean_name or '률' in clean_name): 
        return '성공율'
    if '설치' in clean_name and '완료' in clean_name: 
        return '설치완료'
    if '성공' in clean_name: 
        return '성공'
    if '컨택' in clean_name or '콜' in clean_name: 
        return '컨택'
    if '접수' in clean_name: 
        return '접수'
        
    return clean_name

# =====================================================================
# [2단계] 메인 매출 데이터 파싱 로직 (모든 변수 고려)
# =====================================================================

def parse_sales_data(uploaded_file):
    try:
        df_raw = pd.read_excel(uploaded_file, header=None)
        df_raw = df_raw.fillna("")
        
        anchor_r = -1
        anchor_c = -1
        
        max_r = min(50, len(df_raw))
        max_c = min(50, len(df_raw.columns))
        
        for r in range(max_r):
            for c in range(max_c):
                if "구분" in clean_string(df_raw.iat[r, c]):
                    anchor_r = r
                    anchor_c = c
                    break
            if anchor_r != -1:
                break
                
        if anchor_r == -1:
            st.error("엑셀 파일 인식 실패: 표의 좌측 상단 기준점이 될 '구분' 항목을 찾을 수 없습니다.")
            return None

        parsed_dates = {}
        current_year = datetime.now().year
        
        search_rows = [anchor_r]
        if anchor_r > 0: search_rows.append(anchor_r - 1)
        if anchor_r + 1 < len(df_raw): search_rows.append(anchor_r + 1)
        
        for c in range(anchor_c + 1, len(df_raw.columns)):
            found_date = None
            for r in search_rows:
                dt, y = parse_date_robustly(df_raw.iat[r, c], current_year)
                if dt is not None:
                    found_date = dt
                    current_year = y
                    break
            
            if found_date is not None:
                parsed_dates[c] = found_date

        if not parsed_dates:
            st.error("데이터 추출 실패: 연도 및 월 형식의 날짜 데이터를 인식하지 못했습니다.")
            return None

        records = []
        for r in range(anchor_r + 1, len(df_raw)):
            raw_metric = df_raw.iat[r, anchor_c]
            metric = standardize_metric_name(raw_metric)
            
            if not metric:
                continue
                
            for c, period_dt in parsed_dates.items():
                val = extract_numeric_value(df_raw.iat[r, c])
                records.append({
                    'period': period_dt, 
                    'metric': metric, 
                    'value': val
                })

        if not records:
            st.error("데이터 추출 실패: 유효한 수치 데이터를 찾지 못했습니다.")
            return None

        df_long = pd.DataFrame(records)
        df_long = df_long.groupby(['period', 'metric'], as_index=False)['value'].sum()
        
        df_pivot = df_long.pivot(index='period', columns='metric', values='value').reset_index()
        
        required_cols = ['접수', '컨택', '성공', '성공율', '설치완료']
        for col in required_cols:
            if col not in df_pivot.columns:
                df_pivot[col] = 0.0
                
        df_pivot = df_pivot.sort_values('period').reset_index(drop=True)
        
        # 성공율 시스템 강제 재계산
        df_pivot['성공율'] = df_pivot.apply(
            lambda row: row['성공'] / row['접수'] if row.get('접수', 0) > 0 else 0.0, axis=1
        )
        
        return df_pivot
        
    except Exception as e:
        st.error(f"예상치 못한 시스템 오류가 발생했습니다: {str(e)}")
        st.code(traceback.format_exc())
        return None

# =====================================================================
# [3단계] CRM 데이터 처리 및 고도화된 AI 마케팅 분석 리포트
# =====================================================================

def parse_crm_data(uploaded_file):
    """CRM 고객 데이터 파일 파싱 (나이/연령대/연도 자동 계산)"""
    try:
        crm_df = pd.read_excel(uploaded_file)
        crm_df.columns = [clean_string(col) for col in crm_df.columns]
        
        if '생년월일' in crm_df.columns:
            crm_df['생년월일'] = pd.to_datetime(crm_df['생년월일'], errors='coerce')
            crm_df = crm_df.dropna(subset=['생년월일']).copy()
            current_year = datetime.now().year
            crm_df['나이'] = current_year - crm_df['생년월일'].dt.year
            crm_df['연령대'] = (crm_df['나이'] // 10 * 10).astype(int).astype(str) + '대'
            
        for col in ['성별', '성공여부']:
            if col in crm_df.columns:
                crm_df[col] = crm_df[col].astype(str).apply(clean_string)
                
        # 가입일, 접수일 등을 찾아 '연도'를 추출하여 그룹화 지원
        date_col = next((c for c in crm_df.columns if '일' in c and ('가입' in c or '접수' in c or '등록' in c)), None)
        if date_col:
            crm_df['연도'] = pd.to_datetime(crm_df[date_col], errors='coerce').dt.year
        else:
            crm_df['연도'] = "전체 기간"
            
        return crm_df
    except Exception:
        return None

def generate_ai_analysis(df, selected_period, crm_df=None):
    """대시보드 화면에 출력될 전문적인 자동화 리포트 생성"""
    if df is None or df.empty: 
        return "분석 리포트를 생성할 수 있는 데이터가 부족합니다."
        
    current_data = df[df['period'] == selected_period]
    if current_data.empty or current_data.iloc[0]['접수'] == 0:
        return "선택하신 월의 실적 데이터가 충분하지 않습니다."
        
    latest = current_data.iloc[0]
    analysis_texts = [f"### {latest['period'].strftime('%Y년 %m월')} 비즈니스 요약"]
    
    # 전년 동월 데이터 탐색
    last_year_dt = latest['period'].replace(year=latest['period'].year - 1)
    ly_data = df[df['period'] == last_year_dt]
    
    if not ly_data.empty:
        ly = ly_data.iloc[0]
        rec_diff = latest['접수'] - ly['접수']
        rate_diff = (latest['성공율'] - ly['성공율']) * 100
        
        trend_rec = "증가" if rec_diff > 0 else "감소"
        analysis_texts.append(
            f"- **전년 동월 대비 성과**: 접수 건수는 **{abs(rec_diff):,.0f}건 {trend_rec}**하였으며, "
            f"성공율은 **{rate_diff:+.1f}%p 변동**하였습니다."
        )
        
    if crm_df is not None and all(c in crm_df.columns for c in ['성공여부', '연령대', '성별', '연도']):
        analysis_texts.append("\n---\n#### 인구통계학적(Demographic) 코호트 전환율 분석")
        
        # 전문적인 테이블 양식 포맷팅 반영
        table_md = "| 분석 연도 | 최우수 전환 타겟 (최고 성공율) | 전환 취약 타겟 (최저 성공율) |\n|:---|:---|:---|\n"
        years = sorted([y for y in crm_df['연도'].unique() if pd.notna(y)])
        
        has_valid_stats = False
        for y in years:
            y_df = crm_df[crm_df['연도'] == y]
            if y_df.empty: continue
            
            stats = y_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean())
            stats = stats.sort_values(ascending=False)
            
            if not stats.empty and len(stats) >= 1:
                best = stats.index[0]
                best_rate = stats.iloc[0] * 100
                
                worst = stats.index[-1]
                worst_rate = stats.iloc[-1] * 100
                
                y_label = f"{int(y)}년" if isinstance(y, (int, float)) else str(y)
                
                # 표기 에러 수정 (best[1]성 적용하여 완벽하게 "20대 남성" 형태 출력)
                table_md += f"| **{y_label}** | {best[0]} {best[1]}성 ({best_rate:.1f}%) | {worst[0]} {worst[1]}성 ({worst_rate:.1f}%) |\n"
                has_valid_stats = True
                
        if has_valid_stats:
            analysis_texts.append(table_md)
            analysis_texts.append("\n#### 💡 경영/데이터 마케팅 AI 인사이트 제언")
            analysis_texts.append(
                "1. **선택과 집중을 통한 LTV(고객생애가치) 극대화**: 전환율 최상위 코호트(Top-tier)는 고객 획득 비용(CAC) 회수율이 가장 우수한 핵심 세그먼트입니다. "
                "해당 타겟층을 대상으로 예산을 우선 배정(Resource Allocation)하여 록인(Lock-in) 및 업셀링(Up-selling) 전략을 공격적으로 전개할 것을 권장합니다.\n"
                "2. **미드티어(Middle-tier) 넛지(Nudge) 캠페인 도입**: 성과 부진 또는 중간 수준의 전환율을 보이는 세그먼트에 대해서는 무리한 푸시 마케팅을 지양해야 합니다. "
                "고객 여정(Customer Journey) 내 이탈이 발생하는 병목(Bottleneck) 구간을 정밀 분석하고, 개인화된 리타겟팅(Re-targeting) 및 A/B 테스트를 통해 "
                "점진적인 전환율 개선(Conversion Rate Optimization)을 도모하는 STP 고도화 전략이 요구됩니다."
            )
            
    return "\n".join(analysis_texts)

# =====================================================================
# [4단계] Streamlit 대시보드 UI (화면 렌더링)
# =====================================================================

st.set_page_config(layout="wide", page_title="통합 매출 대시보드")
apply_custom_css()

st.title("현대렌탈케어 고객만족센터 매출관리 대시보드")
st.markdown("---")

st.sidebar.header("데이터 업로드")
sales_file = st.sidebar.file_uploader("1. 매출 데이터 (필수)", type=["xlsx", "xls"])
crm_file = st.sidebar.file_uploader("2. CRM 데이터 (선택)", type=["xlsx", "xls"])

if sales_file:
    df = parse_sales_data(sales_file)
    crm_df = parse_crm_data(crm_file) if crm_file else None
    
    if df is not None and not df.empty:
        st.sidebar.success("데이터 렌더링 성공")
        
        valid_periods = df[df['접수'] > 0]['period']
        default_period = valid_periods.max() if not valid_periods.empty else df['period'].max()
        
        available_years = sorted(df['period'].dt.year.unique().tolist())
        months = list(range(1, 13))
        
        st.markdown("#### 메인 KPI 조회 기준월 설정")
        m_col1, m_col2, _ = st.columns([1.5, 1.5, 7])
        
        with m_col1:
            sel_main_y = st.selectbox("기준 연도", options=available_years, index=available_years.index(default_period.year), format_func=lambda x: f"{x}년", key="main_y")
        with m_col2:
            sel_main_m = st.selectbox("기준 월", options=months, index=months.index(default_period.month), format_func=lambda x: f"{x}월", key="main_m")
            
        selected_period = pd.to_datetime(f"{sel_main_y}-{sel_main_m}-01")
        current_data_df = df[df['period'] == selected_period]
        
        if current_data_df.empty or current_data_df.iloc[0]['접수'] == 0:
            st.warning(f"{sel_main_y}년 {sel_main_m}월의 실적 데이터가 입력되지 않았습니다. 메인 지표는 0으로 표기됩니다.")
            latest_data = pd.Series({'접수':0, '컨택':0, '성공':0, '성공율':0.0, '설치완료':0})
        else:
            latest_data = current_data_df.iloc[0]
            
        prev_period = selected_period - pd.DateOffset(months=1)
        prev_data_df = df[df['period'] == prev_period]
        prev_data = prev_data_df.iloc[0] if not prev_data_df.empty else None
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.expander(f"{sel_main_y}년 {sel_main_m}월 핵심 성과 지표", expanded=True):
            kpi_cols = st.columns(4)
            for col, metric in zip(kpi_cols, ['접수', '컨택', '성공', '성공율']):
                val = latest_data.get(metric, 0)
                delta = val - prev_data[metric] if prev_data is not None else 0
                
                if metric == '성공율': 
                    col.metric(metric, f"{val:.1%}", f"{delta*100:+.1f}%p")
                else: 
                    col.metric(f"{metric} (건)", f"{val:,.0f}", f"{delta:+.0f}")
                    
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2 = st.columns([3.5, 6.5])
        
        with col1:
            with st.expander("데이터 분석 리포트", expanded=True):
                st.markdown(generate_ai_analysis(df, selected_period, crm_df))
                
                st.markdown("<br><b>연도별 최고 실적 현황 (성공율 기준)</b>", unsafe_allow_html=True)
                df['year'] = df['period'].dt.year
                df_valid = df[df['성공율'] > 0]
                if not df_valid.empty:
                    best_per_year = df_valid.loc[df_valid.groupby('year')['성공율'].idxmax()]
                    year_cols = st.columns(len(best_per_year))
                    for y_col, (_, row) in zip(year_cols, best_per_year.iterrows()):
                        y_col.caption(f"{row['year']}년 최고 실적\n\n{row['period'].strftime('%m월')} (성공율 {row['성공율']:.1%})")

        with col2:
            with st.expander("지표별 트렌드 분석 (시각화)", expanded=True):
                vis_col1, vis_col2 = st.columns(2)
                with vis_col1:
                    target_metric = st.selectbox("분석 지표 커스터마이징", ['설치완료', '접수', '컨택', '성공', '성공율'])
                with vis_col2:
                    chart_type = st.radio("그래프 형태 선택", ["막대 그래프", "꺾은선형 그래프"], horizontal=True)
                    
                st.markdown("<br><b>차트 조회 기간 설정</b>", unsafe_allow_html=True)
                start_d = df['period'].min()
                end_d = df['period'].max()
                
                sc1, sc2, sc3, sc4 = st.columns(4)
                with sc1:
                    start_y = st.selectbox("시작 연도", options=available_years, index=0, format_func=lambda x: f"{x}년", key="c_sy")
                with sc2:
                    start_m_idx = months.index(start_d.month) if start_y == start_d.year else 0
                    start_m = st.selectbox("시작 월", options=months, index=start_m_idx, format_func=lambda x: f"{x}월", key="c_sm")
                with sc3:
                    end_y = st.selectbox("종료 연도", options=available_years, index=len(available_years)-1, format_func=lambda x: f"{x}년", key="c_ey")
                with sc4:
                    end_m_idx = months.index(end_d.month) if end_y == end_d.year else 11
                    end_m = st.selectbox("종료 월", options=months, index=end_m_idx, format_func=lambda x: f"{x}월", key="c_em")
                    
                start_p = pd.to_datetime(f"{start_y}-{start_m}-01")
                end_p = pd.to_datetime(f"{end_y}-{end_m}-01")
                
                if start_p > end_p:
                    st.warning("시작 연/월이 종료 연/월보다 늦을 수 없습니다.")
                else:
                    chart_df = df[(df['period'] >= start_p) & (df['period'] <= end_p)].copy()
                    chart_df = chart_df[chart_df[target_metric] > 0]
                    
                    if not chart_df.empty:
                        chart_df['조회월'] = chart_df['period'].dt.strftime('%y년 ') + chart_df['period'].dt.month.astype(str) + '월'
                        
                        if target_metric == '성공율':
                            chart_df[target_metric] = chart_df[target_metric] * 100

                        if chart_type == "막대 그래프":
                            fig = px.bar(chart_df, x='조회월', y=target_metric, text=target_metric)
                            fig.update_traces(
                                texttemplate='%{text:.1f}' if target_metric == '성공율' else '%{text:,.0f}',
                                textposition='outside', 
                                marker_color='#1E88E5', 
                                textfont_size=13,
                                cliponaxis=False        
                            )
                        else:
                            fig = px.line(chart_df, x='조회월', y=target_metric, markers=True, text=target_metric)
                            fig.update_traces(
                                line=dict(width=3, color='#1E88E5'), 
                                marker=dict(size=8, color='#2C3E50'),
                                texttemplate='%{text:.1f}' if target_metric == '성공율' else '%{text:,.0f}',
                                textposition="top center",
                                textfont_size=13,
                                cliponaxis=False
                            )
                            
                        max_val = chart_df[target_metric].max()
                        y_max_range = max_val * 1.2 if max_val > 0 else 1.0

                        fig.update_layout(
                            plot_bgcolor='rgba(255,255,255,1)',
                            paper_bgcolor='rgba(255,255,255,1)',
                            xaxis_title="",
                            yaxis_title="",  
                            margin=dict(l=10, r=10, t=70, b=10),
                            xaxis=dict(showgrid=False, tickangle=-45, type='category', categoryorder='array', categoryarray=chart_df['조회월']),
                            yaxis=dict(showgrid=True, gridcolor='#F0F0F0', range=[0, y_max_range]),
                            annotations=[dict(
                                x=0, y=1.15, xref='paper', yref='paper',
                                text=f"<b>{target_metric}</b> {'(%)' if target_metric == '성공율' else '(건)'}", 
                                showarrow=False, font=dict(size=14, color='#555555'), xanchor='left', yanchor='bottom'
                            )]
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        if target_metric == '성공율':
                            st.caption("※ 성공율은 백분율(%) 스케일로 출력됩니다.")
                    else:
                        st.warning("선택하신 기간 내에 유효한 수치 데이터가 존재하지 않습니다.")
        
        with st.expander("데이터 원본 표 확인", expanded=False):
            display_df = df.drop(columns=['year'], errors='ignore').copy()
            display_df['조회월'] = display_df['period'].dt.strftime('%Y-%m')
            display_df = display_df.set_index('조회월').drop(columns=['period'])
            st.dataframe(display_df.style.format({
                "성공율": "{:.2%}", "접수": "{:.0f}", "컨택": "{:.0f}", "성공": "{:.0f}", "설치완료": "{:.0f}"
            }))
            
    else:
        st.error("데이터 처리 중 문제가 발생했습니다. 파일 형식을 다시 확인해주십시오.")
else:
    st.info("좌측 메뉴에서 매출 데이터를 업로드하여 대시보드를 시작해주십시오.")
