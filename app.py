import streamlit as st
import pandas as pd
from datetime import datetime
import re
import traceback
import plotly.express as px

# =====================================================================
# [0단계] 고급 디자인 커스텀 CSS
# =====================================================================
def apply_custom_css():
    st.markdown("""
        <style>
            .stApp { background-color: #F9F9F6; }
            [data-testid="stMetric"] {
                background-color: #FFFFFF;
                padding: 20px 25px;
                border-radius: 12px;
                box-shadow: 0px 6px 15px rgba(0, 0, 0, 0.08);
                border: 1px solid #EAEAEA;
                border-left: 6px solid #2C3E50;
                transition: transform 0.2s ease;
            }
            [data-testid="stMetric"]:hover {
                transform: translateY(-3px);
                box-shadow: 0px 8px 20px rgba(0, 0, 0, 0.12);
            }
            [data-testid="stExpander"] {
                background-color: #FFFFFF;
                border-radius: 12px;
                box-shadow: 0px 4px 12px rgba(0, 0, 0, 0.06);
                border: 1px solid #E5E5E5;
                margin-bottom: 15px;
            }
            h1, h2, h3, h4 {
                color: #2C3E50 !important;
                font-weight: 700 !important;
            }
        </style>
    """, unsafe_allow_html=True)

# =====================================================================
# [1단계] 지표명 및 문자열 정제
# =====================================================================
def clean_string(val):
    if pd.isna(val): return ""
    return str(val).replace(" ", "").replace("\n", "").replace("\t", "").replace("\r", "").strip()

def standardize_metric_name(raw_name):
    clean_name = clean_string(raw_name)
    if not clean_name: return None
    
    if '접수' in clean_name and ('비' in clean_name or '比' in clean_name or '율' in clean_name or '률' in clean_name): return '성공율'
    if '성공' in clean_name and ('율' in clean_name or '률' in clean_name): return '성공율'
    if '설치' in clean_name and '완료' in clean_name: return '설치완료'
    if '성공' in clean_name: return '성공'
    if '컨택' in clean_name or '콜' in clean_name: return '컨택'
    if '접수' in clean_name: return '접수'
    return clean_name

# =====================================================================
# [2단계] 핵심 매출 데이터 파싱 (오타 수정 및 에러 은폐 방지)
# =====================================================================
def parse_sales_data(uploaded_file):
    try:
        df_raw = pd.read_excel(uploaded_file, header=None).fillna("")
        header_rows = []
        anchor_c = -1
        
        # '구분' 기준점 스캔
        for r in range(min(50, len(df_raw))):
            for c in range(min(50, len(df_raw.columns))):
                if "구분" in clean_string(df_raw.iat[r, c]):
                    if r not in header_rows:
                        header_rows.append(r)
                        anchor_c = c
        
        if not header_rows:
            st.error("데이터 인식 실패: 엑셀 표에서 '구분' 항목을 찾을 수 없습니다. 양식을 확인해주세요.")
            return None
        records = []
        
        # 다중 표(2025, 2026) 순회
        for i, h_idx in enumerate(header_rows):
            end_idx = header_rows[i+1] if i + 1 < len(header_rows) else len(df_raw)
            block = df_raw.iloc[h_idx:end_idx]
            
            dates = {}
            fallback_y = datetime.now().year
            
            # 날짜 열 스캔 및 파싱
            for c in range(anchor_c + 1, len(df_raw.columns)):
                d_val = str(block.iat[0, c]).replace(" ", "").replace(".0", "")
                if not d_val or d_val == 'nan': continue
                
                nums = re.findall(r'\d+', d_val)
                if not nums: continue
                
                num_str = "".join(nums)
                y, m = -1, -1
                
                # 1. '202501' 처럼 6자리 숫자일 때 완벽 대응
                if len(num_str) >= 6:
                    y = int(num_str[:4])
                    m = int(num_str[4:6])
                # 2. '2025년 1월' 처럼 숫자가 떨어져 있을 때 (오타 수정 부분)
                elif len(nums) >= 2:
                    y = int(nums[0])
                    m = int(nums) # 이전 오타 디버깅 완료 반영
                # 3. '1월' 처럼 월만 적혀있을 때
                elif len(nums) == 1:
                    m = int(nums[0])
                    y = fallback_y
                
                # 날짜 최종 병합
                if y != -1 and m != -1:
                    if y < 100: y += 2000
                    if 2000 <= y <= 2100 and 1 <= m <= 12:
                        dates[c] = pd.Timestamp(y, m, 1)
                        fallback_y = y
            # 데이터가 추출되지 않으면 텅빈 하얀 화면 대신 에러를 띄우도록 원상복구
            if not dates:
                continue
            for r_idx in range(1, len(block)):
                metric = standardize_metric_name(block.iat[r_idx, anchor_c])
                if not metric: continue
                
                for c, dt in dates.items():
                    v_raw = str(block.iat[r_idx, c]).replace(",", "").strip()
                    v_num = re.sub(r'[^\d.-]', '', v_raw)
                    try:
                        val = float(v_num) if v_num and v_num != '-' else 0.0
                    except:
                        val = 0.0
                    records.append({'period': dt, 'metric': metric, 'value': val})
        # 하얀 빈 화면 방지 장치
        if not records:
            st.error("데이터 추출 실패: 연/월 날짜 형식 또는 유효한 수치 데이터를 찾지 못했습니다.")
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
        df_pivot['성공율'] = df_pivot.apply(lambda row: row['성공'] / row['접수'] if row.get('접수', 0) > 0 else 0.0, axis=1)
        
        return df_pivot
        
    except Exception as e:
        st.error(f"시스템 오류 발생: {str(e)}")
        st.code(traceback.format_exc())
        return None

# =====================================================================
# [3단계] CRM 데이터 처리 및 학술적 AI 리포트
# =====================================================================
def parse_crm_data(uploaded_file):
    try:
        crm_df = pd.read_excel(uploaded_file)
        crm_df.columns = [clean_string(col) for col in crm_df.columns]
        
        if '생년월일' in crm_df.columns:
            crm_df['생년월일'] = pd.to_datetime(crm_df['생년월일'], errors='coerce')
            crm_df = crm_df.dropna(subset=['생년월일']).copy()
            current_year = datetime.now().year
            crm_df['나이'] = current_year - crm_df['생년월일'].dt.year
            crm_df['연령대'] = (crm_df['나이'] // 10 * 10).astype(int).astype(str) + '대'
            
        for col in ['성별', '성공여부']:
            if col in crm_df.columns:
                crm_df[col] = crm_df[col].astype(str).apply(clean_string)
                
        date_col = next((c for c in crm_df.columns if '일' in c and ('가입' in c or '접수' in c or '등록' in c)), None)
        if date_col:
            crm_df['연도'] = pd.to_datetime(crm_df[date_col], errors='coerce').dt.year
        else:
            crm_df['연도'] = "전체 기간"
            
        return crm_df
    except Exception:
        return None

def generate_ai_analysis(df, selected_period, crm_df=None):
    current_data = df[df['period'] == selected_period]
    if current_data.empty or current_data.iloc[0]['접수'] == 0:
        return "⚠️ **선택하신 월의 실적 데이터가 존재하지 않거나 충분하지 않습니다.**"
        
    latest = current_data.iloc[0]
    
    # ----------------------------------------------------
    # [1단계] 실적 변동율 산출
    # ----------------------------------------------------
    prev_month_dt = latest['period'] - pd.DateOffset(months=1)
    prev_data_df = df[df['period'] == prev_month_dt]
    
    rec_val = latest['접수']
    success_rate = latest['성공율']
    rec_change_pct = 0.0
    rate_diff_p = 0.0
    
    if not prev_data_df.empty and prev_data_df.iloc[0]['접수'] > 0:
        prev = prev_data_df.iloc[0]
        rec_change_pct = (rec_val - prev['접수']) / prev['접수']
        rate_diff_p = (success_rate - prev['성공율']) * 100
    
    # 국면 진단 기준 세분화
    if rec_change_pct >= 0.15: rec_state = "폭증"
    elif rec_change_pct >= 0.02: rec_state = "성장"
    elif -0.05 <= rec_change_pct < 0.02: rec_state = "정체"
    elif -0.15 <= rec_change_pct < -0.05: rec_state = "감소"
    else: rec_state = "급락"
        
    if rate_diff_p >= 3.0: rate_state = "급증"
    elif rate_diff_p >= 0.5: rate_state = "개선"
    elif -0.5 <= rate_diff_p < 0.5: rate_state = "유지"
    elif -3.0 <= rate_diff_p < -0.5: rate_state = "하락"
    else: rate_state = "급락"

    # ----------------------------------------------------
    # [2단계] 학술 매핑 및 단도직입 처방 매트릭스
    # ----------------------------------------------------
    if rec_state in ["폭증", "성장"] and rate_state in ["급증", "개선"]:
        theory = "LTV/CAC 극대화 모델"
        key_issue = f"신규 유입({rec_state})과 효율({rate_state})이 동시에 올라가는 최고의 성장 사이클입니다."
        one_line_action = "🚨 **우수 채널에 즉각 추가 광고 예산을 배정하여 점유율을 독식하십시오.**"
        detail_action = "- 획득 가치(LTV)가 획득 비용(CAC)보다 압도적으로 높은 시기이므로 소극적 예산 통제를 지양할 것.\n- 성과가 가장 잘 나오는 고소득층 타겟 대상 크로스셀링 캠페인 동시 기획."
    
    elif rec_state in ["폭증", "성장"] and rate_state in ["하락", "급락"]:
        theory = "전환 퍼널(Funnel) 보틀넥 최적화"
        key_issue = f"광고 유입({rec_state})은 잘 되나, 내부 전환 효율({rate_state})이 무너져 유실이 발생하고 있습니다."
        one_line_action = "🚨 **신규 마케팅을 일시 중단하고, 접수→상담 퍼널의 병목 구간을 수리하십시오.**"
        detail_action = "- 유입된 가입 기대 수준에 비해 상담 스크립트나 조건 혜택 설계에 괴리가 있는지 점검 필요.\n- 콜 인센티브 구조 및 가입 신청 페이지의 UI 이탈 마찰력을 줄이는 작업 선행."
    
    elif rec_state in ["감소", "급락"] and rate_state in ["급증", "개선"]:
        theory = "파레토 관계 마케팅 (80/20 법칙)"
        key_issue = f"총 유입량({rec_state})은 축소되었으나, 선별된 정예 고객의 전환율({rate_state})은 상승했습니다."
        one_line_action = "🚨 **비효율 대중 광고를 끊고, 우수 성공 고객의 '유사 프로필 타겟팅'으로 전환하십시오.**"
        detail_action = "- 불특정 다수 타겟팅보다 우수 성공 이력을 기반으로 한 유사 타겟(Look-alike) 광고 소스 집중 분배.\n- 렌탈 객단가가 높은 프리미엄 모델 패키지 중심으로 상품 믹스 전략 재조정."
    
    elif rec_state in ["감소", "급락"] and rate_state in ["하락", "급락"]:
        theory = "손실 회피(Loss Aversion) 및 넛지"
        key_issue = f"유입량({rec_state})과 품질 효율({rate_state})이 동반 둔화되는 비즈니스 침체 국면입니다."
        one_line_action = "🚨 **고객의 금전적 위약금 장벽과 해지 저항감을 없애는 파격 제안을 검토하십시오.**"
        detail_action = "- '첫 달 무료 렌탈 케어' 또는 '중도 해약금 면제 보장 기간 설정' 등 행동경제학적 넛지 배치 필요.\n- 초기 설치비 면제 등 가입 장벽을 완전히 허물어 심리적 진입로를 재확보할 것."
    
    else: # 정체 및 유지
        theory = "STP 마이크로 세분화 이론"
        key_issue = "수치 변동이 극히 미미하고 고착화되어 비즈니스 활력이 고갈된 상태입니다."
        one_line_action = "🚨 **기존 성별/연령 구분을 넘어서 '라이프스타일' 맞춤형 신규 세그먼트를 개척하십시오.**"
        detail_action = "- 기존 상담 리스트의 유선 접촉 시간대, 주거 환경 분석 등을 통합한 마이크로 세분화 실행.\n- '1인 가구', '반려동물 가구' 등 렌탈 목적에 맞춘 세일즈 포지셔닝 타겟 재설정."

    # ----------------------------------------------------
    # [3단계] UI 가독성 극대화 리포트 구성 (마크다운)
    # ----------------------------------------------------
    analysis_texts = []
    analysis_texts.append(f"### 📊 {latest['period'].strftime('%Y년 %m월')} 비즈니스 진단 리포트")
    
    # 1. 단도직입 핵심 Action
    analysis_texts.append(f"### 💡 핵심 권장 Action\n{one_line_action}")
    analysis_texts.append("\n---")

    # 2. 일목요연 요약 매트릭스 테이블
    table_summary = (
        f"| 구분 | 분석 결과 및 진단 내용 |\n"
        f"|---|---|\n"
        f"| **📈 현재 모객 국면** | 유입 `[{rec_state}]` (전월비 {rec_change_pct:+.1%}) |\n"
        f"| **🎯 세일즈 효율** | 성공율 `[{rate_state}]` (전월비 {rate_diff_p:+.1f}%p) |\n"
        f"| **🔬 추천 학술 모델** | `{theory}` |\n"
        f"| **⚠️ 핵심 발견 문제** | {key_issue} |"
    )
    analysis_texts.append(table_summary)
    analysis_texts.append("\n---")
    
    # 3. 상세 처방전
    analysis_texts.append(f"### 📋 세부 처방 가이드\n{detail_action}")
    
    # 4. CRM 연동 코호트가 있을 경우 간결하게 추가
    if crm_df is not None and all(c in crm_df.columns for c in ['성공여부', '연령대', '성별', '연도']):
        analysis_texts.append("\n---\n### 👥 CRM 코호트 핵심 요약")
        
        table_crm = "| 연도 | 최고 전환 세그먼트 | 최저 전환 세그먼트 | 해결을 위한 집중 Action 플랜 |\n|---|---|---|---|\n"
        years = sorted([y for y in crm_df['연도'].unique() if pd.notna(y)])
        
        for y in years:
            y_df = crm_df[crm_df['연도'] == y]
            if y_df.empty: continue
            
            stats = y_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean())
            stats = stats.sort_values(ascending=False)
            
            if not stats.empty and len(stats) >= 1:
                best = stats.index[0]
                best_rate = stats.iloc[0] * 100
                worst = stats.index[-1]
                worst_rate = stats.iloc[-1] * 100
                
                best_gender = best if str(best).endswith('성') else f"{best}성"
                worst_gender = worst if str(worst).endswith('성') else f"{worst}성"
                
                # 심플 액션 매핑
                if "20대" in worst[0]:
                    action_plan = "모바일 계약서 간소화 (Friction 최저화)"
                elif "50대" in worst[0] or "60대" in worst[0]:
                    action_plan = "시니어 전담 케어 콜 및 종이 안내장 병행"
                else:
                    action_plan = "연령 맞춤형 요금 결합 혜택 제시"
                
                y_label = f"{int(y)}년" if isinstance(y, (int, float)) else str(y)
                table_crm += f"| **{y_label}** | {best[0]} {best_gender} ({best_rate:.1f}%) | {worst[0]} {worst_gender} ({worst_rate:.1f}%) | {action_plan} |\n"
                
        analysis_texts.append(table_crm)
            
    return "\n".join(analysis_texts)


# =====================================================================
# [4단계] 대시보드 UI 및 차트 구성
# =====================================================================
st.set_page_config(layout="wide", page_title="현대렌탈케어 고객만족센터 매출관리 대시보드")
apply_custom_css()
st.title("현대렌탈케어 고객만족센터 매출관리 대시보드")
st.markdown("---")
st.sidebar.header("데이터 업로드")
sales_file = st.sidebar.file_uploader("1. 매출 데이터 (필수)", type=["xlsx", "xls"])
crm_file = st.sidebar.file_uploader("2. CRM 데이터 (선택)", type=["xlsx", "xls"])

if sales_file:
    df = parse_sales_data(sales_file)
    crm_df = parse_crm_data(crm_file) if crm_file else None
    
    if df is not None and not df.empty:
        valid_periods = df[df['접수'] > 0]['period']
        default_period = valid_periods.max() if not valid_periods.empty else df['period'].max()
        
        available_years = sorted(df['period'].dt.year.unique().tolist())
        months = list(range(1, 13))
        
        st.markdown("#### 조회 기준월 설정")
        m_col1, m_col2, _ = st.columns([1.5, 1.5, 7])
        
        with m_col1:
            sel_main_y = st.selectbox("기준 연도", options=available_years, index=available_years.index(default_period.year), format_func=lambda x: f"{x}년", key="main_y")
        with m_col2:
            sel_main_m = st.selectbox("기준 월", options=months, index=months.index(default_period.month), format_func=lambda x: f"{x}월", key="main_m")
            
        selected_period = pd.to_datetime(f"{sel_main_y}-{sel_main_m}-01")
        current_data_df = df[df['period'] == selected_period]
        
        if current_data_df.empty or current_data_df.iloc[0]['접수'] == 0:
            latest_data = pd.Series({'접수':0, '컨택':0, '성공':0, '성공율':0.0, '설치완료':0})
            st.warning("선택하신 월의 데이터가 없어 0으로 표기됩니다.")
        else:
            latest_data = current_data_df.iloc[0]
            
        prev_period = selected_period - pd.DateOffset(months=1)
        prev_data_df = df[df['period'] == prev_period]
        prev_data = prev_data_df.iloc[0] if not prev_data_df.empty else None
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.expander(f"{sel_main_y}년 {sel_main_m}월 핵심 성과 지표", expanded=True):
            kpi_cols = st.columns(4)
            for col, metric in zip(kpi_cols, ['접수', '컨택', '성공', '성공율']):
                val = latest_data.get(metric, 0)
                delta = val - prev_data[metric] if prev_data is not None else 0
                
                if metric == '성공율': col.metric(metric, f"{val:.1%}", f"{delta*100:+.1f}%p")
                else: col.metric(f"{metric} (건)", f"{val:,.0f}", f"{delta:+.0f}")
                    
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2 = st.columns([3.5, 6.5])
        
        with col1:
            with st.expander("데이터 분석 리포트", expanded=True):
                st.markdown(generate_ai_analysis(df, selected_period, crm_df))
                
                st.markdown("<br><b>연도별 최고 실적 현황 (성공율 기준)</b>", unsafe_allow_html=True)
                df['year'] = df['period'].dt.year
                df_valid = df[df['성공율'] > 0]
                if not df_valid.empty:
                    best_per_year = df_valid.loc[df_valid.groupby('year')['성공율'].idxmax()]
                    for _, row in best_per_year.iterrows():
                        st.info(f"{row['year']}년 최고 실적: {row['period'].strftime('%m월')} (성공율 {row['성공율']:.1%})")
        with col2:
            with st.expander("지표별 트렌드 분석 (시각화)", expanded=True):
                vis_col1, vis_col2 = st.columns(2)
                with vis_col1:
                    target_metric = st.selectbox("분석 지표 커스터마이징", ['설치완료', '접수', '컨택', '성공', '성공율'])
                with vis_col2:
                    chart_type = st.radio("그래프 형태 선택", ["막대 그래프", "꺾은선형 그래프"], horizontal=True)
                    
                st.markdown("<br><b>차트 조회 기간 설정</b>", unsafe_allow_html=True)
                start_d, end_d = df['period'].min(), df['period'].max()
                
                sc1, sc2, sc3, sc4 = st.columns(4)
                with sc1: start_y = st.selectbox("시작 연도", options=available_years, index=0, format_func=lambda x: f"{x}년", key="c_sy")
                with sc2: start_m = st.selectbox("시작 월", options=months, index=months.index(start_d.month) if start_y == start_d.year else 0, format_func=lambda x: f"{x}월", key="c_sm")
                with sc3: end_y = st.selectbox("종료 연도", options=available_years, index=len(available_years)-1, format_func=lambda x: f"{x}년", key="c_ey")
                with sc4: end_m = st.selectbox("종료 월", options=months, index=months.index(end_d.month) if end_y == end_d.year else 11, format_func=lambda x: f"{x}월", key="c_em")
                    
                start_p = pd.to_datetime(f"{start_y}-{start_m}-01")
                end_p = pd.to_datetime(f"{end_y}-{end_m}-01")
                
                if start_p > end_p:
                    st.warning("시작 연/월이 종료 연/월보다 늦을 수 없습니다.")
                else:
                    chart_df = df[(df['period'] >= start_p) & (df['period'] <= end_p)].copy()
                    chart_df = chart_df[chart_df[target_metric] > 0]
                    
                    if not chart_df.empty:
                        chart_df['조회월'] = chart_df['period'].dt.strftime('%y년 ') + chart_df['period'].dt.month.astype(str) + '월'
                        if target_metric == '성공율': chart_df[target_metric] = chart_df[target_metric] * 100
                        if chart_type == "막대 그래프":
                            fig = px.bar(chart_df, x='조회월', y=target_metric, text=target_metric)
                            fig.update_traces(texttemplate='%{text:.1f}' if target_metric == '성공율' else '%{text:,.0f}', textposition='outside', marker_color='#1E88E5', textfont_size=13, cliponaxis=False)
                        else:
                            fig = px.line(chart_df, x='조회월', y=target_metric, markers=True, text=target_metric)
                            fig.update_traces(line=dict(width=3, color='#1E88E5'), marker=dict(size=8, color='#2C3E50'), texttemplate='%{text:.1f}' if target_metric == '성공율' else '%{text:,.0f}', textposition="top center", textfont_size=13, cliponaxis=False)
                            
                        max_val = chart_df[target_metric].max()
                        y_max_range = max_val * 1.2 if max_val > 0 else 1.0
                        fig.update_layout(
                            plot_bgcolor='rgba(255,255,255,1)', paper_bgcolor='rgba(255,255,255,1)', xaxis_title="", yaxis_title="",  
                            margin=dict(l=10, r=10, t=70, b=10),
                            xaxis=dict(showgrid=False, tickangle=-45, type='category', categoryorder='array', categoryarray=chart_df['조회월']),
                            yaxis=dict(showgrid=True, gridcolor='#F0F0F0', range=[0, y_max_range]),
                            annotations=[dict(x=0, y=1.15, xref='paper', yref='paper', text=f"<b>{target_metric}</b> {'(%)' if target_metric == '성공율' else '(건)'}", showarrow=False, font=dict(size=14, color='#555555'), xanchor='left', yanchor='bottom')]
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("해당 기간에 차트를 구성할 데이터가 없습니다.")
        
        with st.expander("데이터 원본 표 확인", expanded=False):
            display_df = df.drop(columns=['year'], errors='ignore').copy()
            display_df['조회월'] = display_df['period'].dt.strftime('%Y-%m')
            st.dataframe(display_df.set_index('조회월').drop(columns=['period']).style.format({"성공율": "{:.2%}", "접수": "{:.0f}", "컨택": "{:.0f}", "성공": "{:.0f}", "설치완료": "{:.0f}"}))
            
    else:
        pass
else:
    st.info("좌측 메뉴에서 매출 데이터를 업로드하여 대시보드를 시작해주십시오.")
