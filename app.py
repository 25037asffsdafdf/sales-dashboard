import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io

# --- 데이터 파싱 로직 (고도화 버전) ---
def parse_sales_data(uploaded_file):
    """
    업로드된 엑셀 파일의 구조를 지능적으로 분석하여 데이터를 추출합니다.
    - '구분' 텍스트를 기준으로 테이블의 시작점을 동적으로 탐색합니다.
    - 파일 내 여러 테이블을 자동으로 감지하고 병합합니다.
    - 다양한 데이터 형식(%, 숫자, 문자) 오류를 예방합니다.
    """
    try:
        # 파일을 바이트로 읽어 Pandas로 로드
        xls_content = uploaded_file.getvalue()
        df_raw = pd.read_excel(io.BytesIO(xls_content), header=None, sheet_name=0)

        # '구분'이라는 텍스트가 포함된 행의 인덱스를 모두 찾음
        header_indices = df_raw[df_raw[0].astype(str).str.contains('구분', na=False)].index.tolist()

        if not header_indices:
            st.error("엑셀 파일에서 '구분'을 포함한 행을 찾을 수 없습니다. 데이터 구조를 확인해주세요.")
            return None

        all_data_frames = []
        for i, start_row in enumerate(header_indices):
            # 현재 '구분' 행부터 다음 '구분' 행 전까지, 혹은 파일 끝까지를 하나의 테이블로 간주
            end_row = header_indices[i+1] if i + 1 < len(header_indices) else len(df_raw)
            table_df = df_raw.iloc[start_row:end_row].copy()
            
            # 테이블 정리
            table_df = table_df.dropna(how='all', axis=1).dropna(how='all', axis=0) # 전부 빈 행/열 제거
            headers = table_df.iloc[0].astype(str).str.strip().str.replace(r'[.\s]', '', regex=True)
            data = table_df.iloc[1:]
            data.columns = headers
            
            # 데이터를 세로로 긴 형태로 변환 (Melt)
            melted_df = data.melt(
                id_vars=[headers[0]],
                var_name='period_str',
                value_name='value'
            ).rename(columns={headers[0]: 'metric'})
            
            all_data_frames.append(melted_df)

        # 모든 테이블 병합
        combined_df = pd.concat(all_data_frames, ignore_index=True)

        # 데이터 정리 및 형식 변환
        combined_df['metric'] = combined_df['metric'].astype(str).str.strip().str.replace(r'\s', '', regex=True)
        combined_df['period_str'] = combined_df['period_str'].str.replace('월', '', regex=False)
        combined_df = combined_df.dropna(subset=['value'])
        
        # 피벗 테이블로 최종 구조 생성
        final_df = combined_df.pivot_table(index='period_str', columns='metric', values='value', aggfunc='first').reset_index()
        final_df.columns.name = None
        final_df = final_df.rename_axis(None, axis=1)

        # 'period' 컬럼을 datetime 형식으로 변환
        final_df['period'] = pd.to_datetime(final_df['period_str'], format='%y%m', errors='coerce')
        final_df = final_df.dropna(subset=['period']) # 날짜 변환 실패한 행 제거
        
        # 숫자 및 성공률 컬럼 처리
        for col in ['접수', '컨택', '성공', '설치완료']:
            if col in final_df.columns:
                final_df[col] = pd.to_numeric(final_df[col], errors='coerce')

        success_rate_col = next((c for c in ['접수比성공율', '접수비성공율', '성공율'] if c in final_df.columns), None)
        if success_rate_col:
            final_df['성공율'] = final_df[success_rate_col].astype(str).str.replace('%', '', regex=False)
            final_df['성공율'] = pd.to_numeric(final_df['성공율'], errors='coerce') / 100.0
        elif '성공' in final_df.columns and '접수' in final_df.columns:
             final_df['성공율'] = (final_df['성공'] / final_df['접수']).fillna(0)
        
        # 불필요한 열 제거 및 정렬
        cols_to_keep = ['period', '접수', '컨택', '성공', '성공율', '설치완료']
        final_df = final_df[[c for c in cols_to_keep if c in final_df.columns]]
        final_df = final_df.sort_values('period').reset_index(drop=True)
        
        return final_df

    except Exception as e:
        st.error(f"데이터 처리 중 예상치 못한 오류가 발생했습니다: {e}")
        st.warning("업로드한 엑셀 파일의 첫 열에는 '구분', '접수', '컨택' 등이, 첫 행에는 '25.1월' 과 같은 날짜 형식이 있는지 확인해주세요.")
        return None


def parse_crm_data(uploaded_file):
    """CRM 데이터를 정제하고 연령대와 나이를 계산합니다."""
    try:
        crm_df = pd.read_excel(uploaded_file)
        crm_df.columns = [col.strip().replace(" ", "") for col in crm_df.columns]
        
        if '생년월일' in crm_df.columns:
            crm_df['생년월일'] = pd.to_datetime(crm_df['생년월일'], errors='coerce')
            crm_df = crm_df.dropna(subset=['생년월일']) # 날짜 오류 데이터 제거
            current_year = datetime.now().year
            crm_df['나이'] = current_year - crm_df['생년월일'].dt.year
            crm_df['연령대'] = (crm_df['나이'] // 10 * 10).astype(int).astype(str) + '대'
            
        for col in ['성별', '성공여부']:
            if col in crm_df.columns:
                crm_df[col] = crm_df[col].astype(str).str.strip()
                
        return crm_df
    except Exception as e:
        st.error(f"CRM 데이터 처리 오류: {e}")
        return None

def generate_ai_analysis(df, crm_df=None):
    if df is None or df.empty:
        return "분석할 데이터가 없습니다."

    latest = df.iloc[-1]
    analysis_texts = []

    analysis_texts.append(f"### 📅 {latest['period'].strftime('%Y년 %m월')} AI 브리핑")

    # 전년 동월 비교
    last_year_month = latest['period'].replace(year=latest['period'].year - 1)
    last_year_data = df[df['period'] == last_year_month]
    if not last_year_data.empty:
        ly_data = last_year_data.iloc[0]
        reception_diff = latest.get('접수', 0) - ly_data.get('접수', 0)
        success_rate_diff = (latest.get('성공율', 0) - ly_data.get('성공율', 0)) * 100
        analysis_texts.append(
            f"• **전년 동월 비교**: 접수 건수는 **{reception_diff:,.0f}건** {'증가📈' if reception_diff > 0 else '감소📉'}했으며, 성공률은 **{success_rate_diff:+.1f}%p** 변화했습니다."
        )

    # CRM 연계 분석
    if crm_df is not None and '성공여부' in crm_df.columns and '연령대' in crm_df.columns and '성별' in crm_df.columns:
        group_stats = crm_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean()).sort_values(ascending=False)
        if not group_stats.empty:
            best_group = group_stats.index[0]
            best_rate = group_stats.iloc[0]
            best_group_name = f"{best_group[0]} {best_group[1]}"
            analysis_texts.append(
                f"• **핵심 고객 페르소나**: CRM 분석 결과, **{best_group_name}** 그룹이 **{best_rate:.1%}**의 가장 높은 성공률을 보였습니다. 이들을 타겟으로 한 마케팅 전략이 유효할 것으로 판단됩니다."
            )

    # 종합 인사이트
    analysis_texts.append("• **AI 인사이트**: 데이터의 월별 변동성을 볼 때, 특정 계절성 요인이나 마케팅 이벤트와의 연관성을 분석하면 더 정확한 성과 예측이 가능합니다. '설치완료'와 '성공' 지표 간의 차이가 큰 달은 설치 지연 문제를 점검할 필요가 있습니다.")
    
    return "\n\n".join(analysis_texts)


# --- Streamlit UI ---
st.set_page_config(layout="wide", page_title="매출 분석 대시보드")
st.title("📊 매출 지표 및 CRM 분석 대시보드")

# 사이드바
st.sidebar.header("📁 데이터 업로드")
sales_file = st.sidebar.file_uploader("1. 매출 데이터 엑셀", type=["xlsx", "xls"])
crm_file = st.sidebar.file_uploader("2. CRM 데이터 엑셀 (선택)", type=["xlsx", "xls"])

if sales_file:
    df = parse_sales_data(sales_file)
    crm_df = parse_crm_data(crm_file) if crm_file else None

    if df is not None:
        st.sidebar.success("✅ 데이터 로드 및 분석 완료!")

        latest_data = df.iloc[-1]
        prev_data = df.iloc[-2] if len(df) > 1 else None

        # KPI
        st.subheader(f"📍 {latest_data['period'].strftime('%Y년 %m월')} 핵심 성과 (전월 대비)")
        kpi_cols = st.columns(4)
        metrics = {'접수': '건', '컨택': '건', '성공': '건', '성공율': '%p'}
        for col, (metric_name, unit) in zip(kpi_cols, metrics.items()):
            if metric_name in df.columns:
                value = latest_data.get(metric_name, 0)
                delta = value - prev_data.get(metric_name, 0) if prev_data is not None else 0
                if unit == '%p':
                    col.metric(f"{metric_name}", f"{value:.1%}", f"{delta*100:+.1f}{unit}")
                else:
                    col.metric(f"{metric_name}", f"{value:,.0f}{unit}", f"{delta:+.0f}{unit}")
        st.markdown("---")

        # 메인 레이아웃
        col1, col2 = st.columns([4, 6])
        with col1:
            st.subheader("💡 AI 분석 리포트")
            st.markdown(generate_ai_analysis(df, crm_df))
            best_month = df.loc[df['성공율'].idxmax()]
            st.info(f"🏆 **역대 최고 성공률**: **{best_month['period'].strftime('%y년 %m월')}** ({best_month['성공율']:.1%})")

        with col2:
            st.subheader("📈 설치 완료 건수 추이")
            use_total_period = st.toggle('전체 기간 그래프 보기', value=True)
            
            start_d, end_d = df['period'].min().to_pydatetime(), df['period'].max().to_pydatetime()
            if use_total_period:
                date_range = (start_d, end_d)
            else:
                date_range = st.date_input("기간 선택", value=(start_d, end_d), min_value=start_d, max_value=end_d, format="YYYY.MM")
            
            start_p, end_p = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
            chart_df = df[(df['period'] >= start_p) & (df['period'] <= end_p)].copy()
            
            if not chart_df.empty:
                chart_df['월'] = chart_df['period'].dt.strftime('%y-%m')
                st.bar_chart(chart_df.set_index('월')['설치완료'])
            else:
                st.warning("선택된 기간에 데이터가 없습니다.")

        with st.expander("📄 처리된 전체 데이터 보기"):
            st.dataframe(df.style.format({'성공율': '{:.2%}'}))
    else:
        st.error("매출 데이터 처리에 실패했습니다. 파일을 확인 후 다시 업로드해주세요.")
else:
    st.info("👈 사이드바에서 매출 데이터 엑셀 파일을 업로드하면 대시보드가 실행됩니다.")
