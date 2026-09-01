import streamlit as st
import pandas as pd
from datetime import datetime

# --- 데이터 파싱 로직 ---
def parse_sales_data(uploaded_file):
    try:
        # 헤더 없이 원본 데이터 전체 로드
        df_raw = pd.read_excel(uploaded_file, header=None)
        
        target_row_indices = []
        # 한 줄씩 읽으며 '구분' 텍스트가 있는 행 번호 추출
        for idx, row in df_raw.iterrows():
            row_str = row.astype(str).str.replace(r'\s+', '', regex=True)
            if any(row_str == '구분'):
                target_row_indices.append(idx)
                
        if not target_row_indices:
            st.error("데이터 인식 실패: 파일 내에 '구분' 항목을 찾을 수 없습니다.")
            return None
            
        all_melted = []
        for i, start_idx in enumerate(target_row_indices):
            end_idx = target_row_indices[i+1] if i+1 < len(target_row_indices) else len(df_raw)
            block = df_raw.iloc[start_idx:end_idx].copy()
            
            # 첫 번째 행을 헤더로 지정
            headers = block.iloc[0].astype(str).str.replace(r'\s+', '', regex=True).tolist()
            data = block.iloc[1:]
            data.columns = headers
            
            if '구분' not in data.columns:
                continue
                
            # 유효한 열만 추출 (빈 값 제외)
            valid_cols = [c for c in data.columns if c not in ('nan', 'None', '')]
            data = data[valid_cols].copy()
            
            # 가로로 나열된 월별 데이터를 세로형 구조로 변환
            melted = data.melt(id_vars=['구분'], var_name='period_str', value_name='value')
            all_melted.append(melted)
            
        if not all_melted:
            st.error("데이터 추출 실패: 유효한 데이터 영역을 찾지 못했습니다.")
            return None
            
        # 다중 테이블 병합 및 정제
        combined_df = pd.concat(all_melted, ignore_index=True)
        combined_df = combined_df.rename(columns={'구분': 'metric'})
        combined_df = combined_df.dropna(subset=['metric', 'value'])
        combined_df['metric'] = combined_df['metric'].astype(str).str.replace(r'\s+', '', regex=True)
        
        # 월별 표기 텍스트 보정 (예: 25.1 -> 2501)
        def clean_period(p):
            p = str(p).replace('월', '').replace('.', '').replace('년', '').strip()
            if len(p) == 3: 
                return p[:2] + '0' + p[2:]
            return p
            
        combined_df['period_str'] = combined_df['period_str'].apply(clean_period)
        
        # 지표별 피벗 테이블 생성
        final_df = combined_df.pivot_table(index='period_str', columns='metric', values='value', aggfunc='first').reset_index()
        final_df.columns.name = None
        
        # 날짜 형식 변환
        final_df['period'] = pd.to_datetime(final_df['period_str'], format='%y%m', errors='coerce')
        final_df = final_df.dropna(subset=['period'])
        
        # 숫자 데이터 타입 변환
        metrics_to_check = ['접수', '컨택', '성공', '설치완료', '접수比성공율', '접수비성공율', '성공율']
        for col in metrics_to_check:
            if col in final_df.columns:
                final_df[col] = final_df[col].astype(str).replace(r'[^\d.]', '', regex=True)
                final_df[col] = pd.to_numeric(final_df[col], errors='coerce')

        # 성공율 소수점 보정
        success_col = next((c for c in ['접수比성공율', '접수비성공율', '성공율'] if c in final_df.columns), None)
        if success_col:
            final_df['성공율'] = final_df[success_col]
            final_df.loc[final_df['성공율'] > 1.0, '성공율'] = final_df['성공율'] / 100.0
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
                
                # 그래프 형태 선택 기능 추가
                chart_type = st.radio("그래프 형태 선택", ["막대그래프", "꺾은선형그래프"], horizontal=True)
                date_range = st.date_input("조회 기간 설정", value=(start_d, end_d), min_value=start_d, max_value=end_d)
                
                if isinstance(date_range, tuple) and len(date_range) == 2:
                    start_p, end_p = pd.to_datetime(date_range[0]), pd.to_datetime(date_range)
                    chart_df = df[(df['period'] >= start_p) & (df['period'] <= end_p)].copy()
                    
                    if not chart_df.empty:
                        chart_df['조회월'] = chart_df['period'].dt.strftime('%y-%m')
                        chart_data = chart_df.set_index('조회월')['설치완료']
                        
                        # 선택된 형태에 따라 차트 출력
                        if chart_type == "막대그래프":
                            st.bar_chart(chart_data)
                        else:
                            st.line_chart(chart_data)
        
        with st.expander("원본 데이터 테이블 보기"): 
            st.dataframe(df)
    else:
        st.error("데이터를 화면에 표시할 수 없습니다. 파일의 구조를 다시 확인해주십시오.")
