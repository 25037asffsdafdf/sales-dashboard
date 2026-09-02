import streamlit as st
import pandas as pd
from datetime import datetime
import traceback

# =====================================================================
# [1단계] 철저한 예외 처리가 적용된 헬퍼 함수
# =====================================================================

def clean_string(val):
    """셀의 공백 및 줄바꿈을 완벽히 제거"""
    if pd.isna(val): 
        return ""
    return str(val).replace(" ", "").replace("\n", "").replace("\t", "").strip()

def standardize_metric_name(raw_name):
    """어떤 형태의 지표명이든 5대 표준 명칭으로 통합"""
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
# [2단계] YYYYMM 포맷 맞춤형 데이터 파싱 로직 (오류 원천 차단)
# =====================================================================

def parse_sales_data(uploaded_file):
    try:
        # 결측치를 빈 문자열로 처리하여 통로드
        df_raw = pd.read_excel(uploaded_file, header=None)
        df_raw = df_raw.fillna("")

        header_r = -1
        header_c = -1
        
        # [방어 1] '구분' 셀의 정확한 좌표 탐색
        for r in range(min(50, len(df_raw))):
            for c in range(min(50, len(df_raw.columns))):
                if "구분" in clean_string(df_raw.iat[r, c]):
                    header_r = r
                    header_c = c
                    break
            if header_r != -1:
                break
                
        if header_r == -1:
            st.error("데이터 인식 실패: 표의 좌측 상단 기준점이 될 '구분' 항목을 찾을 수 없습니다.")
            return None

        parsed_dates = {}
        
        # [방어 2] 날짜 매핑: YYYYMM (예: 202501) 형식 절대 방어 로직
        for c in range(header_c + 1, len(df_raw.columns)):
            date_val = str(df_raw.iat[header_r, c]).strip()
            
            # 엑셀에서 숫자를 읽어올 때 '.0'이 붙는 현상 방지 (예: '202501.0' -> '202501')
            if date_val.endswith(".0"):
                date_val = date_val[:-2]
                
            # 정확히 6자리 숫자인지 확인 (TypeError 원천 차단)
            if len(date_val) == 6 and date_val.isdigit():
                y = int(date_val[:4])
                m = int(date_val[4:])
                
                if 2000 <= y <= 2100 and 1 <= m <= 12:
                    parsed_dates[c] = pd.Timestamp(y, m, 1)

        if not parsed_dates:
            st.error("데이터 추출 실패: '202501' 형태의 연월 데이터를 인식하지 못했습니다.")
            return None

        # [방어 3] 지표 추출 및 백분율/일반 숫자 안전 변환
        records = []
        for r in range(header_r + 1, len(df_raw)):
            raw_metric = df_raw.iat[r, header_c]
            metric = standardize_metric_name(raw_metric)
            
            if not metric:
                continue
                
            for c, period_dt in parsed_dates.items():
                val_raw = df_raw.iat[r, c]
                
                # 숫자로 변환 시도, 실패 시 0.0 처리
                try:
                    val = float(val_raw)
                except ValueError:
                    val = 0.0
                except TypeError:
                    val = 0.0
                    
                records.append({
                    'period': period_dt, 
                    'metric': metric, 
                    'value': val
                })

        if not records:
            st.error("데이터 추출 실패: 유효한 수치 데이터를 찾지 못했습니다.")
            return None

        # [방어 4] 중복 인덱스 충돌(ValueError) 방지를 위한 groupby 병합 처리
        df_long = pd.DataFrame(records)
        df_long = df_long.groupby(['period', 'metric'], as_index=False)['value'].sum()
        df_pivot = df_long.pivot(index='period', columns='metric', values='value').reset_index()
        
        # [방어 5] 필수 열 누락(KeyError) 방지
        required_cols = ['접수', '컨택', '성공', '성공율', '설치완료']
        for col in required_cols:
            if col not in df_pivot.columns:
                df_pivot[col] = 0.0
                
        df_pivot = df_pivot.sort_values('period').reset_index(drop=True)
        
        # [방어 6] 성공율 시스템 강제 재계산 (엑셀 서식 무시하고 절대값 확보)
        for idx, row in df_pivot.iterrows():
            접수 = row['접수']
            성공 = row['성공']
            calc_rate = (성공 / 접수) if 접수 > 0 else 0.0
            df_pivot.at[idx, '성공율'] = calc_rate
            
        return df_pivot
        
    except Exception as e:
        st.error(f"시스템 오류 발생: {str(e)}")
        st.code(traceback.format_exc())
        return None

# =====================================================================
# [3단계] CRM 데이터 파싱 및 AI 분석 모듈
# =====================================================================

def parse_crm_data(uploaded_file):
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
                
        return crm_df
    except Exception:
        return None

def generate_ai_analysis(df, crm_df=None):
    if df is None or df.empty: 
        return "데이터가 부족하여 리포트를 생성할 수 없습니다."
        
    latest = df.iloc[-1]
    analysis_texts = [f"### {latest['period'].strftime('%Y년 %m월')} 실적 요약"]
    
    last_year_dt = latest['period'].replace(year=latest['period'].year - 1)
    ly_data = df[df['period'] == last_year_dt]
    
    if not ly_data.empty:
        ly = ly_data.iloc[0]
        rec_diff = latest['접수'] - ly['접수']
        rate_diff = (latest['성공율'] - ly['성공율']) * 100
        
        trend_rec = "증가" if rec_diff > 0 else "감소"
        analysis_texts.append(
            f"- 전년 동월 대비 접수 건수는 {abs(rec_diff):,.0f}건 {trend_rec}하였으며, "
            f"성공율은 {rate_diff:+.1f}%p 변동하였습니다."
        )
        
    if crm_df is not None and all(c in crm_df.columns for c in ['성공여부', '연령대', '성별']):
        try:
            stats = crm_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean())
            stats = stats.sort_values(ascending=False)
            if not stats.empty:
                best = stats.index[0]
                best_rate = stats.iloc[0]
                analysis_texts.append(
                    f"- 타겟 분석: {best[0]} {best} 고객군의 성공율이 {best_rate:.1%}로 가장 높게 나타났습니다. "
                    f"해당 계층을 중점적으로 타게팅할 것을 권장합니다."
                )
        except Exception:
            pass
            
    return "\n\n".join(analysis_texts)

# =====================================================================
# [4단계] Streamlit 대시보드 UI 구성
# =====================================================================

st.set_page_config(layout="wide", page_title="통합 매출 대시보드")
st.title("매출 지표 종합 대시보드")
st.markdown("---")

st.sidebar.header("데이터 업로드")
sales_file = st.sidebar.file_uploader("1. 매출 데이터 (필수)", type=["xlsx", "xls"])
crm_file = st.sidebar.file_uploader("2. CRM 데이터 (선택)", type=["xlsx", "xls"])

if sales_file:
    df = parse_sales_data(sales_file)
    crm_df = parse_crm_data(crm_file) if crm_file else None
    
    if df is not None and not df.empty:
        st.sidebar.success("데이터 추출 및 처리 완료")
        
        latest_data = df.iloc[-1]
        prev_data = df.iloc[-2] if len(df) > 1 else None
        
        st.subheader(f"{latest_data['period'].strftime('%Y년 %m월')} 핵심 성과 지표 (M-1 기준)")
        kpi_cols = st.columns(4)
        
        for col, metric in zip(kpi_cols, ['접수', '컨택', '성공', '성공율']):
            val = latest_data[metric]
            delta = val - prev_data[metric] if prev_data is not None else 0
            
            if metric == '성공율': 
                col.metric(metric, f"{val:.1%}", f"{delta*100:+.1f}%p")
            else: 
                col.metric(f"{metric} (건)", f"{val:,.0f}", f"{delta:+.0f}")
        
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2 = st.columns([4, 6])
        
        with col1:
            st.subheader("데이터 분석 리포트")
            st.markdown(generate_ai_analysis(df, crm_df))
            
            best_month = df.loc[df['성공율'].idxmax()]
            st.info(f"최고 효율 기록월: {best_month['period'].strftime('%Y년 %m월')} (성공율: {best_month['성공율']:.1%})")
            
        with col2:
            st.subheader("설치 완료 건수 추이")
            
            start_d = df['period'].min().date()
            end_d = df['period'].max().date()
            
            chart_type = st.radio("그래프 형태 선택", ["막대 그래프", "꺾은선형 그래프"], horizontal=True)
            date_range = st.date_input("조회 기간 설정", value=(start_d, end_d), min_value=start_d, max_value=end_d)
            
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_p, end_p = pd.to_datetime(date_range[0]), pd.to_datetime(date_range)
                chart_df = df[(df['period'] >= start_p) & (df['period'] <= end_p)].copy()
                
                if not chart_df.empty:
                    # 인덱스를 문자열로 변환하여 시각화 에러 완벽 차단
                    chart_df['조회월'] = chart_df['period'].dt.strftime('%Y-%m')
                    chart_data = chart_df.set_index('조회월')['설치완료']
                    
                    if chart_type == "막대 그래프":
                        st.bar_chart(chart_data)
                    else:
                        st.line_chart(chart_data)
                else:
                    st.warning("선택하신 기간 내에 데이터가 존재하지 않습니다.")
            else:
                st.info("기간의 시작일과 종료일을 모두 지정해주십시오.")
        
        with st.expander("시스템 추출 데이터 원본 확인"): 
            st.dataframe(df.style.format({"성공율": "{:.2%}", "접수": "{:.0f}", "컨택": "{:.0f}", "성공": "{:.0f}", "설치완료": "{:.0f}"}))
            
    else:
        # 데이터프레임이 빈 값일 경우 에러 메시지는 parse_sales_data 내부에서 출력됨
        pass
else:
    st.info("좌측 사이드바에서 매출 데이터 파일을 업로드해주십시오.")
