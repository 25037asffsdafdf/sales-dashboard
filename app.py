import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# 1. Page Config (UI: Korean, Logic: English)
st.set_page_config(page_title="영업 성과 대시보드", layout="wide")

st.title("📊 통합 영업 성과 대시보드")
st.markdown("최신 실적 데이터를 업로드하면 다차원 시각화 및 AI 데이터 진단이 자동으로 수행됩니다.")

uploaded_file = st.file_uploader("📁 월별 실적 엑셀 파일을 드래그 앤 드롭으로 업로드해주세요.", type=["xlsx", "csv"])

# 2. Bulletproof Data Loading Function
@st.cache_data
def load_clean_data(file):
    # Read raw data as string, ignoring excel headers completely
    raw_df = pd.read_excel(file, header=None, dtype=str)
    raw_df = raw_df.dropna(how='all')
    
    # Auto-detect which column has the dates (to fix shifted Excel columns)
    date_col_idx = 0
    for i in raw_df.columns:
        if raw_df[i].str.contains('월', na=False).any():
            date_col_idx = i
            break
            
    # Filter only rows that contain valid month strings
    valid_rows = raw_df[raw_df[date_col_idx].str.contains('월', na=False)].copy()
    
    processed_data = pd.DataFrame()
    
    # Date Format Converter: "25.6월" -> "25년 6월"
    def format_month(val):
        val = str(val).strip()
        if '.' in val:
            return val.replace('.', '년 ')
        return val
    
    processed_data['Month_Label'] = valid_rows[date_col_idx].apply(format_month)
    
    # Safe Number Parser: Ignores text, forces conversion to numbers
    def parse_number(col_offset):
        target_idx = date_col_idx + col_offset
        if target_idx in valid_rows.columns:
            clean_str = valid_rows[target_idx].astype(str).str.replace(',', '')
            return pd.to_numeric(clean_str, errors='coerce').fillna(0).astype(int)
        return pd.Series([0] * len(valid_rows))
        
    # Extracting Data via relative positions (Ignoring ratio columns)
    processed_data['New_Receipt'] = parse_number(1)
    processed_data['New_Contact'] = parse_number(2)
    processed_data['New_Success'] = parse_number(3)
    processed_data['New_Install'] = parse_number(5)
    
    processed_data['Mem_Target'] = parse_number(6)
    processed_data['Mem_Attempt'] = parse_number(7)
    processed_data['Mem_Success'] = parse_number(9)
    processed_data['Mem_Contract'] = parse_number(11)
    
    processed_data['Re_Target'] = parse_number(12)
    processed_data['Re_Attempt'] = parse_number(13)
    processed_data['Re_Success'] = parse_number(15)
    processed_data['Re_Confirm'] = parse_number(17)
    
    return processed_data

# 3. AI Report Generator
def generate_ai_report(df):
    if len(df) < 3:
        return "AI 진단 불가: 최소 3개월 이상의 데이터가 필요합니다."
        
    latest_month = df['Month_Label'].iloc[-1]
    prev_month = df['Month_Label'].iloc[-2]
    
    growth_diff = df['New_Success'].iloc[-1] - df['New_Success'].iloc[-2]
    growth_status = "상승" if growth_diff > 0 else "하락"
    
    pred_new = int(df['New_Success'].tail(3).mean())
    pred_mem = int(df['Mem_Success'].tail(3).mean())
    
    report = f"""
    ### 💡 AI 데이터 기반 핵심 진단 리포트 (기준월: {latest_month})
    **1. 전체 실적 동향:** {latest_month}의 신규 성공 건수는 전월({prev_month}) 대비 **{abs(growth_diff):,}건 {growth_status}**하였습니다.
    **2. 🤖 AI 기반 차월 실적 예측치:** 다음 달 예상 신규 성공은 약 **{pred_new:,}건**, 예상 멤버십 성공은 약 **{pred_mem:,}건** 입니다.
    """
    return report

# 4. UI Rendering
if uploaded_file is not None:
    try:
        df_clean = load_clean_data(uploaded_file)
        
        tab_main, tab_new, tab_mem, tab_re = st.tabs(["📊 종합 요약", "🌱 신규 고객", "⭐ 멤버십", "🔁 재약정"])
        
        with tab_main:
            st.subheader("전체 KPI 요약")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("총 누적 접수 (신규)", f"{df_clean['New_Receipt'].sum():,}건")
            col2.metric("총 누적 성공 (신규)", f"{df_clean['New_Success'].sum():,}건")
            col3.metric("누적 멤버십 성공", f"{df_clean['Mem_Success'].sum():,}건")
            col4.metric("누적 재약정 성공", f"{df_clean['Re_Success'].sum():,}건")
            
            st.write("데이터 미리보기 (숫자 및 날짜 포맷 자동 변환됨)")
            st.dataframe(df_clean, use_container_width=True)
            
        with tab_new:
            st.subheader("월별 신규 영업 흐름 (비율 제외)")
            fig_new = px.line(df_clean, x='Month_Label', y=['New_Receipt', 'New_Contact', 'New_Success', 'New_Install'], markers=True)
            # 영어 변수를 화면엔 한글로 보이도록 치환
            fig_new.for_each_trace(lambda t: t.update(name=t.name.replace('New_Receipt', '접수').replace('New_Contact', '컨택').replace('New_Success', '성공').replace('New_Install', '설치완료')))
            st.plotly_chart(fig_new, use_container_width=True)
            
        with tab_mem:
            st.subheader("멤버십 목표 대비 실적")
            fig_mem = go.Figure()
            fig_mem.add_trace(go.Bar(x=df_clean['Month_Label'], y=df_clean['Mem_Attempt'], name='시도건'))
            fig_mem.add_trace(go.Scatter(x=df_clean['Month_Label'], y=df_clean['Mem_Target'], name='목표', mode='lines+markers'))
            st.plotly_chart(fig_mem, use_container_width=True)
            
        with tab_re:
            st.subheader("재약정 목표 대비 실적")
            fig_re = go.Figure()
            fig_re.add_trace(go.Bar(x=df_clean['Month_Label'], y=df_clean['Re_Attempt'], name='시도건'))
            fig_re.add_trace(go.Scatter(x=df_clean['Month_Label'], y=df_clean['Re_Target'], name='목표', mode='lines+markers'))
            st.plotly_chart(fig_re, use_container_width=True)
            
        st.markdown("---")
        with st.container():
            st.markdown(generate_ai_report(df_clean))
            
    except Exception as e:
        st.error(f"데이터를 처리하는 중 문제가 발생했습니다. 파일을 다시 확인해주세요. (상세 오류: {e})")
else:
    st.info("👆 상단의 업로드 버튼을 눌러 데이터를 넣어주시면 분석이 시작됩니다.")
