import streamlit as st
import pandas as pd
from datetime import datetime
import re
import traceback

# =====================================================================
# [1단계] 철저한 예외 처리를 위한 데이터 정제 전용 도우미 함수 모음
# =====================================================================

def clean_string(val):
    """셀의 모든 공백, 줄바꿈, 탭 등 불순물을 완벽히 제거하여 순수 텍스트만 반환"""
    if pd.isna(val): 
        return ""
    return str(val).replace(" ", "").replace("\n", "").replace("\t", "").replace("\r", "").strip()

def parse_date_robustly(val, fallback_year):
    """
    엑셀의 날짜 데이터가 문자열, Datetime, 일련번호 등 어떤 형태이든 
    에러 없이 완벽하게 연도(YYYY)와 월(MM)로 변환하는 함수
    """
    if pd.isna(val):
        return None, fallback_year
        
    # 1. 이미 날짜 객체(Datetime)인 경우
    if isinstance(val, (datetime, pd.Timestamp)):
        return pd.Timestamp(val.year, val.month, 1), val.year
        
    # 2. 엑셀 특유의 숫자형 일련번호 날짜인 경우 (예: 45000)
    if isinstance(val, (int, float)) and 30000 < val < 70000:
        try:
            dt = pd.to_datetime(val, unit='D', origin='1899-12-30')
            return pd.Timestamp(dt.year, dt.month, 1), dt.year
        except Exception:
            pass

    # 3. 텍스트 형태인 경우 (예: '25.1월', '2025년 1월', '1월')
    str_val = clean_string(val)
    if not str_val:
        return None, fallback_year
        
    # 숫자만 전부 추출 (예: '2025년 1월' -> ['2025', '1'])
    nums = re.findall(r'\d+', str_val)
    
    # [치명적 오류 수정 구간] 숫자가 2개 이상이면 무조건 첫번째를 연도, 두번째를 월로 취급
    if len(nums) >= 2:
        try:
            # 완벽히 수정된 부분: int(nums)가 아닌 int(nums)로 배열 요소 명확히 지정
            y = int(nums[0])
            m = int(nums) 
            
            if y < 100: 
                y += 2000
            if 2000 <= y <= 2100 and 1 <= m <= 12:
                return pd.Timestamp(y, m, 1), y
        except Exception:
            pass
            
    # 연도 기재 없이 숫자가 1개('1월')만 있을 경우 이전 열의 연도를 이어받음
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
    
    # 마이너스(-) 부호와 소수점(.)을 포함한 숫자 패턴만 정밀 추출
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
        # 데이터 통로드
        df_raw = pd.read_excel(uploaded_file, header=None)
        
        anchor_r = -1
        anchor_c = -1
        
        # 1. 2차원 매트릭스 탐색으로 '구분' 기준점 찾기 (최대 50x50 범위)
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

        # 2. 기준점 우측으로 이동하며 유효한 날짜 컬럼 탐색
        parsed_dates = {}
        current_year = datetime.now().year
        
        # '구분' 행과 그 위아래 1줄씩(총 3줄) 스캔하여 날짜를 찾음 (셀 병합 대비)
        search_rows = [anchor_r]
        if anchor_r > 0: search_rows.append(anchor_r - 1)
        if anchor_r + 1 < len(df_raw): search_rows.append(anchor_r + 1)
        
        for c in range(anchor_c + 1, len(df_raw.columns)):
            found_date = None
            for r in search_rows:
                dt, y = parse_date_robustly(df_raw.iat[r, c], current_year)
                if dt is not None:
                    found_date = dt
                    current_year = y # 연도 갱신
                    break
            
            if found_date is not None:
                parsed_dates[c] = found_date

        if not parsed_dates:
            st.error("데이터 추출 실패: 연도 및 월 형식의 날짜 데이터를 인식하지 못했습니다.")
            return None

        # 3. 기준점 아래로 이동하며 지표와 수치 데이터 매핑
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

        # 4. 데이터프레임 구조화 및 피벗
        df_long = pd.DataFrame(records)
        
        # 날짜와 지표가 중복될 경우 합산(sum) 처리하여 ValueError 원천 방지
        df_long = df_long.groupby(['period', 'metric'], as_index=False)['value'].sum()
        
        df_pivot = df_long.pivot(index='period', columns='metric', values='value').reset_index()
        
        # 5. 필수 열(컬럼) 강제 생성 (KeyError 원천 방지)
        required_cols = ['접수', '컨택', '성공', '성공율', '설치완료']
        for col in required_cols:
            if col not in df_pivot.columns:
                df_pivot[col] = 0.0
                
        # 6. 정렬 및 성공율 강제 재계산 (엑셀 서식 무시하고 시스템 기준으로 덮어쓰기)
        df_pivot = df_pivot.sort_values('period').reset_index(drop=True)
        
        for idx, row in df_pivot.iterrows():
            접수 = row['접수']
            성공 = row['성공']
            # 접수가 0 이상일 경우에만 성공/접수로 성공율 재계산
            calc_rate = (성공 / 접수) if 접수 > 0 else 0.0
            df_pivot.at[idx, '성공율'] = calc_rate
            
        return df_pivot
        
    except Exception as e:
        st.error(f"예상치 못한 시스템 오류가 발생했습니다: {str(e)}")
        st.code(traceback.format_exc())
        return None

# =====================================================================
# [3단계] CRM 데이터 처리 및 종합 분석 모듈
# =====================================================================

def parse_crm_data(uploaded_file):
    """CRM 고객 데이터 파일 파싱 (나이/연령대 자동 계산)"""
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
    """대시보드 화면에 출력될 자동화 리포트 생성"""
    if df is None or df.empty: 
        return "분석 리포트를 생성할 수 있는 데이터가 부족합니다."
        
    latest = df.iloc[-1]
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
        
    if crm_df is not None and all(c in crm_df.columns for c in ['성공여부', '연령대', '성별']):
        try:
            stats = crm_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean())
            stats = stats.sort_values(ascending=False)
            if not stats.empty:
                best = stats.index[0]
                best_rate = stats.iloc[0]
                analysis_texts.append(
                    f"- **주요 타겟 고객층**: CRM 교차 분석 결과, **{best[0]} {best}** 고객군의 성공율이 **{best_rate:.1%}**로 "
                    f"가장 높게 측정되었습니다. CRM 마케팅 시 해당 타겟에 예산을 우선 배정하는 것을 권장합니다."
                )
        except Exception:
            pass
            
    return "\n\n".join(analysis_texts)

# =====================================================================
# [4단계] Streamlit 대시보드 UI (화면 렌더링)
# =====================================================================

st.set_page_config(layout="wide", page_title="통합 매출 대시보드")
st.title("매출 지표 종합 대시보드")
st.markdown("---")

st.sidebar.header("📁 데이터 업로드")
sales_file = st.sidebar.file_uploader("1. 매출 데이터 (필수)", type=["xlsx", "xls"])
crm_file = st.sidebar.file_uploader("2. CRM 데이터 (선택)", type=["xlsx", "xls"])

if sales_file:
    df = parse_sales_data(sales_file)
    crm_df = parse_crm_data(crm_file) if crm_file else None
    
    if df is not None and not df.empty:
        st.sidebar.success("✅ 데이터 렌더링 성공")
        
        latest_data = df.iloc[-1]
        prev_data = df.iloc[-2] if len(df) > 1 else None
        
        st.subheader(f"📍 {latest_data['period'].strftime('%Y년 %m월')} 월간 KPI (M-1 기준)")
        kpi_cols = st.columns(4)
        
        # 상단 핵심 지표 표출
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
            st.subheader("💡 AI 분석 리포트")
            st.markdown(generate_ai_analysis(df, crm_df))
            
            best_month = df.loc[df['성공율'].idxmax()]
            st.info(f"🏆 가장 성공율이 높았던 월: **{best_month['period'].strftime('%Y년 %m월')}** (성공율: {best_month['성공율']:.1%})")
            
        with col2:
            st.subheader("📈 설치 완료 건수 트렌드")
            
            start_d = df['period'].min().date()
            end_d = df['period'].max().date()
            
            chart_type = st.radio("그래프 뷰 선택", ["막대 그래프", "꺾은선형 그래프"], horizontal=True)
            date_range = st.date_input("조회 기간 커스텀", value=(start_d, end_d), min_value=start_d, max_value=end_d)
            
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_p, end_p = pd.to_datetime(date_range[0]), pd.to_datetime(date_range)
                chart_df = df[(df['period'] >= start_p) & (df['period'] <= end_p)].copy()
                
                if not chart_df.empty:
                    chart_df['조회월'] = chart_df['period'].dt.strftime('%Y-%m')
                    chart_data = chart_df.set_index('조회월')['설치완료']
                    
                    if chart_type == "막대 그래프":
                        st.bar_chart(chart_data)
                    else:
                        st.line_chart(chart_data)
                else:
                    st.warning("선택하신 기간 내에 데이터가 존재하지 않습니다.")
            else:
                st.info("기간의 시작일과 종료일을 모두 지정해주세요.")
        
        with st.expander("📄 데이터 원본 테이블 확인"): 
            st.dataframe(df.style.format({"성공율": "{:.2%}", "접수": "{:.0f}", "컨택": "{:.0f}", "성공": "{:.0f}", "설치완료": "{:.0f}"}))
            
    else:
        # 데이터프레임이 빈 값일 경우 (parse_sales_data 함수 내에서 이미 에러 출력함)
        pass
else:
    st.info("👈 좌측 사이드바에서 매출 데이터 엑셀 파일을 업로드하여 대시보드를 생성하십시오.")

