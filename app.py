import streamlit as st
import pandas as pd
from datetime import datetime
import re
import traceback

def clean_metric_name(name):
    """지표명을 시스템 표준 포맷으로 통일"""
    name = str(name).replace(" ", "")
    if "성공율" in name or "성공률" in name or "대비성공" in name: return "성공율"
    if "설치" in name: return "설치완료"
    if "성공" in name: return "성공"
    if "컨택" in name or "콜" in name: return "컨택"
    if "접수" in name: return "접수"
    return name

def parse_sales_data(uploaded_file):
    """다중 테이블(연도별 표)을 모두 스캔하여 병합하는 로직"""
    try:
        df_raw = pd.read_excel(uploaded_file, header=None)
        all_data = []
        
        # 파일 내 모든 '구분' 행 인덱스 추출 (2025년, 2026년 등 표가 여러 개일 경우 모두 인식)
        header_rows = df_raw[df_raw[0].astype(str).str.replace(" ", "") == "구분"].index.tolist()
        
        if not header_rows:
            st.error("엑셀 파일 내에 '구분' 항목을 찾을 수 없습니다.")
            return None
            
        for i, h_idx in enumerate(header_rows):
            # 현재 표의 끝을 다음 '구분' 행 이전 또는 파일 끝으로 설정
            end_idx = header_rows[i+1] if i + 1 < len(header_rows) else len(df_raw)
            block = df_raw.iloc[h_idx:end_idx].dropna(how='all')
            
            headers = block.iloc[0]
            for _, row in block.iloc[1:].iterrows():
                metric = clean_metric_name(row[0])
                if metric not in ['접수', '컨택', '성공', '성공율', '설치완료']:
                    continue
                    
                for col_idx in range(1, len(headers)):
                    col_name = str(headers[col_idx]).replace(" ", "").split(".")[0]
                    period = None
                    
                    # '202501' 형식 또는 '2025년1월' 형식 완벽 대응
                    if re.match(r'^20\d{4}$', col_name):
                        period = pd.to_datetime(col_name, format='%Y%m')
                    elif "년" in col_name and "월" in col_name:
                        nums = re.findall(r'\d+', col_name)
                        if len(nums) >= 2:
                            period = pd.to_datetime(f"{nums[0]}{int(nums):02d}", format='%Y%m')
                    
                    if period:
                        val = row[col_idx]
                        # 공란이 아닌 유효한 숫자 데이터만 추출
                        if pd.notna(val) and str(val).strip() != '':
                            try:
                                val_float = float(str(val).replace(",", ""))
                                all_data.append({'period': period, 'metric': metric, 'value': val_float})
                            except ValueError:
                                pass
                                
        if not all_data:
            st.error("유효한 수치 데이터를 추출하지 못했습니다. 날짜 형식을 확인해주십시오.")
            return None
            
        df_long = pd.DataFrame(all_data)
        
        # 중복 데이터 발생 시 마지막 값 우선 반영
        df_long = df_long.groupby(['period', 'metric'], as_index=False)['value'].last()
        df_pivot = df_long.pivot(index='period', columns='metric', values='value').reset_index()
        
        # 누락된 지표 강제 생성 (KeyError 방지)
        for m in ['접수', '컨택', '성공', '성공율', '설치완료']:
            if m not in df_pivot.columns:
                df_pivot[m] = 0.0
                
        df_pivot = df_pivot.sort_values('period').reset_index(drop=True)
        
        # 성공율 시스템 재계산 (엑셀의 % 서식과 일반 숫자 서식 혼용 문제 해결)
        for idx, row in df_pivot.iterrows():
            if row['접수'] > 0:
                df_pivot.at[idx, '성공율'] = row['성공'] / row['접수']
            else:
                df_pivot.at[idx, '성공율'] = 0.0
                
        return df_pivot
        
    except Exception as e:
        st.error(f"데이터 전처리 중 시스템 오류가 발생했습니다: {str(e)}")
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
    except Exception:
        return None

def generate_ai_analysis(df, selected_period, crm_df=None):
    if df is None or df.empty: 
        return "분석 리포트를 생성할 수 있는 데이터가 없습니다."
        
    current_data = df[df['period'] == selected_period]
    if current_data.empty:
        return "해당 월의 데이터가 존재하지 않습니다."
        
    latest = current_data.iloc[0]
    analysis_texts = [f"### {latest['period'].strftime('%Y년 %m월')} 성과 분석 요약"]
    
    last_year_dt = latest['period'].replace(year=latest['period'].year - 1)
    ly_data = df[df['period'] == last_year_dt]
    
    if not ly_data.empty:
        ly = ly_data.iloc[0]
        rec_diff = latest['접수'] - ly['접수']
        rate_diff = (latest['성공율'] - ly['성공율']) * 100
        
        trend_rec = "증가" if rec_diff > 0 else "감소"
        analysis_texts.append(
            f"- 전년 동월 대비 성과: 접수 건수는 {abs(rec_diff):,.0f}건 {trend_rec}하였으며, "
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
                    f"- 주요 타겟 고객층: CRM 교차 분석 결과, {best[0]} {best} 고객군의 성공율이 {best_rate:.1%}로 "
                    f"가장 높게 측정되었습니다. 향후 마케팅 시 해당 타겟에 자원을 우선 배정할 것을 권장합니다."
                )
        except Exception:
            pass
            
    return "\n\n".join(analysis_texts)

# --- 대시보드 UI ---
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
        
        # 월 선택 기능 추가 (가장 최근 실적이 있는 월이 기본값)
        valid_periods = df[df['접수'] > 0]['period']
        default_period = valid_periods.max() if not valid_periods.empty else df['period'].max()
        
        period_options = df['period'].dt.strftime('%Y년 %m월').tolist()
        period_options.reverse() # 최신순 정렬
        default_index = period_options.index(default_period.strftime('%Y년 %m월')) if default_period else 0
        
        selected_month_str = st.selectbox("조회 기준월 설정", options=period_options, index=default_index)
        selected_period = pd.to_datetime(selected_month_str, format='%Y년 %m월')
        
        latest_data = df[df['period'] == selected_period].iloc[0]
        
        # 전월 데이터 추출
        prev_period = selected_period - pd.DateOffset(months=1)
        prev_data_df = df[df['period'] == prev_period]
        prev_data = prev_data_df.iloc[0] if not prev_data_df.empty else None
        
        st.subheader(f"{latest_data['period'].strftime('%Y년 %m월')} 핵심 성과 지표 (전월 대비)")
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
            st.markdown(generate_ai_analysis(df, selected_period, crm_df))
            
            st.markdown("<br><b>연도별 최고 실적 현황 (성공율 기준)</b>", unsafe_allow_html=True)
            df['year'] = df['period'].dt.year
            df_valid_success = df[df['성공율'] > 0]
            if not df_valid_success.empty:
                best_per_year = df_valid_success.loc[df_valid_success.groupby('year')['성공율'].idxmax()]
                
                year_cols = st.columns(len(best_per_year))
                for y_col, (_, row) in zip(year_cols, best_per_year.iterrows()):
                    y_col.caption(f"{row['year']}년 최고 실적\n\n{row['period'].strftime('%m월')} (성공율 {row['성공율']:.1%})")

        with col2:
            st.subheader("설치 완료 건수 트렌드")
            start_d = df['period'].min().date()
            end_d = df['period'].max().date()
            
            chart_type = st.radio("그래프 형태 선택", ["막대 그래프", "꺾은선형 그래프"], horizontal=True)
            date_range = st.date_input("조회 기간 설정", value=(start_d, end_d), min_value=start_d, max_value=end_d)
            
            # Lengths must match 오류 방지를 위한 정확한 인덱싱 처리
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
                    st.warning("선택하신 기간 내에 유효한 데이터가 존재하지 않습니다.")
            else:
                st.info("시작일과 종료일을 모두 지정해주십시오.")
        
        with st.expander("데이터 원본 확인"): 
            st.dataframe(df.drop(columns=['year']).style.format({
                "성공율": "{:.2%}", "접수": "{:.0f}", "컨택": "{:.0f}", "성공": "{:.0f}", "설치완료": "{:.0f}"
            }))
            
else:
    st.info("좌측 메뉴에서 데이터를 업로드하여 대시보드를 활성화해주십시오.")
