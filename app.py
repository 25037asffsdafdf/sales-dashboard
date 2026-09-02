import streamlit as st
import pandas as pd
from datetime import datetime
import re
import traceback
import plotly.express as px

# =====================================================================
# [1단계] 지표명 표준화 함수
# =====================================================================
def standardize_metric_name(raw_name):
    if pd.isna(raw_name): return None
    clean_name = str(raw_name).replace(" ", "").replace("\n", "")
    if not clean_name: return None
    
    if '접수' in clean_name and ('비' in clean_name or '比' in clean_name or '율' in clean_name or '률' in clean_name): return '성공율'
    if '성공' in clean_name and ('율' in clean_name or '률' in clean_name): return '성공율'
    if '설치' in clean_name and '완료' in clean_name: return '설치완료'
    if '성공' in clean_name: return '성공'
    if '컨택' in clean_name or '콜' in clean_name: return '컨택'
    if '접수' in clean_name: return '접수'
    return clean_name

# =====================================================================
# [2단계] 핵심 매출 데이터 파싱
# =====================================================================
def parse_sales_data(uploaded_file):
    try:
        df_raw = pd.read_excel(uploaded_file, header=None)
        df_raw = df_raw.fillna("")

        header_rows = []
        anchor_c = -1
        
        for r in range(len(df_raw)):
            for c in range(len(df_raw.columns)):
                cell_val = str(df_raw.iat[r, c]).replace(" ", "").replace("\n", "")
                if "구분" in cell_val:
                    if r not in header_rows:
                        header_rows.append(r)
                        anchor_c = c
        
        if not header_rows:
            st.error("데이터 인식 실패: 표에서 '구분' 항목을 찾을 수 없습니다. 원본 파일을 확인해주십시오.")
            return None

        records = []
        
        for i, h_idx in enumerate(header_rows):
            end_idx = header_rows[i+1] if i + 1 < len(header_rows) else len(df_raw)
            block = df_raw.iloc[h_idx:end_idx]
            
            dates = {}
            for c in range(anchor_c + 1, len(df_raw.columns)):
                d_val = str(block.iat[0, c]).replace(" ", "").replace(".0", "")
                if not d_val: continue
                
                nums = re.findall(r'\d+', d_val)
                if not nums: continue
                
                num_str = "".join(nums)
                y, m = -1, -1
                
                if len(num_str) >= 6:
                    y = int(num_str[:4])
                    m = int(num_str[4:6])
                elif len(nums) >= 2:
                    y = int(nums[0])
                    m = int(nums)
                
                if y != -1 and m != -1:
                    if y < 100: y += 2000
                    if 2000 <= y <= 2100 and 1 <= m <= 12:
                        dates[c] = pd.Timestamp(y, m, 1)

            for r_idx in range(1, len(block)):
                metric_raw = block.iat[r_idx, anchor_c]
                metric = standardize_metric_name(metric_raw)
                if not metric: continue
                
                for c, dt in dates.items():
                    v_raw = str(block.iat[r_idx, c]).replace(",", "")
                    v_num = re.sub(r'[^\d.-]', '', v_raw)
                    try:
                        val = float(v_num) if v_num and v_num != '-' else 0.0
                    except:
                        val = 0.0
                    records.append({'period': dt, 'metric': metric, 'value': val})

        if not records:
            st.error("데이터 추출 실패: 유효한 날짜 및 수치 데이터를 찾지 못했습니다.")
            return None

        df_long = pd.DataFrame(records)
        df_long = df_long.groupby(['period', 'metric'], as_index=False)['value'].last()
        df_pivot = df_long.pivot(index='period', columns='metric', values='value').reset_index()
        
        for req in ['접수', '컨택', '성공', '성공율', '설치완료']:
            if req not in df_pivot.columns: 
                df_pivot[req] = 0.0
            else:
                df_pivot[req] = pd.to_numeric(df_pivot[req], errors='coerce').fillna(0.0)
                
        df_pivot = df_pivot.sort_values('period').reset_index(drop=True)
        
        df_pivot['성공율'] = df_pivot.apply(
            lambda row: row['성공'] / row['접수'] if row.get('접수', 0) > 0 else 0.0, axis=1
        )
        
        return df_pivot
        
    except Exception as e:
        st.error(f"시스템 오류 발생: {e}")
        st.code(traceback.format_exc())
        return None

# =====================================================================
# [3단계] CRM 데이터 및 종합 분석 리포트 (전월 대비로 로직 변경)
# =====================================================================
def parse_crm_data(uploaded_file):
    try:
        crm_df = pd.read_excel(uploaded_file)
        crm_df.columns = [str(col).replace(" ", "").replace("\n", "") for col in crm_df.columns]
        
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
        return "데이터가 부족하여 분석 리포트를 생성할 수 없습니다."
        
    current_data = df[df['period'] == selected_period]
    if current_data.empty:
        return "해당 월의 데이터가 존재하지 않습니다."
        
    latest = current_data.iloc[0]
    analysis_texts = [f"### {latest['period'].strftime('%Y년 %m월')} 성과 분석 요약"]
    
    # [수정] 전년 동월이 아닌 '전월' 데이터로 추출
    prev_month_dt = latest['period'] - pd.DateOffset(months=1)
    prev_data_df = df[df['period'] == prev_month_dt]
    
    if not prev_data_df.empty:
        prev = prev_data_df.iloc[0]
        rec_diff = latest['접수'] - prev['접수']
        rate_diff = (latest['성공율'] - prev['성공율']) * 100
        
        trend_rec = "증가" if rec_diff > 0 else "감소"
        
        # [수정] 전월 대비 증감율로 문구 및 로직 완전 변경
        analysis_texts.append(
            f"- 전월 대비 성과: 접수 건수는 {abs(rec_diff):,.0f}건 {trend_rec}하였으며, "
            f"성공율은 {rate_diff:+.1f}%p 변동하였습니다."
        )
    else:
        analysis_texts.append("- 이전 달의 데이터가 존재하지 않아 전월 대비 성과를 산출할 수 없습니다.")
        
    if crm_df is not None and all(c in crm_df.columns for c in ['성공여부', '연령대', '성별']):
        try:
            stats = crm_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean())
            stats = stats.sort_values(ascending=False)
            if not stats.empty:
                best = stats.index[0]
                best_rate = stats.iloc[0]
                analysis_texts.append(
                    f"- 주요 타겟 고객층: CRM 분석 결과, {best[0]} {best} 고객군의 성공율이 {best_rate:.1%}로 "
                    f"가장 높게 측정되었습니다. 향후 마케팅 시 해당 타겟에 자원을 우선 배정할 것을 권장합니다."
                )
        except:
            pass
            
    return "\n\n".join(analysis_texts)

# =====================================================================
# [4단계] 대시보드 UI 구성
# =====================================================================
# [수정] 대시보드 공식 명칭 변경
st.set_page_config(layout="wide", page_title="현대렌탈케어 고객만족센터 매출관리 대시보드")
st.title("현대렌탈케어 고객만족센터 매출관리 대시보드")
st.markdown("---")

st.sidebar.header("데이터 업로드")
sales_file = st.sidebar.file_uploader("1. 매출 데이터 (필수)", type=["xlsx", "xls"])
crm_file = st.sidebar.file_uploader("2. CRM 데이터 (선택)", type=["xlsx", "xls"])

if sales_file:
    df = parse_sales_data(sales_file)
    crm_df = parse_crm_data(crm_file) if crm_file else None
    
    if df is not None and not df.empty:
        st.sidebar.success("데이터 처리 완료")
        
        valid_periods = df[df['접수'] > 0]['period']
        default_period = valid_periods.max() if not valid_periods.empty else df['period'].max()
        
        period_options = df['period'].dt.strftime('%Y년 %m월').tolist()
        period_options.reverse() 
        default_index = period_options.index(default_period.strftime('%Y년 %m월')) if default_period else 0
        
        selected_month_str = st.selectbox("조회 기준월 설정", options=period_options, index=default_index)
        selected_period = pd.to_datetime(selected_month_str, format='%Y년 %m월')
        
        latest_data = df[df['period'] == selected_period].iloc[0]
        
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
            df_valid = df[df['성공율'] > 0]
            if not df_valid.empty:
                best_per_year = df_valid.loc[df_valid.groupby('year')['성공율'].idxmax()]
                year_cols = st.columns(len(best_per_year))
                for y_col, (_, row) in zip(year_cols, best_per_year.iterrows()):
                    y_col.caption(f"🏆 {row['year']}년 최고 실적\n\n{row['period'].strftime('%m월')} (성공율 {row['성공율']:.1%})")

        with col2:
            st.subheader("지표별 트렌드 분석 (시각화)")
            
            vis_col1, vis_col2 = st.columns(2)
            with vis_col1:
                target_metric = st.selectbox("분석 지표 커스터마이징", ['설치완료', '접수', '컨택', '성공', '성공율'])
            with vis_col2:
                chart_type = st.radio("그래프 형태 선택", ["막대 그래프", "꺾은선형 그래프"], horizontal=True)
                
            # [수정] 기간 설정을 위한 연도, 월 리스트 추출
            available_years = sorted(df['period'].dt.year.unique().tolist())
            months = list(range(1, 13))
            
            start_d = df['period'].min()
            end_d = df['period'].max()
            
            st.markdown("**차트 조회 기간 설정**")
            sc1, sc2, sc3, sc4 = st.columns(4)
            
            with sc1:
                start_y = st.selectbox("시작 연도", options=available_years, index=0, format_func=lambda x: f"{x}년")
            with sc2:
                start_m_idx = months.index(start_d.month) if start_y == start_d.year else 0
                start_m = st.selectbox("시작 월", options=months, index=start_m_idx, format_func=lambda x: f"{x}월")
            with sc3:
                end_y = st.selectbox("종료 연도", options=available_years, index=len(available_years)-1, format_func=lambda x: f"{x}년")
            with sc4:
                end_m_idx = months.index(end_d.month) if end_y == end_d.year else 11
                end_m = st.selectbox("종료 월", options=months, index=end_m_idx, format_func=lambda x: f"{x}월")
                
            start_p = pd.to_datetime(f"{start_y}-{start_m}-01")
            end_p = pd.to_datetime(f"{end_y}-{end_m}-01")
            
            if start_p > end_p:
                st.warning("시작 월이 종료 월보다 늦을 수 없습니다. 기간을 다시 확인해주십시오.")
            else:
                chart_df = df[(df['period'] >= start_p) & (df['period'] <= end_p)].copy()
                chart_df = chart_df[chart_df[target_metric] > 0]
                
                if not chart_df.empty:
                    chart_df['조회월'] = chart_df['period'].dt.strftime('%y년 ') + chart_df['period'].dt.month.astype(str) + '월'
                    
                    if target_metric == '성공율':
                        chart_df[target_metric] = chart_df[target_metric] * 100

                    if chart_type == "막대 그래프":
                        fig = px.bar(chart_df, x='조회월', y=target_metric, text=target_metric)
                        fig.update_traces(
                            texttemplate='%{text:.1f}' if target_metric == '성공율' else '%{text:,.0f}',
                            textposition='outside', 
                            marker_color='#1E88E5', 
                            textfont_size=12,
                            cliponaxis=False        
                        )
                    else:
                        fig = px.line(chart_df, x='조회월', y=target_metric, markers=True, text=target_metric)
                        fig.update_traces(
                            line=dict(width=3, color='#1E88E5'), 
                            marker=dict(size=8, color='#0D47A1'),
                            texttemplate='%{text:.1f}' if target_metric == '성공율' else '%{text:,.0f}',
                            textposition="top center",
                            textfont_size=12,
                            cliponaxis=False
                        )
                        
                    max_val = chart_df[target_metric].max()
                    y_max_range = max_val * 1.15 if max_val > 0 else 1.0

                    fig.update_layout(
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        xaxis_title="",
                        yaxis_title="",  
                        margin=dict(l=10, r=10, t=70, b=10), # [수정] 상단 마진을 70으로 넓혀 텍스트 짤림 완전 방지
                        xaxis=dict(
                            showgrid=False, 
                            tickangle=-45,
                            type='category',
                            categoryorder='array',
                            categoryarray=chart_df['조회월']
                        ),
                        yaxis=dict(
                            showgrid=True, 
                            gridcolor='#E0E0E0',
                            range=[0, y_max_range]
                        ),
                        annotations=[dict(
                            x=0, y=1.15, xref='paper', yref='paper', # [수정] Y위치 1.15로 올려서 안전하게 표기
                            text=f"<b>{target_metric}</b> {'(%)' if target_metric == '성공율' else '(건)'}", 
                            showarrow=False,
                            font=dict(size=14, color='gray'),
                            xanchor='left', yanchor='bottom'
                        )]
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    if target_metric == '성공율':
                        st.caption("※ 성공율은 가시성을 위해 백분율(%) 스케일로 출력됩니다.")
                else:
                    st.warning("선택하신 기간 내에 유효한(0보다 큰) 수치 데이터가 존재하지 않습니다.")
        
        with st.expander("데이터 원본 확인"):
            display_df = df.drop(columns=['year'], errors='ignore').copy()
            display_df['조회월'] = display_df['period'].dt.strftime('%Y-%m')
            display_df = display_df.set_index('조회월').drop(columns=['period'])
            st.dataframe(display_df.style.format({
                "성공율": "{:.2%}", "접수": "{:.0f}", "컨택": "{:.0f}", "성공": "{:.0f}", "설치완료": "{:.0f}"
            }))
            
    else:
        pass
else:
    st.info("좌측 메뉴에서 데이터를 업로드하여 대시보드를 활성화해주십시오.")
