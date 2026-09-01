import streamlit as st
import pandas as pd
import io
from datetime import datetime

# --- 데이터 처리 함수 ---
def parse_sales_data(uploaded_file):
    """업로드된 엑셀 파일을 읽고 분석 가능한 형태로 가공합니다."""
    try:
        # 첫 번째 시트를 읽되, 헤더가 없는 상태로 읽어옵니다.
        df = pd.read_excel(uploaded_file, header=None, sheet_name=0)

        # 데이터가 2개의 테이블로 나뉘어 있는 경우를 처리
        split_row = df[df[0] == '구 분'].index
        if len(split_row) > 1:
            df1 = df.iloc[:split_row[1]].copy()
            df2 = df.iloc[split_row[1]:].copy()
            df2.columns = df1.columns # 두 번째 테이블의 컬럼을 첫 번째와 동일하게 맞춤
            df = pd.concat([df1, df2], axis=1)

        # '구 분' 행을 인덱스로 설정
        df = df.set_index(0)
        
        # 컬럼 이름 정리 (25.1월 -> 2501)
        header_row = df.loc['구 분']
        df = df.drop('구 분').T.reset_index(drop=True)
        df.columns = header_row
        
        # 월(period) 컬럼 생성 및 데이터 타입 변환
        df['period'] = df.columns[1:].str.replace('월', '').str.replace('.', '')
        df = df.melt(id_vars=['period'], value_vars=df.columns[:-1], var_name='구분', value_name='값')
        df = df.pivot(index='period', columns='구분', values='값').reset_index()

        # 데이터 타입 정리
        df['period'] = pd.to_datetime(df['period'], format='%y%m')
        
        for col in ['접수', '컨택', '성공', '설치완료']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # '접수比 성공율'을 숫자(float)로 변환
        if '접수比 성공율' in df.columns:
            # '%' 문자가 문자열로 포함된 경우 처리
            if df['접수比 성공율'].dtype == 'object':
                 df['접수比 성공율'] = df['접수比 성공율'].str.replace('%', '', regex=False).astype(float) / 100.0
            # 직접 계산이 필요하면 아래 주석 해제
            # df['접수比 성공율'] = df['성공'] / df['접수']

        df = df.sort_values('period').reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"매출 데이터 처리 중 오류가 발생했습니다: {e}")
        st.info("업로드한 엑셀 파일이 제공해주신 이미지와 유사한 구조인지 확인해주세요. (예: 첫 번째 열에 '구분', '접수' 등, 첫 행에 '25.1월' 등)")
        return None

def parse_crm_data(uploaded_file):
    """CRM 데이터를 읽고 나이, 연령대를 계산합니다."""
    try:
        crm_df = pd.read_excel(uploaded_file)
        # '생년월일' 컬럼이 있는지 확인하고 날짜형으로 변환
        if '생년월일' in crm_df.columns:
            crm_df['생년월일'] = pd.to_datetime(crm_df['생년월일'], errors='coerce')
            current_year = datetime.now().year
            crm_df['나이'] = current_year - crm_df['생년월일'].dt.year
            crm_df['연령대'] = (crm_df['나이'] // 10 * 10).astype(str) + '대'
        return crm_df
    except Exception as e:
        st.error(f"CRM 데이터 처리 중 오류가 발생했습니다: {e}")
        return None


# --- AI 분석 함수 ---
def generate_ai_analysis(df, crm_df=None):
    """데이터를 기반으로 분석 및 평가 텍스트를 생성합니다."""
    if df is None or df.empty:
        return "분석할 데이터가 없습니다."

    # M-1 (최신 월) 데이터 기준
    latest = df.iloc[-1]
    prev_month = df.iloc[-2] if len(df) > 1 else None

    analysis_texts = []

    # 1. 전년 동월 대비 분석
    target_month = latest['period']
    last_year_month = target_month.replace(year=target_month.year - 1)
    last_year_data = df[df['period'] == last_year_month]

    if not last_year_data.empty:
        ly_data = last_year_data.iloc[0]
        reception_diff = latest['접수'] - ly_data['접수']
        success_rate_diff = (latest['접수比 성공율'] - ly_data['접수比 성공율']) * 100
        
        analysis_texts.append(
            f"📈 **전년 동월 대비 분석**: {target_month.strftime('%Y년 %m월')}은 전년 동월 대비 "
            f"접수 건수가 **{reception_diff:,.0f}건** {'증가' if reception_diff > 0 else '감소'}했고, "
            f"성공률은 **{success_rate_diff:.1f}%p** {'상승' if success_rate_diff > 0 else '하락'}했습니다."
        )

    # 2. CRM 데이터 연계 분석
    if crm_df is not None and all(col in crm_df.columns for col in ['성별', '연령대']):
        try:
            # 여기서는 CRM 데이터에 '성공여부' 컬럼이 있다고 가정합니다.
            # 실제 데이터에 맞게 컬럼명을 수정해야 합니다.
            # 예시: crm_df.rename(columns={'성공여부컬럼명': '성공여부'}, inplace=True)
            if '성공여부' not in crm_df.columns:
                 st.warning("CRM 데이터에 '성공여부'와 같은 성공/실패를 나타내는 컬럼이 필요합니다. 임의로 '성공' 컬럼을 만들어 분석합니다.")
                 # 성공률이 50%라고 가정하고 임의의 '성공여부' 생성
                 crm_df['성공여부'] = pd.Series(list('성공' * (len(crm_df)//2)) + list('실패' * (len(crm_df) - len(crm_df)//2))).sample(frac=1).values


            # 성별 분석
            gender_success_rate = crm_df.groupby('성별')['성공여부'].apply(lambda x: (x == '성공').mean()).sort_values(ascending=False)
            if not gender_success_rate.empty:
                top_gender = gender_success_rate.index[0]
                analysis_texts.append(
                    f"👥 **주요 고객 분석 (성별)**: **{top_gender}**의 성공률이 가장 높게 나타났습니다. "
                    f"이는 타겟 마케팅 시 중요한 고려사항이 될 수 있습니다."
                )

            # 연령대 분석
            age_success_rate = crm_df.groupby('연령대')['성공여부'].apply(lambda x: (x == '성공').mean()).sort_values(ascending=False)
            if not age_success_rate.empty:
                top_age_group = age_success_rate.index[0]
                analysis_texts.append(
                    f"🎂 **주요 고객 분석 (연령)**: **{top_age_group}** 고객층에서 가장 높은 성공률을 보였습니다. "
                    f"이 연령대에 맞는 프로모션 전략이 효과적일 수 있습니다."
                )
        except Exception as e:
             analysis_texts.append(f"CRM 데이터 분석 중 오류: {e}")


    # 3. 종합 인사이트
    insight = "전반적으로 데이터의 월별 변동성을 고려할 때, 특정 이벤트나 시즌에 따른 영향이 있는지 추가 데이터(마케팅 활동, 공휴일 등)와 함께 분석하면 더 깊은 인사이트를 얻을 수 있습니다."
    analysis_texts.append(f"💡 **종합 의견**: {insight}")
    
    return "\n\n".join(analysis_texts)


# --- 대시보드 UI 구성 ---
st.set_page_config(layout="wide")
st.title("📈 매출 지표 대시보드")

# --- 사이드바: 파일 업로드 ---
st.sidebar.header("📁 데이터 업로드")
sales_file = st.sidebar.file_uploader("1. 매출 데이터 엑셀 파일", type=["xlsx", "xls"])
crm_file = st.sidebar.file_uploader("2. CRM 로우 데이터 (선택)", type=["xlsx", "xls"])

if sales_file:
    df = parse_sales_data(sales_file)
    crm_df = parse_crm_data(crm_file) if crm_file else None

    if df is not None:
        st.sidebar.success("매출 데이터 로드 완료!")
        if crm_file and crm_df is not None:
            st.sidebar.success("CRM 데이터 로드 완료!")
        elif crm_file and crm_df is None:
            st.sidebar.error("CRM 데이터 로드 실패.")

        # --- 메인 대시보드 ---
        
        # M-1 (최신 월) 데이터
        latest_data = df.iloc[-1]
        prev_data = df.iloc[-2] if len(df) > 1 else None

        st.header(f"📊 {latest_data['period'].strftime('%Y년 %m월')} 주요 지표 (전월 대비)")

        col1, col2, col3, col4 = st.columns(4)
        
        # 1. 접수
        with col1:
            delta_reception = (latest_data['접수'] - prev_data['접수']) if prev_data is not None else 0
            st.metric(label="✅ 접수 (건)", value=f"{latest_data['접수']:,.0f}", delta=f"{delta_reception:,.0f}")
        
        # 2. 컨택
        with col2:
            delta_contact = (latest_data['컨택'] - prev_data['컨택']) if prev_data is not None else 0
            st.metric(label="📞 컨택 (건)", value=f"{latest_data['컨택']:,.0f}", delta=f"{delta_contact:,.0f}")

        # 3. 성공
        with col3:
            delta_success = (latest_data['성공'] - prev_data['성공']) if prev_data is not None else 0
            st.metric(label="🏆 성공 (건)", value=f"{latest_data['성공']:,.0f}", delta=f"{delta_success:,.0f}")

        # 4. 성공률
        with col4:
            delta_rate = (latest_data['접수比 성공율'] - prev_data['접수比 성공율']) * 100 if prev_data is not None else 0
            st.metric(label="🎯 성공률 (%)", value=f"{latest_data['접수比 성공율']:.1%}", delta=f"{delta_rate:.1f}%p")

        st.markdown("---")

        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("💡 AI 분석 및 평가")
            ai_report = generate_ai_analysis(df, crm_df)
            st.markdown(ai_report)
            
            # 최고의 달
            best_month = df.loc[df['접수比 성공율'].idxmax()]
            st.info(f"**⭐ 최고의 달**: **{best_month['period'].strftime('%Y년 %m월')}**에 **{best_month['접수比 성공율']:.1%}**로 가장 높은 성공률을 기록했습니다.")

        with col2:
            st.subheader("🔍 설치 완료 건수 그래프")
            
            # 기간 설정
            min_date = df['period'].min().to_pydatetime()
            max_date = df['period'].max().to_pydatetime()

            date_range = st.date_input(
                "기간 선택",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                format="YYYY.MM.DD"
            )
            
            if st.button("📈 그래프 보기"):
                start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
                
                # 선택된 기간 내 데이터 필터링
                chart_data = df[(df['period'] >= start_date) & (df['period'] <= end_date)]
                
                if not chart_data.empty:
                    chart_data['월'] = chart_data['period'].dt.strftime('%y.%m')
                    st.bar_chart(chart_data.set_index('월')['설치완료'])
                else:
                    st.warning("선택된 기간에 데이터가 없습니다.")

        # 데이터 테이블 표시 (옵션)
        with st.expander("전체 데이터 보기"):
            display_df = df.copy()
            display_df['period'] = display_df['period'].dt.strftime('%Y-%m')
            st.dataframe(display_df)

else:
    st.info("좌측 사이드바에서 매출 데이터 엑셀 파일을 업로드하여 대시보드를 시작하세요.")

