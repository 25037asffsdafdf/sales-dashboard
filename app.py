import streamlit as st
import pandas as pd
from datetime import datetime
import re
import traceback

# --- 100% 무결성 확보: 개별 셀 단위 핀포인트 파싱 로직 ---
def parse_sales_data(uploaded_file):
    try:
        # 모든 빈칸을 빈 문자열로 처리하여 통째로 로드 (결측치 충돌 원천 차단)
        df_raw = pd.read_excel(uploaded_file, header=None)
        df_raw = df_raw.fillna("")

        header_row = -1
        header_col = -1
        
        # 1. '구분' 셀의 정확한 X, Y 좌표 탐색 (전체 셀 전수조사)
        for r in range(len(df_raw)):
            for c in range(len(df_raw.columns)):
                # 단일 셀 단위로 문자로 변환하므로 float 에러가 발생할 수 없음
                cell_val = str(df_raw.iat[r, c]).replace(" ", "").replace("\n", "")
                if "구분" in cell_val:
                    header_row = r
                    header_col = c
                    break
            if header_row != -1:
                break
                
        if header_row == -1:
            st.error("엑셀 파일에서 '구분' 항목을 찾을 수 없습니다. 표의 최상단 좌측에 '구분'이 있는지 확인해주십시오.")
            return None

        # 2. 좌표를 기준으로 날짜(기간) 데이터만 정밀 추출
        parsed_dates = {}
        for c in range(header_col + 1, len(df_raw.columns)):
            date_val = df_raw.iat[header_row, c]
            if str(date_val) == "": 
                continue
            
            dt = None
            if isinstance(date_val, datetime):
                dt = date_val
            elif isinstance(date_val, (int, float)):
                # 엑셀 고유 일련번호(날짜) 데이터일 경우
                if 40000 <= date_val <= 60000:
                    dt = pd.to_datetime(date_val, unit='D', origin='1899-12-30')
            else:
                # 텍스트 형태(예: 25.1월)일 경우 숫자만 추출
                d_str = str(date_val).replace(" ", "")
                nums = re.findall(r'\d+', d_str)
                if len(nums) >= 2:
                    yy, mm = int(nums[0]), int(nums)
                    if yy < 100: yy += 2000
                    if 1 <= mm <= 12:
                        dt = datetime(yy, mm, 1)
                elif len(nums) == 1:
                    mm = int(nums[0])
                    if 1 <= mm <= 12:
                        dt = datetime(datetime.now().year, mm, 1)
            
            if dt:
                parsed_dates[c] = dt.strftime('%Y-%m-%d')
                
        if not parsed_dates:
            st.error("'구분' 우측열에 위치한 날짜 데이터(예: 25.1월 등)를 인식하지 못했습니다.")
            return None

        melted_rows = []
        
        # 3. Y좌표를 따라 아래로 내려가며 지표 및 수치 매핑
        for r in range(header_row + 1, len(df_raw)):
            metric_raw = str(df_raw.iat[r, header_col]).replace(" ", "").replace("\n", "")
            if not metric_raw: 
                continue
            
            # 지표명 자동 규격화
            if '성공' in metric_raw and ('율' in metric_raw or '비' in metric_raw or '比' in metric_raw): 
                metric = '성공율'
            elif '설치' in metric_raw: metric = '설치완료'
            elif '성공' in metric_raw: metric = '성공'
            elif '컨택' in metric_raw or '콜' in metric_raw: metric = '컨택'
            elif '접수' in metric_raw: metric = '접수'
            else: metric = metric_raw

            for c, period_str in parsed_dates.items():
                val_raw = str(df_raw.iat[r, c]).replace(",", "").strip()
                if not val_raw:
                    val = 0.0
                else:
                    # 마이너스(-)와 소수점(.)을 제외한 모든 문자 제거 후 숫자 변환
                    v_num = re.sub(r'[^\d.-]', '', val_raw)
                    try:
                        val = float(v_num) if v_num and v_num != '-' else 0.0
                    except:
                        val = 0.0
                
                melted_rows.append({'period': period_str, 'metric': metric, 'value': val})

        if not melted_rows:
            st.error("분석 가능한 수치 데이터를 추출하지 못했습니다.")
            return None
            
        # 4. 데이터 조립 및 누락된 지표 강제 보정
        df_long = pd.DataFrame(melted_rows)
        # 중복 방지 처리
        df_long = df_long.drop_duplicates(subset=['period', 'metric'])
        df_pivot = df_long.pivot(index='period', columns='metric', values='value').reset_index()
        
        for req_col in ['접수', '컨택', '성공', '성공율', '설치완료']:
            if req_col not in df_pivot.columns:
                df_pivot[req_col] = 0.0
                
        df_pivot['period'] = pd.to_datetime(df_pivot['period'])
        df_pivot = df_pivot.sort_values('period').reset_index(drop=True)
        
        # 성공율 소수점 단위 통일 및 재계산
        for i, row in df_pivot.iterrows():
            rate = row['성공율']
            if rate > 1.0:
                df_pivot.at[i, '성공율'] = rate / 100.0
            elif rate == 0.0 and row['접수'] > 0:
                df_pivot.at[i, '성공율'] = row['성공'] / row['접수']
                
        return df_pivot
        
    except Exception as e:
        # 혹시 모를 에러 발생 시 원인을 즉시 파악할 수 있도록 시스템 로그를 표출합니다.
        st.error(f"시스템 데이터 처리 중 오류가 발생했습니다: {e}")
        st.code(traceback.format_exc())
        return None

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

# --- 대시보드 UI 구성 ---
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
            
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_p, end_p = pd.to_datetime(date_range[0]), pd.to_datetime(date_range)
                chart_df = df[(df['period'] >= start_p) & (df['period'] <= end_p)].copy()
                
                if not chart_df.empty:
                    chart_df['조회월'] = chart_df['period'].dt.strftime('%y-%m')
                    # Streamlit 중복 인덱스 에러 방지를 위해 groupby 활용
                    chart_data = chart_df.groupby('조회월')['설치완료'].sum()
                    
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
        st.error("데이터를 처리할 수 없습니다. 업로드한 파일의 양식을 확인해주십시오.")
else:
    st.info("좌측 사이드바에서 매출 데이터 파일을 업로드하면 대시보드가 실행됩니다.")
