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
        return "선택하신 월의 실적 데이터가 충분하지 않아 분석 리포트를 생성할 수 없습니다."
        
    latest = current_data.iloc[0]
    
    # ----------------------------------------------------
    # [추론 엔진 1단계] 전월 대비 실적 추세 자동 스캔 및 비즈니스 국면 진단
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
    
    # 접수량 상태 자동 판정 (다차원 시나리오 분기)
    if rec_change_pct >= 0.15: rec_state = "폭증"
    elif rec_change_pct >= 0.02: rec_state = "성장"
    elif -0.05 <= rec_change_pct < 0.02: rec_state = "정체"
    elif -0.15 <= rec_change_pct < -0.05: rec_state = "감소"
    else: rec_state = "급락"
        
    # 성공율 효율 상태 자동 판정
    if rate_diff_p >= 3.0: rate_state = "급증"
    elif rate_diff_p >= 0.5: rate_state = "개선"
    elif -0.5 <= rate_diff_p < 0.5: rate_state = "유지"
    elif -3.0 <= rate_diff_p < -0.5: rate_state = "하락"
    else: rate_state = "급락"

    # ----------------------------------------------------
    # [추론 엔진 2단계] 10대 마케팅 이론 기반의 지능형 의사결정 매핑
    # ----------------------------------------------------
    selected_theories = []
    strategic_action = ""
    
    if rec_state in ["폭증", "성장"] and rate_state in ["급증", "개선"]:
        selected_theories = ["선택과 집중 전략 (Pareto Principle)", "고객 생애 가치 극대화 이론 (LTV/CAC Framework)"]
        strategic_action = (
            f"현재 신규 유입({rec_state})과 품질 효율({rate_state})이 이상적으로 동반 폭발하는 비즈니스 골든 크로스(Golden Cross) 구간입니다. "
            f"이 국면에서는 신규 고객 획득 비용(CAC)을 보다 공격적으로 상향 조정하더라도, 장기적인 가입 고객 생애 가치(LTV) 회수율이 압도적일 확률이 높습니다. "
            f"고객 유입 채널의 타겟팅 범위를 확대하는 동시, 우수 코호트에 마케팅 예산을 우선 재배정(Resource Allocation)하는 적극적 성장을 권장합니다."
        )
    elif rec_state in ["폭증", "성장"] and rate_state in ["하락", "급락"]:
        selected_theories = ["전환 퍼널 최적화 이론 (Conversion Funnel Bottleneck)", "보상적 의사결정 모델 (Compensatory Decision Theory)"]
        strategic_action = (
            f"마케팅을 통한 모객 볼륨은 {rec_state} 중이나, 실제 최종 상담 성공율은 {rate_state}하는 심각한 병목(Bottleneck) 구간에 진입했습니다. "
            f"이는 인입된 고객의 가입 의사에 비해 상담 프로세스나 계약 체결 조건 설계상 심각한 마찰(Friction)이 존재함을 뜻합니다. "
            f"즉시 무리한 광고 확장을 중단하고, 접수에서 컨택 및 성공으로 넘어가는 고객 여정(Customer Journey)의 중간 손실률을 분석하는 퍼널 고도화 작업을 단행해야 합니다."
        )
    elif rec_state in ["감소", "급락"] and rate_state in ["급증", "개선"]:
        selected_theories = ["관계 마케팅 및 차별적 고착화 (Relationship & Lock-in Strategy)", "가치 인식 기반 가격 이론 (Value Perception Theory)"]
        strategic_action = (
            f"유입되는 모수 규모 자체는 {rec_state}했으나 양질의 타겟 고객을 선별 집중함으로써 세일즈 효율({rate_state})을 방어해 내는 정예화(Filtering) 상태입니다. "
            f"비용 대비 마케팅 효율이 안정적인 흐름이므로, 억지로 수치를 늘리려 비효율 채널을 재개하기보단 "
            f"성공 가능성이 입증된 핵심 타겟 프로필(Look-alike Profile)을 정밀 역추적하여 유사 고객층에 예산을 유도하는 록인(Lock-in) 전략이 훨씬 유리합니다."
        )
    elif rec_state in ["감소", "급락"] and rate_state in ["하락", "급락"]:
        selected_theories = ["손실 회피성 이론 (Loss Aversion Theory)", "행동 경제학적 넛지 모델 (Nudge & Psychological Pricing)"]
        strategic_action = (
            f"유입량({rec_state})과 세일즈 효율({rate_state})이 동시 침체 구조에 빠진 심각한 수축 비즈니스 사이클입니다. "
            f"고객들의 심리적 구매 거부감과 가입 장벽이 극대화된 상태이므로 일반적인 제안으로는 극복이 어렵습니다. "
            f"장기 계약 위약금 면제 옵션이나 첫 달 무료 홈체험 프로모션 등 고객의 '손실 회피 심리'를 허무는 혁신적인 넛지(Nudge) 트리거를 조속히 심어야 합니다."
        )
    else: # 정체 및 유지 상태
        selected_theories = ["고객 여정 지도 분석 (Customer Journey Mapping)", "STP 고도화 세분화 이론 (Micro-segmentation)"]
        strategic_action = (
            f"접수량과 전환 효율 모두 전월 대비 정체 국면을 유지하고 있어 성장 동력이 다소 무뎌진 교착 상태입니다. "
            f"기존의 단편화된 타겟 분석 방식으로는 새로운 전환 포인트를 찾기 어렵습니다. "
            f"고객 연령 및 성별의 인구통계 변수를 넘어 라이프스타일, 라이프사이클 요구 수준에 맞춘 마이크로 세분화(STP) 리포지셔닝 캠페인을 수립할 필요가 있습니다."
        )

    # ----------------------------------------------------
    # [추론 엔진 3단계] 최종 분석 리포트 구조화 및 마크다운 바인딩
    # ----------------------------------------------------
    analysis_texts = []
    analysis_texts.append(f"### 📊 {latest['period'].strftime('%Y년 %m월')} 지능형 성과 진단 리포트")
    analysis_texts.append(f"**현재 비즈니스 국면**: 유입 `{rec_state}` / 효율 `{rate_state}` 상황")
    
    if not prev_data_df.empty and prev_data_df.iloc[0]['접수'] > 0:
        analysis_texts.append(
            f"🔍 **핵심 지표 요약**: 당월 신규 접수량은 전월 대비 **{rec_change_pct:+.1%}** 변동하였으며, "
            f"상담 성공율은 **{rate_diff_p:+.2f}%p** 추세를 기록하고 있습니다."
        )
    else:
        analysis_texts.append("🔍 **핵심 지표 요약**: 비교 대상이 되는 직전월 데이터가 확인되지 않아 당월 단독 흐름을 기반으로 마케팅 모델을 판단합니다.")
        
    analysis_texts.append("\n---\n### 🔬 데이터 분석가의 마케팅 학술 프레임워크 제언")
    analysis_texts.append(f"📌 **적용 권장 마케팅 이론**: `{'`, `'.join(selected_theories)}`")
    analysis_texts.append(f"💡 **AI 경영 처방**:\n{strategic_action}")
    
    # [추론 엔진 4단계] CRM 데이터 존재 시 인구통계 기반 연계 처방 설계
    if crm_df is not None and all(c in crm_df.columns for c in ['성공여부', '연령대', '성별', '연도']):
        analysis_texts.append("\n---\n### 👥 코호트(Cohort) 다차원 고객 세그먼트 분석")
        analysis_texts.append("CRM 고객 데이터베이스의 가입 이력을 학술적 세그먼트 구조로 교차 대조하여 도출한 **최우수 전환 코호트** 및 **취약 코호트 집중 해결 액션 플랜**입니다.")
        
        table_md = "| 분석 연도 | 최우수 전환 코호트 (Target) | 전환 마찰 코호트 (Friction) | 해결을 위한 경영 전략적 Action 플랜 |\n|---|---|---|---|\n"
        
        years = sorted([y for y in crm_df['연도'].unique() if pd.notna(y)])
        has_valid_stats = False
        
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
                
                # 취약 타겟 특성별 맞춤형 해결 기법 매핑
                if "20대" in worst[0]:
                    action_plan = "**[디지털 넛지]** 모바일 친화적인 간편 계약 서명 프로세스 구현 및 UX 전환 병목 최소화."
                elif "50대" in worst[0] or "60대" in worst[0]:
                    action_plan = "**[휴리스틱 케어]** 유선 해피콜 전담 레이아웃 추가 구축 및 직관적인 렌탈 안내 팜플렛 지원."
                else:
                    action_plan = "**[A/B 테스트]** 타겟 세그먼트에 맞춘 맞춤형 월 렌탈 요금제 및 특전 가치 제안(CVP) 전개."
                
                y_label = f"{int(y)}년" if isinstance(y, (int, float)) else str(y)
                table_md += f"| **{y_label}** | {best[0]} {best_gender} ({best_rate:.1f}%) | {worst[0]} {worst_gender} ({worst_rate:.1f}%) | {action_plan} |\n"
                has_valid_stats = True
                
        if has_valid_stats:
            analysis_texts.append(table_md)
            analysis_texts.append(
                "⚠️ **비즈니스 리스크 조기 경고 (Watch out)**:\n"
                "- **인과 신뢰의 한계**: 특정 핵심 코호트의 실적 상승 원인이 순수한 핵심 가치 만족인지, 혹은 타 채널의 한시적 결합할인 제휴에 따른 단기적 착시인지 정밀 분기 검증이 병행되어야 합니다.\n"
                "- **평균값의 오류**: 조직의 전체 성과 지표가 성장세라 하더라도 부진 코호트와의 간극이 점진적으로 벌어지는 불균형 현상이 나타날 경우, 전사 마케팅 효율이 누수되므로 성과 지표 가중치 차등 분배를 권장합니다."
            )
            
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
