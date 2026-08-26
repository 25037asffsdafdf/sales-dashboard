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

# --- 3. (✨완전 수정) 데이터 전처리 함수 ---
@st.cache_data
def load_data(file):
    """
    2층 구조의 엑셀 헤더를 인식하고, 이를 '카테고리_항목' 형태의 단일 이름으로 변환하는
    업그레이드된 데이터 로드 함수입니다.
    """
    # 엑셀 파일의 첫 두 줄을 헤더로 읽어들임
    df = pd.read_excel(file, header=[0, 1])

    # 새로운 열 이름을 저장할 리스트
    new_columns = []
    
    # MultiIndex(2층) 헤더를 순회하며 새로운 이름 생성
    for col in df.columns:
        # col[0]은 1층 헤더 (예: '신규'), col[1]은 2층 헤더 (예: '접수')
        
        # 1층 헤더가 'Unnamed'로 시작하면, 2층 헤더 이름만 사용 (예: '구분')
        if 'Unnamed' in str(col[0]):
            new_columns.append(col[1])
        # 그렇지 않으면 '1층_2층' 형태로 조합 (예: '신규_접수')
        else:
            new_columns.append(f'{col[0]}_{col[1]}')
            
    # 데이터프레임의 열 이름을 새로 만든 이름으로 교체
    df.columns = new_columns
    
    # 기존 전처리 로직 (소계/평균 행 제거, 퍼센트 변환)
    if '구분' in df.columns:
        df = df[~df['구분'].astype(str).isin(['소계', '평균'])]
    
    for col in df.columns:
        if df[col].dtype == 'object' and '%' in str(df[col].iloc[0]):
            df[col] = df[col].str.replace('%', '', regex=False).astype(float) / 100
            
    return df

# --- (함수명 수정) AI 진단 함수 ---
def generate_ai_diagnosis(df):
    # AI 진단에 필요한 최소 열 목록
    required_cols = ['구분', '신규_성공', '재약정_컨택比성공율', '멤버십_성공건']
    
    # 필수 열 중 하나라도 없거나 데이터가 3개월 미만이면 진단 불가
    if not all(col in df.columns for col in required_cols) or len(df) < 3:
        missing_cols = [col for col in required_cols if col not in df.columns]
        return f"AI 진단 불가: 데이터가 부족하거나 필수 열({', '.join(missing_cols)})이 파일에 없습니다."

    # 안전하게 데이터 추출
    recent_month = df['구분'].iloc[-1]
    prev_month = df['구분'].iloc[-2]
    new_growth = df['신규_성공'].iloc[-1] - df['신규_성공'].iloc[-2]
    new_status = "상승" if new_growth > 0 else "하락"
    avg_recontract_rate = df['재약정_컨택比성공율'].mean() * 100
    predicted_new = int(df['신규_성공'].tail(3).mean())
    predicted_mem = int(df['멤버십_성공건'].tail(3).mean())

    diagnosis_text = f"""
    ### 💡 AI 데이터 기반 핵심 진단 리포트 (기준월: {recent_month})
    **1. 전체 실적 동향:** {recent_month}의 신규 성공 건수는 전월({prev_month}) 대비 **{abs(new_growth):,}건 {new_status}**하였습니다.
    **2. 부문별 효율성 진단:** 재약정 부문의 전체 기간 평균 성공률은 **{avg_recontract_rate:.1f}%** 입니다.
    **3. 🤖 AI 기반 차월 실적 예측치:** 다음 달 예상 신규 성공은 약 **{predicted_new:,}건**, 예상 멤버십 성공은 약 **{predicted_mem:,}건** 입니다.
    """
    return diagnosis_text

# --- 4. 화면 렌더링 ---
if uploaded_file is not None:
    try:
        df = load_data(uploaded_file)
        
        tab1, tab2, tab3, tab4 = st.tabs(["📊 종합 요약", "🌱 신규 고객", "⭐ 멤버십", "🔁 재약정"])

        # 각 탭 렌더링
        with tab1:
            st.subheader("전체 KPI 요약")
            cols_kpi = {'신규_접수': '총 누적 접수 (신규)', '신규_성공': '총 누적 성공 (신규)', '멤버십_성공건': '누적 멤버십 성공', '재약정_성공건': '누적 재약정 성공'}
            c1, c2, c3, c4 = st.columns(4)
            columns_map = [c1, c2, c3, c4]
            for idx, (col, title) in enumerate(cols_kpi.items()):
                if col in df.columns:
                    columns_map[idx].metric(title, f"{df[col].sum():,}건")
                else:
                    columns_map[idx].metric(title, "N/A", help=f"'{col}' 열 없음")
            st.write("데이터 미리보기 (이름 자동 변환 적용)")
            st.dataframe(df, use_container_width=True)

        with tab2:
            st.subheader("월별 신규 영업 흐름 (접수 vs 컨택 vs 성공)")
            fig = px.line(df, x='구분', y=['신규_접수', '신규_컨택', '신규_성공'], markers=True)
            st.plotly_chart(fig, use_container_width=True)

        with tab3:
            st.subheader("멤버십 시도 대비 성공 실적")
            fig = px.bar(df, x='구분', y=['멤버십_시도건', '멤버십_성공건'], barmode='group')
            st.plotly_chart(fig, use_container_width=True)
        
        with tab4:
            st.subheader("재약정 성공률 및 실적")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df['구분'], y=df['재약정_성공건'], name='재약정 성공건'))
            fig.add_trace(go.Scatter(x=df['구분'], y=df['재약정_목표'], name='재약정 목표', line=dict(dash='dot')))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        with st.container():
            st.markdown(generate_ai_diagnosis(df))

    except Exception as e:
        st.error(f"파일을 처리하는 중 오류가 발생했습니다. 엑셀 파일의 첫 두 줄이 헤더(제목) 형식인지 확인해주세요. (오류: {e})")
else:
    st.info("👆 상단의 업로드 버튼을 눌러 데이터를 넣어주시면 분석이 시작됩니다.")
