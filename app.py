import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
import re

# --- 극한의 예외 처리 데이터 파싱 로직 ---
def parse_sales_data(uploaded_file):
    """
    띄어쓰기, 셀 위치, 병합 등 모든 변수를 무시하고 핵심 데이터를 추출합니다.
    """
    try:
        xls_content = uploaded_file.getvalue()
        df_raw = pd.read_excel(io.BytesIO(xls_content), header=None, sheet_name=0)

        # 1. 엑셀 전체 셀의 모든 공백(띄어쓰기, 줄바꿈) 완벽 제거 및 문자열 변환
        # (예: '구 분', '구  분', '구\n분' -> '구분')
        df_clean = df_raw.applymap(lambda x: re.sub(r'\s+', '', str(x)) if pd.notnull(x) else np.nan)

        # 2. '구분'이라는 단어가 있는 정확한 행 인덱스 탐색
        header_indices = []
        for col in df_clean.columns:
            # 해당 열에서 '구분' 문자열과 완벽히 일치하는 행을 찾음
            indices = df_clean.index[df_clean[col] == '구분'].tolist()
            header_indices.extend(indices)
            
        header_indices = sorted(list(set(header_indices))) # 중복 제거 및 정렬

        if not header_indices:
            st.error("❌ 엑셀 파일 내에서 '구분' 셀을 찾을 수 없습니다. (띄어쓰기 무관)")
            return None

        all_data_frames = []
        for i, start_row in enumerate(header_indices):
            # 다음 테이블의 '구분' 행이 나오기 전까지 잘라냄
            end_row = header_indices[i+1] if i + 1 < len(header_indices) else len(df_clean)
            table_df = df_clean.iloc[start_row:end_row].copy()
            
            # 빈 열/행 모두 제거
            table_df = table_df.dropna(how='all', axis=1).dropna(how='all', axis=0).reset_index(drop=True)
            
            # 헤더(첫 번째 행) 설정
            headers = table_df.iloc[0].tolist()
            data = table_df.iloc[1:]
            
            # 헤더가 중복되거나 빈 값이 있을 수 있으므로 처리
            valid_headers = [h for h in headers if pd.notnull(h) and str(h).strip() != 'nan']
            if len(valid_headers) < 2: continue # 날짜 데이터가 없으면 패스

            # 데이터프레임 재구성 (Melt 활용하여 가로로 긴 데이터를 세로로)
            data.columns = headers
            melted_df = data.melt(
                id_vars=[headers[0]], # 기준 열 (ex: 접수, 컨택 등)
                var_name='period_str', # 날짜 열 (ex: 25.1월)
                value_name='value' # 값 열
            ).rename(columns={headers[0]: 'metric'})
            
            all_data_frames.append(melted_df)

        if not all_data_frames:
            st.error("❌ 데이터 추출에 실패했습니다.")
            return None

        # 3. 데이터 병합 및 정제
        combined_df = pd.concat(all_data_frames, ignore_index=True)
        combined_df = combined_df.dropna(subset=['metric', 'period_str', 'value'])
        
        # 쓸데없는 문자(nan 등) 제거
        combined_df = combined_df[~combined_df['period_str'].astype(str).str.contains('nan', case=False, na=False)]

        # 4. 날짜(period_str) 문자열 정제 (예: 25.1월, 25.01월, 25.1 -> 2501)
        def clean_period(p):
            p = str(p).replace('월', '').replace('.', '').replace('년', '')
            # 251 -> 2501 로 보정 (자릿수가 3자리일 경우)
            if len(p) == 3: return p[:2] + '0' + p[2:]
            return p

        combined_df['period_str'] = combined_df['period_str'].apply(clean_period)

        # 5. 피벗 테이블 (행: 날짜, 열: 지표(metric))
        final_df = combined_df.pivot_table(index='period_str', columns='metric', values='value', aggfunc='first').reset_index()
        final_df.columns.name = None
        
        # 6. 날짜 형식(datetime) 변환
        final_df['period'] = pd.to_datetime(final_df['period_str'], format='%y%m', errors='coerce')
        final_df = final_df.dropna(subset=['period']) # 변환 실패 행 삭제
        
        # 7. 지표 컬럼 숫자형 변환
        metrics_to_check = ['접수', '컨택', '성공', '설치완료', '접수比성공율', '접수비성공율', '성공율']
        for col in metrics_to_check:
            if col in final_df.columns:
                # 숫자 외 문자(예: %, 컴마) 제거
                final_df[col] = final_df[col].astype(str).str.replace(r'[^\d.]', '', regex=True)
                final_df[col] = pd.to_numeric(final_df[col], errors='coerce')

        # 성공율 소수점 처리 (1.0 이상이면 100으로 나눔)
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
        st.error(f"⚠️ 엑셀 분석 중 치명적 오류 발생: {e}")
        return None

# --- 이하 코드는 이전 버전과 동일하게 유지합니다 ---
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
                crm_df[col] = crm_df[col].astype(str).str.replace(r'\s+', '', regex=True)
                
        return crm_df
    except Exception as e:
        st.error(f"CRM 데이터 처리 오류: {e}")
        return None

def generate_ai_analysis(df, crm_df=None):
    if df is None or df.empty: return "분석할 데이터가 없습니다."
    latest = df.iloc[-1]
    analysis_texts = [f"### 📅 {latest['period'].strftime('%Y년 %m월')} AI 브리핑"]

    last_year_month = latest['period'].replace(year=latest['period'].year - 1)
    last_year_data = df[df['period'] == last_year_month]
    if not last_year_data.empty:
        ly_data = last_year_data.iloc[0]
        reception_diff = latest.get('접수', 0) - ly_data.get('접수', 0)
        success_rate_diff = (latest.get('성공율', 0) - ly_data.get('성공율', 0)) * 100
        analysis_texts.append(f"• **전년 대비**: 접수 건수는 **{reception_diff:,.0f}건** {'증가📈' if reception_diff > 0 else '감소📉'}했으며, 성공률은 **{success_rate_diff:+.1f}%p** 변화했습니다.")

    if crm_df is not None and all(c in crm_df.columns for c in ['성공여부', '연령대', '성별']):
        group_stats = crm_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean()).sort_values(ascending=False)
        if not group_stats.empty:
            best_group = group_stats.index[0]
            analysis_texts.append(f"• **핵심 타겟**: **{best_group[0]} {best_group}** 타겟층이 **{group_stats.iloc[0]:.1%}**의 가장 높은 성공률을 보였습니다. 집중 마케팅을 제안합니다.")

    return "\n\n".join(analysis_texts)

# --- UI 렌더링 ---
st.set_page_config(layout="wide", page_title="매출 대시보드")
st.title("📊 매출 지표 통합 대시보드")

st.sidebar.header("📁 엑셀 데이터 업로드")
sales_file = st.sidebar.file_uploader("1. 매출 데이터 (필수)", type=["xlsx", "xls"])
crm_file = st.sidebar.file_uploader("2. CRM 데이터 (선택)", type=["xlsx", "xls"])

if sales_file:
    df = parse_sales_data(sales_file)
    crm_df = parse_crm_data(crm_file) if crm_file else None

    if df is not None and not df.empty:
        st.sidebar.success("✅ 매출 데이터 분석 완료!")
        latest_data = df.iloc[-1]
        prev_data = df.iloc[-2] if len(df) > 1 else None

        st.subheader(f"📍 {latest_data['period'].strftime('%Y년 %m월')} 핵심 성과")
        kpi_cols = st.columns(4)
        for col, metric in zip(kpi_cols, ['접수', '컨택', '성공', '성공율']):
            if metric in df.columns:
                val = latest_data[metric]
                delta = val - prev_data[metric] if prev_data is not None else 0
                if metric == '성공율': col.metric(metric, f"{val:.1%}", f"{delta*100:+.1f}%p")
                else: col.metric(f"{metric} (건)", f"{val:,.0f}", f"{delta:+.0f}")
        
        st.markdown("---")
        col1, col2 = st.columns([4, 6])
        with col1:
            st.subheader("💡 AI 분석 리포트")
            st.markdown(generate_ai_analysis(df, crm_df))
            if '성공율' in df.columns:
                best_month = df.loc[df['성공율'].idxmax()]
                st.info(f"🏆 **역대 최고 효율 달**: {best_month['period'].strftime('%y년 %m월')} ({best_month['성공율']:.1%})")

        with col2:
            if '설치완료' in df.columns:
                st.subheader("📈 설치 완료 건수 추이")
                start_d, end_d = df['period'].min().to_pydatetime(), df['period'].max().to_pydatetime()
                date_range = st.date_input("기간 선택", value=(start_d, end_d), min_value=start_d, max_value=end_d)
                if isinstance(date_range, tuple) and len(date_range) == 2:
                    start_p, end_p = pd.to_datetime(date_range[0]), pd.to_datetime(date_range)
                    chart_df = df[(df['period'] >= start_p) & (df['period'] <= end_p)].copy()
                    if not chart_df.empty:
                        chart_df['월'] = chart_df['period'].dt.strftime('%y-%m')
                        st.bar_chart(chart_df.set_index('월')['설치완료'])
        
        with st.expander("📄 정제된 전체 테이블 보기"): st.dataframe(df)
    else:
        st.error("데이터를 화면에 표시할 수 없습니다. 엑셀 구조를 다시 확인해주세요.")

