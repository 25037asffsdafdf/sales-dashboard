import streamlit as st
import pandas as pd
from datetime import datetime
import re

# --- 절대 무결성 데이터 파싱 로직 ---
def parse_sales_data(uploaded_file):
    try:
        df_raw = pd.read_excel(uploaded_file, header=None)
        
        # 1. '구분' 행 찾기
        header_idx = -1
        for idx, row in df_raw.iterrows():
            row_str = "".join(row.astype(str)).replace(" ", "")
            if '구분' in row_str:
                header_idx = idx
                break
                
        if header_idx == -1:
            st.error("엑셀 파일에서 '구분'이 포함된 행을 찾을 수 없습니다. 양식을 확인해주십시오.")
            return None
            
        # 2. 데이터 블록 추출
        df_table = df_raw.iloc[header_idx:].dropna(how='all').reset_index(drop=True)
        headers = df_table.iloc[0].astype(str).tolist()
        df_data = df_table.iloc[1:]
        
        melted_rows = []
        
        # 3. 셀 단위 정밀 추출 및 명칭 강제 표준화
        for _, row in df_data.iterrows():
            metric_raw = str(row.iloc[0]).replace(" ", "")
            if not metric_raw or metric_raw == 'nan':
                continue
                
            # 범용 지표명 매핑
            if '성공' in metric_raw and ('율' in metric_raw or '비' in metric_raw or '比' in metric_raw): 
                metric = '성공율'
            elif '설치' in metric_raw: metric = '설치완료'
            elif '성공' in metric_raw: metric = '성공'
            elif '컨택' in metric_raw or '콜' in metric_raw: metric = '컨택'
            elif '접수' in metric_raw: metric = '접수'
            else: metric = metric_raw
            
            # 열 단위로 날짜와 값 추출
            for col_idx in range(1, len(headers)):
                date_raw = str(headers[col_idx])
                nums = re.findall(r'\d+', date_raw)
                
                # 날짜 형식이 숫자로 2개 이상(연, 월) 존재할 경우
                if len(nums) >= 2:
                    yy, mm = int(nums[0]), int(nums)
                    yy = yy + 2000 if yy < 100 else yy
                    
                    if 1 <= mm <= 12:
                        period_str = f"{yy:04d}-{mm:02d}-01"
                        val_raw = str(row.iloc[col_idx]).strip()
                        
                        # 문자열 내 숫자, 소수점, 마이너스 기호만 추출
                        v_num = re.sub(r'[^\d.-]', '', val_raw)
                        try:
                            val = float(v_num) if v_num else 0.0
                        except:
                            val = 0.0
                            
                        melted_rows.append({'period': period_str, 'metric': metric, 'value': val})
                        
        if not melted_rows:
            st.error("분석 가능한 유효 데이터(날짜 및 수치)를 추출하지 못했습니다.")
            return None
            
        # 4. 데이터프레임 변환 및 피벗 (중복값은 첫번째 값 우선)
        df_long = pd.DataFrame(melted_rows)
        df_pivot = df_long.pivot_table(index='period', columns='metric', values='value', aggfunc='first').reset_index()
        
        # 5. 필수 열 누락 방지 (KeyError 원천 차단)
        essential_cols = ['접수', '컨택', '성공', '성공율', '설치완료']
        for c in essential_cols:
            if c not in df_pivot.columns:
                df_pivot[c] = 0.0
                
        # 6. 날짜 변환 및 정렬
        df_pivot['period'] = pd.to_datetime(df_pivot['period'])
        df_pivot = df_pivot.sort_values('period').reset_index(drop=True)
        
        # 7. 성공율 수치 보정 (1보다 크면 퍼센트로 간주하여 나눗셈, 0일 경우 재계산)
        for i, row in df_pivot.iterrows():
            rate = row['성공율']
            if rate > 1.0:
                df_pivot.at[i, '성공율'] = rate / 100.0
            elif rate == 0.0 and row['접수'] > 0:
                df_pivot.at[i, '성공율'] = row['성공'] / row['접수']
                
        return df_pivot
        
    except Exception as e:
        st.error(f"데이터 파싱 중 심각한 오류가 발생했습니다: {e}")
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
        reception_diff = latest['접수'] - ly_data['접수']
        success_rate_diff = (latest['성공율'] - ly_data['성공율']) * 100
        
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

        st.subheader(f"{latest_data['period'].strftime('%Y년 %m월')} 핵심 성과 지표 (M-1 기준)")
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
            
            # 날짜가 두 개 모두 선택되었을 때만 그래프 렌더링 실행
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_p, end_p = pd.to_datetime(date_range[0]), pd.to_datetime(date_range)
                chart_df = df[(df['period'] >= start_p) & (df['period'] <= end_p)].copy()
                
                if not chart_df.empty:
                    chart_df['조회월'] = chart_df['period'].dt.strftime('%y-%m')
                    chart_data = chart_df.set_index('조회월')['설치완료']
                    
                    if chart_type == "막대 그래프":
                        st.bar_chart(chart_data)
                    else:
                        st.line_chart(chart_data)
                else:
                    st.warning("선택하신 기간 내에 데이터가 존재하지 않습니다.")
            else:
                st.info("종료 날짜를 선택해주십시오.")
        
        with st.expander("원본 데이터 테이블 보기 (시스템 추출본)"): 
            st.dataframe(df)
    else:
        st.error("데이터 처리에 실패했습니다. 파일 양식을 확인해주십시오.")
