import streamlit as st
import pandas as pd
from datetime import datetime
import re

# --- 데이터 파싱 로직 ---
def parse_sales_data(uploaded_file):
    try:
        df_raw = pd.read_excel(uploaded_file, header=None)
        
        start_idx = None
        target_col = None
        
        # 1. 항목 인식 (공백 무시 및 범용 탐색)
        for idx, row in df_raw.iterrows():
            clean_row = row.astype(str).str.replace(r'\s+', '', regex=True)
            for col_idx, cell_value in enumerate(clean_row):
                if '구분' in cell_value:
                    start_idx = idx
                    target_col = col_idx
                    break
            if start_idx is not None:
                break
                
        if start_idx is None:
            st.error("엑셀 파일 내에서 '구분' 항목을 찾을 수 없습니다. 표의 형태를 확인해주십시오.")
            return None
            
        df_table = df_raw.iloc[start_idx:].copy()
        
        # 2. 헤더 설정
        headers = df_table.iloc[0].astype(str).str.replace(r'\s+', '', regex=True).tolist()
        df_table.columns = headers
        df_table = df_table.iloc[1:]
        
        g_col = headers[target_col]
        
        melted = df_table.melt(id_vars=[g_col], var_name='period_str', value_name='value')
        melted = melted.rename(columns={g_col: 'metric'})
        
        # 3. 결측치 및 불필요한 데이터 제거
        melted = melted[~melted['period_str'].str.contains('nan', case=False, na=False)]
        melted = melted[~melted['metric'].astype(str).str.contains('nan', case=False, na=False)]
        
        # 4. 날짜 데이터 정제 (숫자만 추출하여 정확한 날짜로 매핑)
        def parse_date(p):
            nums = re.sub(r'[^\d]', '', str(p))
            if len(nums) == 3: return f"20{nums[:2]}-0{nums[-1]}-01"
            elif len(nums) == 4: return f"20{nums[:2]}-{nums[2:]}-01"
            elif len(nums) == 5: return f"{nums[:4]}-0{nums[-1]}-01"
            elif len(nums) == 6: return f"{nums[:4]}-{nums[4:]}-01"
            return None
            
        melted['period_dt'] = pd.to_datetime(melted['period_str'].apply(parse_date), errors='coerce')
        melted = melted.dropna(subset=['period_dt'])
        
        # 5. 지표명 표준화
        def standardize_metric(m):
            if '접수' in m and '성공' in m and ('율' in m or '률' in m or '비' in m or '比' in m): return '성공율'
            if '성공' in m and '율' in m: return '성공율'
            if '접수' in m: return '접수'
            if '컨택' in m: return '컨택'
            if '설치' in m and '완료' in m: return '설치완료'
            if '성공' in m: return '성공'
            return m
            
        melted['metric'] = melted['metric'].astype(str).str.replace(r'\s+', '', regex=True).apply(standardize_metric)
        
        # 6. 피벗 테이블 생성
        final_df = melted.pivot_table(index='period_dt', columns='metric', values='value', aggfunc='first').reset_index()
        final_df = final_df.rename(columns={'period_dt': 'period'})
        
        # 7. 숫자 변환 및 계산
        for col in ['접수', '컨택', '성공', '설치완료', '성공율']:
            if col in final_df.columns:
                final_df[col] = final_df[col].astype(str).apply(lambda x: re.sub(r'[^\d.]', '', x))
                final_df[col] = pd.to_numeric(final_df[col], errors='coerce')
                
        if '성공율' in final_df.columns:
            final_df.loc[final_df['성공율'] > 1.0, '성공율'] /= 100.0
        elif '성공' in final_df.columns and '접수' in final_df.columns:
            final_df['성공율'] = (final_df['성공'] / final_df['접수']).fillna(0)
            
        cols_to_keep = ['period', '접수', '컨택', '성공', '성공율', '설치완료']
        final_df = final_df[[c for c in cols_to_keep if c in final_df.columns]]
        final_df = final_df.sort_values('period').reset_index(drop=True)
        
        return final_df
    except Exception as e:
        st.error(f"데이터 처리 오류: {e}")
        return None

def parse_crm_data(uploaded_file):
    try:
        crm_df = pd.read_excel(uploaded_file)
        crm_df.columns = [str(col).strip().replace(" ", "") for col in crm_df.columns]
        
        if '생년월일' in crm_df.columns:
            crm_df['생년월일'] = pd.to_datetime(crm_df['생년월일'], errors='coerce')
            crm_df = crm_df.dropna(subset=['생년월일'])
            current_year = datetime.now().year
            crm_df['나이'] = current_year - crm_df['생년월일'].dt.year
            crm_df['연령대'] = (crm_df['나이'] // 10 * 10).astype(int).astype(str) + '대'
            
        for col in ['성별', '성공여부']:
            if col in crm_df.columns:
                crm_df[col] = crm_df[col].astype(str).replace(r'\s+', '', regex=True)
                
        return crm_df
    except Exception as e:
        st.error(f"CRM 데이터 처리 오류: {e}")
        return None

def generate_ai_analysis(df, crm_df=None):
    if df is None or df.empty: 
        return "분석할 데이터가 존재하지 않습니다."
        
    latest = df.iloc[-1]
    analysis_texts = [f"### {latest['period'].strftime('%Y년 %m월')} 실적 분석 요약"]

    last_year_month = latest['period'].replace(year=latest['period'].year - 1)
    last_year_data = df[df['period'] == last_year_month]
    
    if not last_year_data.empty:
        ly_data = last_year_data.iloc[0]
        reception_diff = latest.get('접수', 0) - ly_data.get('접수', 0)
        success_rate_diff = (latest.get('성공율', 0) - ly_data.get('성공율', 0)) * 100
        
        trend_reception = "증가" if reception_diff > 0 else "감소"
        analysis_texts.append(f"- 전년 동월 대비: 접수 건수는 {abs(reception_diff):,.0f}건 {trend_reception}하였으며, 성공률은 {success_rate_diff:+.1f}%p 변동을 보였습니다.")

    if crm_df is not None and all(c in crm_df.columns for c in ['성공여부', '연령대', '성별']):
        group_stats = crm_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean()).sort_values(ascending=False)
        if not group_stats.empty:
            best_group = group_stats.index[0]
            analysis_texts.append(f"- 고객 세분화 분석: {best_group[0]} {best_group} 고객군의 성공률이 {group_stats.iloc[0]:.1%}로 가장 높게 나타났습니다. 해당 타겟 중심의 마케팅 전략 수립을 권장합니다.")

    return "\n\n".join(analysis_texts)

# --- 대시보드 UI ---
st.set_page_config(layout="wide", page_title="매출 및 CRM 대시보드")
st.title("매출 지표 통합 대시보드")

st.sidebar.header("데이터 업로드")
sales_file = st.sidebar.file_uploader("1. 매출 데이터 (필수)", type=["xlsx", "xls"])
crm_file = st.sidebar.file_uploader("2. CRM 데이터 (선택)", type=["xlsx", "xls"])

if sales_file:
    df = parse_sales_data(sales_file)
    crm_df = parse_crm_data(crm_file) if crm_file else None

    if df is not None and not df.empty:
        st.sidebar.success("데이터 분석이 완료되었습니다.")
        latest_data = df.iloc[-1]
        prev_data = df.iloc[-2] if len(df) > 1 else None

        st.subheader(f"{latest_data['period'].strftime('%Y년 %m월')} 핵심 성과 지표 (KPI)")
        kpi_cols = st.columns(4)
        for col, metric in zip(kpi_cols, ['접수', '컨택', '성공', '성공율']):
            if metric in df.columns:
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
            if '성공율' in df.columns:
                best_month = df.loc[df['성공율'].idxmax()]
                st.info(f"최고 효율 기록월: {best_month['period'].strftime('%Y년 %m월')} (성공율 {best_month['성공율']:.1%})")

        with col2:
            if '설치완료' in df.columns:
                st.subheader("설치 완료 건수 추이")
                start_d, end_d = df['period'].min().to_pydatetime(), df['period'].max().to_pydatetime()
                
                chart_type = st.radio("그래프 형태 선택", ["막대 그래프", "꺾은선형 그래프"], horizontal=True)
                date_range = st.date_input("조회 기간 설정", value=(start_d, end_d), min_value=start_d, max_value=end_d)
                
                if isinstance(date_range, tuple) and len(date_range) == 2:
                    start_p, end_p = pd.to_datetime(date_range[0]), pd.to_datetime(date_range)
                    chart_df = df[(df['period'] >= start_p) & (df['period'] <= end_p)].copy()
                    
                    if not chart_df.empty:
                        chart_df['조회월'] = chart_df['period'].dt.strftime('%y-%m')
                        
                        # 인덱스 중복 오류 방지를 위한 그룹화 합산
                        chart_data = chart_df.groupby('조회월')['설치완료'].sum()
                        
                        if chart_type == "막대 그래프":
                            st.bar_chart(chart_data)
                        else:
                            st.line_chart(chart_data)
        
        with st.expander("원본 데이터 테이블 보기"): 
            st.dataframe(df)
    else:
        st.error("데이터를 화면에 표시할 수 없습니다. 파일의 구조를 다시 확인해주십시오.")
