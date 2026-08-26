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

# --- 3. (✨완전 재작성) 데이터 로드 및 강제 매핑 함수 ---
@st.cache_data
def load_and_map_data(file):
    """
    엑셀의 헤더(열 이름)를 완전히 무시하고, 정해진 위치(열 순서)에 따라
    데이터를 강제로 매핑하는 가장 확실한 방식의 로드 함수.
    """
    # 엑셀의 첫 2줄(헤더)을 건너뛰고 데이터만 읽어옴
    df = pd.read_excel(file, header=None, skiprows=2)
    
    # 너무 길거나 짧은 데이터는 제외 (소계/평균 행 필터링)
    df = df[df[0].str.contains('월', na=False)]

    # 정의된 열 위치에 따라 새 데이터프레임 생성
    # 원본 엑셀: A열=0, B열=1, C열=2 ...
    data = {
        '구분': df[0].apply(lambda x: x.replace('.', '년 ') + '월' if '.' in str(x) else x),
        '신규_접수': pd.to_numeric(df[1]),
        '신규_컨택': pd.to_numeric(df[2]),
        '신규_성공': pd.to_numeric(df[3]),
        '신규_설치완료': pd.to_numeric(df[5]),
        '멤버십_목표': pd.to_numeric(df[6]),
        '멤버십_시도건': pd.to_numeric(df[7]),
        '멤버십_성공건': pd.to_numeric(df[9]),
        '멤버십_계약서완료': pd.to_numeric(df[11]),
        '재약정_목표': pd.to_numeric(df[12]),
        '재약정_시도건': pd.to_numeric(df[13]),
        '재약정_성공건': pd.to_numeric(df[15]),
        '재약정_재약정확정': pd.to_numeric(df[17]),
    }
    
    return pd.DataFrame(data)

# --- 4. AI 진단 함수 (안전성 강화) ---
def generate_ai_diagnosis(df):
    if len(df) < 3:
        return "AI 진단 불가: 3개월 이상의 데이터가 필요합니다."

    recent_month = df['구분'].iloc[-1]
    prev_month = df['구분'].iloc[-2]
    new_growth = df['신규_성공'].iloc[-1] - df['신규_성공'].iloc[-2]
    new_status = "상승" if new_growth > 0 else "하락"
    predicted_new = int(df['신규_성공'].tail(3).mean())
    predicted_mem = int(df['멤버십_성공건'].tail(3).mean())

    diagnosis_text = f"""
    ### 💡 AI 데이터 기반 핵심 진단 리포트 (기준월: {recent_month})
    **1. 전체 실적 동향:** {recent_month}의 신규 성공 건수는 전월({prev_month}) 대비 **{abs(new_growth):,}건 {new_status}**하였습니다.
    **2. 🤖 AI 기반 차월 실적 예측치:** 다음 달 예상 신규 성공은 약 **{predicted_new:,}건**, 예상 멤버십 성공은 약 **{predicted_mem:,}건** 입니다.
    """
    return diagnosis_text

# --- 5. 화면 렌더링 ---
if uploaded_file is not None:
    try:
        df = load_and_map_data(uploaded_file)
        
        tab1, tab2, tab3, tab4 = st.tabs(["📊 종합 요약", "🌱 신규 고객", "⭐ 멤버십", "🔁 재약정"])

        with tab1:
            st.subheader("전체 KPI 요약")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("총 누적 접수 (신규)", f"{df['신규_접수'].sum():,}건")
            c2.metric("총 누적 성공 (신규)", f"{df['신규_성공'].sum():,}건")
            c3.metric("누적 멤버십 성공", f"{df['멤버십_성공건'].sum():,}건")
            c4.metric("누적 재약정 성공", f"{df['재약정_성공건'].sum():,}건")
            st.write("데이터 미리보기 (위치 기반으로 자동 변환된 데이터)")
            st.dataframe(df, use_container_width=True)

        with tab2:
            st.subheader("월별 신규 영업 흐름 (접수, 컨택, 성공, 설치완료)")
            fig = px.line(df, x='구분', y=['신규_접수', '신규_컨택', '신규_성공', '신규_설치완료'], markers=True)
            st.plotly_chart(fig, use_container_width=True)

        with tab3:
            st.subheader("멤버십 목표 대비 실적")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df['구분'], y=df['멤버십_시도건'], name='시도건'))
            fig.add_trace(go.Scatter(x=df['구분'], y=df['멤버십_목표'], name='목표', mode='lines+markers'))
            st.plotly_chart(fig, use_container_width=True)
        
        with tab4:
            st.subheader("재약정 목표 대비 실적")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df['구분'], y=df['재약정_시도건'], name='시도건'))
            fig.add_trace(go.Scatter(x=df['구분'], y=df['재약정_목표'], name='목표', mode='lines+markers'))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        with st.container():
            st.markdown(generate_ai_diagnosis(df))

    except Exception as e:
        st.error(f"파일을 처리하는 중 예상치 못한 오류가 발생했습니다. (오류: {e})")
else:
    st.info("👆 상단의 업로드 버튼을 눌러 데이터를 넣어주시면 분석이 시작됩니다.")

