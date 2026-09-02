import streamlit as st
import pandas as pd
from datetime import datetime
import re
import traceback

# --- 1. 무결성 확보 데이터 파싱 ---
def parse_sales_data(uploaded_file):
    try:
        df_raw = pd.read_excel(uploaded_file, header=None)
        df_raw = df_raw.fillna("")

        header_r = -1
        header_c = -1
        
        # [검증 1] '구분' 셀의 정확한 2차원 좌표 탐색
        for r in range(len(df_raw)):
            for c in range(len(df_raw.columns)):
                cell_str = str(df_raw.iat[r, c]).replace(" ", "").replace("\n", "")
                if cell_str == "구분":
                    header_r = r
                    header_c = c
                    break
            if header_r != -1: break
            
        if header_r == -1:
            st.error("데이터 인식 실패: 표 좌측 상단에 '구분' 항목이 명시되어 있는지 확인해주십시오.")
            return None

        # [검증 2] 날짜(월) 데이터 추출 및 표준화
        parsed_dates = {}
        for c in range(header_c + 1, len(df_raw.columns)):
            date_val = str(df_raw.iat[header_r, c]).replace(" ", "")
            if not date_val: continue
            
            # 숫자만 추출하여 연도와 월 확인
            nums = re.findall(r'\d+', date_val)
            if len(nums) >= 2:
                # !!! 치명적이었던 오타 수정 완료 !!! (nums -> nums)
                year, month = int(nums[0]), int(nums)
                
                # 연도가 2자리로 입력되었을 경우 4자리로 보정
                if year < 100: year += 2000
                if 2000 <= year <= 2100 and 1 <= month <= 12:
                    parsed_dates[c] = pd.Timestamp(year, month, 1)
            elif len(nums) == 1:
                # 연도 없이 '1월' 처럼 월만 적혀있을 경우
                month = int(nums[0])
                if 1 <= month <= 12:
                    parsed_dates[c] = pd.Timestamp(datetime.now().year, month, 1)

        if not parsed_dates:
            st.error("데이터 인식 실패: '구분' 우측열에 위치한 날짜(연/월) 데이터를 인식하지 못했습니다.")
            return None

        # [검증 3] 지표명 표준화 및 수치 추출
        records = []
        for r in range(header_r + 1, len(df_raw)):
            metric_raw = str(df_raw.iat[r, header_c]).replace(" ", "").replace("\n", "")
            if not metric_raw: continue
            
            # 범용 지표명 매핑 규칙
            if '접수' in metric_raw and ('비' in metric_raw or '比' in metric_raw or '율' in metric_raw): metric = '성공율'
            elif '성공' in metric_raw and '율' in metric_raw: metric = '성공율'
            elif '설치' in metric_raw and '완료' in metric_raw: metric = '설치완료'
            elif '성공' in metric_raw: metric = '성공'
            elif '컨택' in metric_raw or '콜' in metric_raw: metric = '컨택'
            elif '접수' in metric_raw: metric = '접수'
            else: metric = metric_raw

            for c, period_dt in parsed_dates.items():
                val_raw = str(df_raw.iat[r, c]).replace(",", "").strip()
                v_num = re.sub(r'[^\d.-]', '', val_raw)
                try:
                    val = float(v_num) if v_num and v_num != '-' else 0.0
                except:
                    val = 0.0
                
                records.append({'period': period_dt, 'metric': metric, 'value': val})

        if not records:
            return None

        # [검증 4] 중복 인덱스 방지를 위한 피벗 테이블 생성
        df_long = pd.DataFrame(records)
        df_pivot = df_long.pivot_table(index='period', columns='metric', values='value', aggfunc='last').reset_index()
        
        # [검증 5] 필수 열 강제 할당
        for req_col in ['접수', '컨택', '성공', '성공율', '설치완료']:
            if req_col not in df_pivot.columns:
                df_pivot[req_col] = 0.0
                
        df_pivot = df_pivot.sort_values('period').reset_index(drop=True)
        
        # [검증 6] 성공율 시스템 강제 재계산
        df_pivot['성공율'] = df_pivot.apply(
            lambda row: row['성공'] / row['접수'] if row['접수'] > 0 else 0.0, axis=1
        )
        
        return df_pivot
        
    except Exception as e:
        st.error(f"시스템 오류 발생: {e}")
        st.code(traceback.format_exc())
        return None

# --- 2. CRM 데이터 파싱 ---
def parse_crm_data(uploaded_file):
    try:
        crm_df = pd.read_excel(uploaded_file)
        crm_df.columns = [str(col).strip().replace(" ", "") for col in crm_df.columns]
        
        if '생년월일' in crm_df.columns:
            crm_df['생년월일'] = pd.to_datetime(crm_df['생년월일'], errors='coerce')
            crm_df = crm_df.dropna(subset=['생년월일']).copy()
            current_year = datetime.now().year
            crm_df['나이'] = current_year - crm_df['생년월일'].dt.year
            crm_df['연령대'] = (crm_df['나이'] // 10 * 10).astype(int).astype(str) + '대'
            
        for col in ['성별', '성공여부']:
            if col in crm_df.columns:
                crm_df[col] = crm_df[col].astype(str).replace(r'\s+', '', regex=True)
                
        return crm_df
    except Exception as e:
        return None

# --- 3. 종합 분석 리포트 생성 ---
def generate_ai_analysis(df, crm_df=None):
    if df is None or df.empty: 
        return "데이터가 부족하여 분석 리포트를 생성할 수 없습니다."
        
    latest = df.iloc[-1]
    analysis_texts = [f"### {latest['period'].strftime('%Y년 %m월')} 실적 종합 리포트"]
    
    # 전년 동월 대비 분석
    last_year_month = latest['period'].replace(year=latest['period'].year - 1)
    last_year_data = df[df['period'] == last_year_month]
    
    if not last_year_data.empty:
        ly_data = last_year_data.iloc[0]
        reception_diff = latest['접수'] - ly_data['접수']
        success_rate_diff = (latest['성공율'] - ly_data['성공율']) * 100
        
        trend_reception = "증가" if reception_diff > 0 else "감소"
        analysis_texts.append(
            f"- 전년 동월 대비 접수 건수는 {abs(reception_diff):,.0f}건 {trend_reception}하였으며, "
            f"성공율은 {success_rate_diff:+.1f}%p 변동하였습니다."
        )
        
    # CRM 기반 인구통계학적 타겟 분석
    if crm_df is not None and all(c in crm_df.columns for c in ['성공여부', '연령대', '성별']):
        group_stats = crm_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean()).sort_values(ascending=False)
        if not group_stats.empty:
            best_group = group_stats.index[0]
            analysis_texts.append(
                f"- 고객 세분화 분석 결과, {best_group[0]} {best_group} 고객군의 성공율이 {group_stats.iloc[0]:.1%}로 "
                f"가장 높게 측정되었습니다. 향후 CRM 활용 시 해당 타겟층을 우선순위로 배정하는 것을 권장합니다."
            )
            
    return "\n\n".join(analysis_texts)

# --- 4. 대시보드 UI 구성 ---
st.set_page_config(layout="wide", page_title="매출 지표 대시보드")
st.title("매출 지표 종합 대시보드")

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
        
        st.subheader(f"{latest_data['period'].strftime('%Y년 %m월')} 핵심 성과 지표")
        kpi_cols = st.columns(4)
        for col, metric in zip(kpi_cols, ['접수', '컨택', '성공', '성공율']):
            val = latest_data[metric]
            delta = val - prev_data[metric] if prev_data is not None else 0
            
            if metric == '성공율': 
                col.metric(metric, f"{val:.1%}", f"{delta*100:+.1f}%p")
            else: 
                col.metric(f"{metric} (건)", f"{val:,.0f}", f"{delta:+.0f}")
        
        st.markdown("---")
        col1, col2 = st.columns([4, 6])
        
        with col1:
            st.subheader("데이터 분석 리포트")
            st.markdown(generate_ai_analysis(df, crm_df))
            
            best_month = df.loc[df['성공율'].idxmax()]
            st.info(f"최고 효율 기록월: {best_month['period'].strftime('%Y년 %m월')} (성공율 {best_month['성공율']:.1%})")
            
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
                    chart_df['조회월'] = chart_df['period'].dt.strftime('%Y-%m')
                    chart_data = chart_df.set_index('조회월')['설치완료']
                    
                    if chart_type == "막대 그래프":
                        st.bar_chart(chart_data)
                    else:
                        st.line_chart(chart_data)
                else:
                    st.warning("선택하신 기간 내에 유효한 데이터가 존재하지 않습니다.")
            else:
                st.info("기간의 시작일과 종료일을 모두 선택해주십시오.")
        
        with st.expander("시스템 정제 데이터 원본 보기"): 
            st.dataframe(df)
            
    else:
        st.error("데이터 처리 중 문제가 발생했습니다. 파일 형식을 다시 확인해주십시오.")
else:
    st.info("좌측 메뉴에서 매출 데이터를 업로드하여 대시보드를 활성화해주십시오.")
