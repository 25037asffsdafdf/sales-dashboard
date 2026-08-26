import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# --- 1. 페이지 기본 설정 (밝고 넓은 UI) ---
st.set_page_config(page_title="영업 성과 대시보드", layout="wide", initial_sidebar_state="collapsed")

# --- 2. 메인 타이틀 및 엑셀 업로드 (상단 배치) ---
st.title("📊 통합 영업 성과 대시보드")
st.markdown("최신 실적 데이터를 업로드하면 다차원 시각화 및 AI 데이터 진단이 자동으로 수행됩니다.")

# 제목 바로 아래에 업로드 버튼 배치
uploaded_file = st.file_uploader("📁 월별 실적 엑셀(또는 CSV) 파일을 드래그 앤 드롭으로 업로드해주세요.", type=["xlsx", "csv"])

# --- 3. 데이터 전처리 함수 ---
@st.cache_data
def load_data(file):
    try:
        df = pd.read_excel(file)
    except:
        df = pd.read_csv(file)
        
    # '소계', '평균' 등 불필요한 행 제거
    if '구분' in df.columns:
        df = df[~df['구분'].astype(str).isin(['소계', '평균'])]
        
    # 퍼센트(%) 문자열을 숫자로 변환 (예: '38.3%' -> 0.383)
    for col in df.columns:
        if df[col].dtype == 'object' and df[col].str.contains('%').any():
            df[col] = df[col].str.replace('%', '').astype(float) / 100
    return df

# --- 4. AI 진단 로직 함수 ---
def generate_ai_diagnosis(df):
    if len(df) < 3:
        return "데이터가 부족하여 정확한 진단을 내리기 어렵습니다. 최소 3개월 이상의 데이터를 업로드해주세요."
        
    # 최근 달력 기준 수치 추출
    recent_month = df.iloc[-1]['구분']
    prev_month = df.iloc[-2]['구분']
    
    # 1. 신규 실적 진단
    new_growth = df.iloc[-1]['신규_성공'] - df.iloc[-2]['신규_성공']
    new_status = "상승" if new_growth > 0 else "하락"
    
    # 2. 재약정 효율성 진단 (컨택 대비 성공률)
    avg_recontract_rate = df['재약정_컨택比성공율'].mean() * 100
    recent_recontract_rate = df.iloc[-1]['재약정_컨택比성공율'] * 100
    
    # 3. 다음 달 예측치 (최근 3개월 이동평균 기반)
    predicted_new = int(df['신규_성공'].tail(3).mean())
    predicted_mem = int(df['멤버십_성공건'].tail(3).mean())
    
    diagnosis_text = f"""
    ### 💡 AI 데이터 기반 핵심 진단 리포트 (기준월: {recent_month})
    
    **1. 전체 실적 동향 (Trend Analysis)**
    * 가장 최근인 {recent_month}의 신규 성공 건수는 전월({prev_month}) 대비 **{abs(new_growth)}건 {new_status}**하였습니다. 
    * 영업 퍼널의 가장 첫 단계인 '접수'는 꾸준히 유지되고 있으나, 접수 대비 성공으로 이어지는 전환율 개선을 위한 액션 플랜이 필요합니다.
    
    **2. 부문별 효율성 진단 (Efficiency)**
    * **재약정 부문:** 전체 기간 평균 재약정 성공률은 **{avg_recontract_rate:.1f}%**이며, 최근 월은 **{recent_recontract_rate:.1f}%**를 기록했습니다. 재약정은 기존 고객을 대상으로 하므로 타 부문 대비 성공률이 높아야 정상입니다. 만약 이 수치가 15% 미만으로 떨어진다면 프로모션 재점검이 강력히 권장됩니다.
    * **멤버십 부문:** 시도 건수 대비 실제 성공 건수의 격차가 발생하고 있습니다. 이는 단순 컨택 횟수보다는 '상담 퀄리티'나 '고객 혜택 소구점'을 강화해야 함을 시사합니다.
    
    **3. 🤖 AI 기반 차월 실적 예측치 (Forecast)**
    최근 3개월의 데이터 흐름(이동평균 추세선)을 분석한 결과, 특별한 외부 요인이 없다면 다음 달 예상 실적은 다음과 같습니다.
    * **예상 신규 성공:** 약 **{predicted_new:,}건**
    * **예상 멤버십 성공:** 약 **{predicted_mem:,}건**
    * **행동 제안:** 예측치를 상회하기 위해 다음 달에는 재약정 만료 도래 고객을 타겟팅한 '사전 알림 톡 캠페인'을 실시하는 것을 추천합니다.
    """
    return diagnosis_text


# --- 5. 화면 렌더링 (파일이 업로드된 경우에만 표시) ---
if uploaded_file is not None:
    df = load_data(uploaded_file)
    
    # 탭 생성 (종합, 신규, 멤버십, 재약정)
    tab1, tab2, tab3, tab4 = st.tabs(["📊 종합 요약", "🌱 신규 고객", "⭐ 멤버십", "🔁 재약정"])
    
    # [Tab 1] 종합 요약
    with tab1:
        st.subheader("전체 KPI 요약")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 누적 접수 (신규)", f"{df['신규_접수'].sum():,}건")
        c2.metric("총 누적 성공 (신규)", f"{df['신규_성공'].sum():,}건")
        c3.metric("누적 멤버십 성공", f"{df['멤버십_성공건'].sum():,}건")
        c4.metric("누적 재약정 성공", f"{df['재약정_성공건'].sum():,}건")
        
        st.write("원본 데이터 (미리보기)")
        st.dataframe(df, use_container_width=True)
        
    # [Tab 2] 신규 고객
    with tab2:
        st.subheader("월별 신규 영업 흐름 (접수 vs 컨택 vs 성공)")
        fig_new = px.line(df, x='구분', y=['신규_접수', '신규_컨택', '신규_성공'], 
                          markers=True, title="신규 퍼널 추이 (마우스를 올려보세요)")
        fig_new.update_layout(yaxis_title="건수", xaxis_title="월", legend_title="항목")
        st.plotly_chart(fig_new, use_container_width=True)
        
    # [Tab 3] 멤버십
    with tab3:
        st.subheader("멤버십 시도 대비 성공 실적")
        fig_mem = px.bar(df, x='구분', y=['멤버십_시도건', '멤버십_성공건'], 
                         barmode='group', title="멤버십 활동 및 성과 추이")
        fig_mem.update_layout(yaxis_title="건수", xaxis_title="월", legend_title="항목")
        st.plotly_chart(fig_mem, use_container_width=True)
        
    # [Tab 4] 재약정
    with tab4:
        st.subheader("재약정 성공률 및 실적")
        # 혼합 차트 (막대: 성공건, 꺾은선: 목표)
        fig_re = go.Figure()
        fig_re.add_trace(go.Bar(x=df['구분'], y=df['재약정_성공건'], name='재약정 성공건', marker_color='royalblue'))
        fig_re.add_trace(go.Scatter(x=df['구분'], y=df['재약정_목표'], name='재약정 목표', line=dict(color='firebrick', dash='dot')))
        fig_re.update_layout(title="월별 재약정 달성 현황", xaxis_title="월", yaxis_title="건수")
        st.plotly_chart(fig_re, use_container_width=True)
        
    st.markdown("---")
    
    # [하단] AI 진단 섹션
    with st.container():
        st.markdown(generate_ai_diagnosis(df))

else:
    # 파일을 업로드하지 않았을 때 빈 화면 대신 보여줄 안내문
    st.info("👆 상단의 업로드 버튼을 눌러 데이터를 넣어주시면 분석이 시작됩니다.")
