import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- 1. 페이지 기본 설정 ---
st.set_page_config(page_title="영업 성과 대시보드", layout="wide", initial_sidebar_state="collapsed")

# --- 2. 메인 타이틀 및 엑셀 업로드 ---
st.title("📊 통합 영업 성과 대시보드")
st.markdown("최신 실적 데이터를 업로드하면 다차원 시각화 및 AI 데이터 진단이 자동으로 수행됩니다.")
uploaded_file = st.file_uploader("📁 월별 실적 엑셀(또는 CSV) 파일을 드래그 앤 드롭으로 업로드해주세요.", type=["xlsx", "csv"])

# --- 3. 데이터 전처리 함수 ---
@st.cache_data
def load_data(file):
    try:
        df = pd.read_excel(file)
    except Exception:
        df = pd.read_csv(file)
    
    if '구분' in df.columns:
        df = df[~df['구분'].astype(str).isin(['소계', '평균'])]
    
    for col in df.columns:
        if df[col].dtype == 'object' and '%' in str(df[col].iloc[0]):
            df[col] = df[col].str.replace('%', '', regex=False).astype(float) / 100
    return df

# --- ✨ (수정) 안전장치 추가된 렌더링 함수 ---
def safe_get(df, col_name, default_value=0):
    """ 데이터프레임에 특정 열이 없으면 기본값(0)을 반환하는 안전 함수 """
    if col_name in df.columns:
        return df[col_name]
    # 열이 없을 경우, 사용자에게 경고 메시지 표시
    st.warning(f"경고: 업로드된 엑셀 파일에서 '{col_name}' 열을 찾을 수 없습니다. 해당 항목은 0으로 처리됩니다.")
    return pd.Series([default_value] * len(df))

def generate_ai_diagnosis(df):
    required_cols = ['구분', '신규_성공', '재약정_컨택比성공율', '멤버십_성공건']
    if not all(col in df.columns for col in required_cols) or len(df) < 3:
        return "AI 진단 불가: 데이터가 부족하거나 '신규_성공', '재약정_컨택比성공율' 등 필수 열이 파일에 없습니다."

    recent_month = safe_get(df, '구분').iloc[-1]
    prev_month = safe_get(df, '구분').iloc[-2]
    new_growth = safe_get(df, '신규_성공').iloc[-1] - safe_get(df, '신규_성공').iloc[-2]
    new_status = "상승" if new_growth > 0 else "하락"
    avg_recontract_rate = safe_get(df, '재약정_컨택比성공율').mean() * 100
    predicted_new = int(safe_get(df, '신규_성공').tail(3).mean())
    predicted_mem = int(safe_get(df, '멤버십_성공건').tail(3).mean())

    diagnosis_text = f"""
    ### 💡 AI 데이터 기반 핵심 진단 리포트 (기준월: {recent_month})
    **1. 전체 실적 동향:** {recent_month}의 신규 성공 건수는 전월({prev_month}) 대비 **{abs(new_growth)}건 {new_status}**하였습니다.
    **2. 부문별 효율성 진단:** 재약정 부문의 전체 기간 평균 성공률은 **{avg_recontract_rate:.1f}%** 입니다.
    **3. 🤖 AI 기반 차월 실적 예측치:** 다음 달 예상 신규 성공은 약 **{predicted_new:,}건**, 예상 멤버십 성공은 약 **{predicted_mem:,}건** 입니다.
    """
    return diagnosis_text

# --- 4. 화면 렌더링 ---
if uploaded_file is not None:
    try:
        df = load_data(uploaded_file)
        tab1, tab2, tab3, tab4 = st.tabs(["📊 종합 요약", "🌱 신규 고객", "⭐ 멤버십", "🔁 재약정"])

        with tab1:
            st.subheader("전체 KPI 요약")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("총 누적 접수 (신규)", f"{safe_get(df, '신규_접수').sum():,}건")
            c2.metric("총 누적 성공 (신규)", f"{safe_get(df, '신규_성공').sum():,}건")
            c3.metric("누적 멤버십 성공", f"{safe_get(df, '멤버십_성공건').sum():,}건")
            c4.metric("누적 재약정 성공", f"{safe_get(df, '재약정_성공건').sum():,}건")
            st.write("원본 데이터 (미리보기)")
            st.dataframe(df, use_container_width=True)

        with tab2:
            st.subheader("월별 신규 영업 흐름 (접수 vs 컨택 vs 성공)")
            new_cols_to_plot = [col for col in ['신규_접수', '신규_컨택', '신규_성공'] if col in df.columns]
            if new_cols_to_plot:
                fig_new = px.line(df, x='구분', y=new_cols_to_plot, markers=True, title="신규 퍼널 추이 (마우스를 올려보세요)")
                st.plotly_chart(fig_new, use_container_width=True)
            else:
                st.warning("'신규_접수', '신규_컨택' 등의 열이 없어 차트를 그릴 수 없습니다.")

        with tab3:
            st.subheader("멤버십 시도 대비 성공 실적")
            mem_cols_to_plot = [col for col in ['멤버십_시도건', '멤버십_성공건'] if col in df.columns]
            if len(mem_cols_to_plot) > 1:
                fig_mem = px.bar(df, x='구분', y=mem_cols_to_plot, barmode='group', title="멤버십 활동 및 성과 추이")
                st.plotly_chart(fig_mem, use_container_width=True)
            else:
                st.warning("'멤버십_시도건', '멤버십_성공건' 열이 모두 있어야 차트를 그릴 수 있습니다.")
        
        with tab4:
            st.subheader("재약정 성공률 및 실적")
            if '재약정_성공건' in df.columns and '재약정_목표' in df.columns:
                fig_re = go.Figure()
                fig_re.add_trace(go.Bar(x=safe_get(df, '구분'), y=safe_get(df, '재약정_성공건'), name='재약정 성공건'))
                fig_re.add_trace(go.Scatter(x=safe_get(df, '구분'), y=safe_get(df, '재약정_목표'), name='재약정 목표', line=dict(dash='dot')))
                st.plotly_chart(fig_re, use_container_width=True)
            else:
                st.warning("'재약정_성공건', '재약정_목표' 열이 모두 있어야 차트를 그릴 수 있습니다.")

        st.markdown("---")
        with st.container():
            st.markdown(generate_ai_diagnosis(df))

    except Exception as e:
        st.error(f"파일을 처리하는 중 얘기치 못한 오류가 발생했습니다: {e}")

else:
    st.info("👆 상단의 업로드 버튼을 눌러 데이터를 넣어주시면 분석이 시작됩니다.")
