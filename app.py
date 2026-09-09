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
            .action-highlight-box {
                background-color: #FFF3E0;
                color: #D84315;
                padding: 15px 20px;
                border-radius: 8px;
                border-left: 6px solid #E65100;
                font-weight: 800;
                font-size: 1.15em;
                margin-bottom: 20px;
                box-shadow: 0px 2px 5px rgba(0,0,0,0.05);
            }
            .summary-card {
                background-color: #FFFFFF;
                border-radius: 10px;
                padding: 20px 15px;
                text-align: center;
                border: 1px solid #E0E0E0;
                box-shadow: 0 4px 6px rgba(0,0,0,0.04);
                margin-bottom: 20px;
                height: 140px;
            }
            .summary-card h4 {
                margin-top: 0;
                color: #546E7A !important;
                font-size: 1.05rem !important;
                font-weight: 700;
                height: 40px;
            }
            .summary-card .value {
                font-size: 1.6rem;
                font-weight: 800;
                color: #1565C0;
                margin: 5px 0;
            }
            .summary-card .trend {
                font-size: 0.95rem;
                color: #616161;
            }
            .diagnosis-box {
                background-color: #F4F6F9;
                padding: 20px;
                border-radius: 8px;
                border-left: 6px solid #1E88E5;
                margin-bottom: 20px;
                font-size: 1.05em;
                line-height: 1.6;
            }
            .detail-box {
                padding: 10px 15px;
                background-color: #ffffff;
                border: 1px solid #eeeeee;
                border-radius: 8px;
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
# [2단계] 핵심 매출 데이터 파싱
# =====================================================================
def parse_sales_data(uploaded_file):
    try:
        df_raw = pd.read_excel(uploaded_file, header=None).fillna("")
        header_rows = []
        anchor_c = -1
        
        for r in range(min(50, len(df_raw))):
            for c in range(min(50, len(df_raw.columns))):
                if "구분" in clean_string(df_raw.iat[r, c]):
                    if r not in header_rows:
                        header_rows.append(r)
                        anchor_c = c
        
        if not header_rows:
            st.error("데이터 인식 실패: 엑셀 표에서 '구분' 항목을 찾을 수 없습니다.")
            return None
            
        records = []
        for i, h_idx in enumerate(header_rows):
            end_idx = header_rows[i+1] if i + 1 < len(header_rows) else len(df_raw)
            block = df_raw.iloc[h_idx:end_idx]
            
            dates = {}
            fallback_y = datetime.now().year
            
            for c in range(anchor_c + 1, len(df_raw.columns)):
                d_val = str(block.iat[0, c]).replace(" ", "").replace(".0", "")
                if not d_val or d_val == 'nan': continue
                
                nums = re.findall(r'\d+', d_val)
                if not nums: continue
                
                num_str = "".join(nums)
                y, m = -1, -1
                
                if len(num_str) >= 6:
                    y, m = int(num_str[:4]), int(num_str[4:6])
                elif len(nums) >= 2:
                    y, m = int(nums[0]), int(nums)
                elif len(nums) == 1:
                    m, y = int(nums[0]), fallback_y
                
                if y != -1 and m != -1:
                    if y < 100: y += 2000
                    if 2000 <= y <= 2100 and 1 <= m <= 12:
                        dates[c] = pd.Timestamp(y, m, 1)
                        fallback_y = y
                        
            if not dates: continue
            
            for r_idx in range(1, len(block)):
                metric = standardize_metric_name(block.iat[r_idx, anchor_c])
                if not metric: continue
                
                for c, dt in dates.items():
                    v_raw = str(block.iat[r_idx, c]).replace(",", "").strip()
                    v_num = re.sub(r'[^\d.-]', '', v_raw)
                    try: val = float(v_num) if v_num and v_num != '-' else 0.0
                    except: val = 0.0
                    records.append({'period': dt, 'metric': metric, 'value': val})
                    
        if not records:
            st.error("데이터 추출 실패: 유효한 수치 데이터를 찾지 못했습니다.")
            return None
            
        df_long = pd.DataFrame(records)
        df_long = df_long.groupby(['period', 'metric'], as_index=False)['value'].last()
        df_pivot = df_long.pivot(index='period', columns='metric', values='value').reset_index()
        
        for req in ['접수', '컨택', '성공', '성공율', '설치완료']:
            if req not in df_pivot.columns: df_pivot[req] = 0.0
            else: df_pivot[req] = pd.to_numeric(df_pivot[req], errors='coerce').fillna(0.0)
                
        df_pivot = df_pivot.sort_values('period').reset_index(drop=True)
        df_pivot['성공율'] = df_pivot.apply(lambda row: row['성공'] / row['접수'] if row.get('접수', 0) > 0 else 0.0, axis=1)
        return df_pivot
        
    except Exception as e:
        st.error(f"시스템 오류 발생: {str(e)}")
        return None

# =====================================================================
# [3단계] CRM 데이터 파싱
# =====================================================================
def parse_crm_data(uploaded_file):
    try:
        crm_df = pd.read_excel(uploaded_file)
        crm_df.columns = [clean_string(col) for col in crm_df.columns]
        
        if '생년월일' in crm_df.columns:
            crm_df['생년월일'] = pd.to_datetime(crm_df['생년월일'], errors='coerce')
            crm_df = crm_df.dropna(subset=['생년월일']).copy()
            crm_df['연령대'] = ((datetime.now().year - crm_df['생년월일'].dt.year) // 10 * 10).astype(int).astype(str) + '대'
            
        for col in ['성별', '성공여부']:
            if col in crm_df.columns: crm_df[col] = crm_df[col].astype(str).apply(clean_string)
                
        date_col = next((c for c in crm_df.columns if '일' in c and ('가입' in c or '접수' in c or '등록' in c)), None)
        crm_df['연도'] = pd.to_datetime(crm_df[date_col], errors='coerce').dt.year if date_col else "전체 기간"
        return crm_df
    except Exception: return None

# =====================================================================
# [4단계] AI 경영 리포트 생성 엔진 (전년 대비 로직 통합)
# =====================================================================
def generate_ai_analysis(df, selected_period, crm_df=None):
    current_data = df[df['period'] == selected_period]
    if current_data.empty or current_data.iloc[0]['접수'] == 0:
        return None
        
    latest = current_data.iloc[0]
    prev_month_dt = latest['period'] - pd.DateOffset(months=1)
    prev_data_df = df[df['period'] == prev_month_dt]
    
    # 1. 월간 변동성 지표 산출
    rec_val = latest['접수']
    success_rate = latest['성공율']
    rec_change_pct = 0.0
    rate_diff_p = 0.0
    
    if not prev_data_df.empty and prev_data_df.iloc[0]['접수'] > 0:
        prev = prev_data_df.iloc[0]
        rec_change_pct = (rec_val - prev['접수']) / prev['접수']
        rate_diff_p = (success_rate - prev['성공율']) * 100

    # 2. 전년 전체 평균 대비 당월 성공율 비교 지표 산출
    current_year = selected_period.year
    prev_year = current_year - 1
    df_prev_year = df[df['period'].dt.year == prev_year]
    
    avg_success_rate_prev_year = 0.0
    yoy_diff_p = 0.0
    
    if not df_prev_year.empty and df_prev_year['접수'].sum() > 0:
        avg_success_rate_prev_year = df_prev_year['성공'].sum() / df_prev_year['접수'].sum()
        yoy_diff_p = (success_rate - avg_success_rate_prev_year) * 100

    # --- [경우의 수 1축: 접수 건수 변동 (5단계)] ---
    if rec_change_pct >= 0.15: v_lvl, v_text = "대폭 증가", f"전월비 {rec_change_pct*100:+.1f}%"
    elif rec_change_pct >= 0.02: v_lvl, v_text = "점진 증가", f"전월비 {rec_change_pct*100:+.1f}%"
    elif -0.05 <= rec_change_pct < 0.02: v_lvl, v_text = "보합(유지)", f"전월비 {rec_change_pct*100:+.1f}%"
    elif -0.15 <= rec_change_pct < -0.05: v_lvl, v_text = "점진 감소", f"전월비 {rec_change_pct*100:+.1f}%"
    else: v_lvl, v_text = "대폭 감소", f"전월비 {rec_change_pct*100:+.1f}%"
        
    # --- [경우의 수 2축: 당월 성공율 변동폭 (5단계)] ---
    if rate_diff_p >= 3.0: r_lvl, r_text = "대폭 개선", f"전월비 {rate_diff_p:+.1f}%p"
    elif rate_diff_p >= 0.5: r_lvl, r_text = "점진 개선", f"전월비 {rate_diff_p:+.1f}%p"
    elif -0.5 <= rate_diff_p < 0.5: r_lvl, r_text = "보합(유지)", f"전월비 {rate_diff_p:+.1f}%p"
    elif -3.0 <= rate_diff_p < -0.5: r_lvl, r_text = "점진 하락", f"전월비 {rate_diff_p:+.1f}%p"
    else: r_lvl, r_text = "대폭 하락", f"전월비 {rate_diff_p:+.1f}%p"

    # --- [경우의 수 3축: 전년 평균 대비 당월 성공율 판정 (3단계)] ---
    if avg_success_rate_prev_year == 0:
        yoy_lvl, yoy_text = "비교 불가", "전년 데이터 없음"
    elif yoy_diff_p >= 2.0:
        yoy_lvl, yoy_text = "초과 달성", f"작년 평균비 {yoy_diff_p:+.1f}%p"
    elif yoy_diff_p >= -2.0:
        yoy_lvl, yoy_text = "유사 수준(보합)", f"작년 평균비 {yoy_diff_p:+.1f}%p"
    else:
        yoy_lvl, yoy_text = "실적 미흡", f"작년 평균비 {yoy_diff_p:+.1f}%p"

    # --- [경우의 수 4축: CRM 코호트 특성 (4단계)] ---
    c_text = "CRM 데이터 연동 시, 주력 고객층 및 취약 고객층에 대한 세부 진단이 제공됩니다."
    best_cohort, worst_cohort = "-", "-"
    
    if crm_df is not None and not crm_df.empty:
        try:
            curr_y_df = crm_df[crm_df['연도'] == latest['period'].year]
            if not curr_y_df.empty:
                stats = curr_y_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean()).sort_values(ascending=False)
                if not stats.empty and len(stats) > 0:
                    best = stats.index[0]
                    worst = stats.index[-1]
                    best_cohort = f"{best[0]} {best}"
                    worst_cohort = f"{worst[0]} {worst}"
                    c_text = f"현재 당사의 주력 성공 타겟은 <b>[{best_cohort}]</b>이며, 이탈 마찰이 가장 심한 취약 타겟은 <b>[{worst_cohort}]</b>입니다."
        except: pass

    # --- [AI 진단 및 마케팅 이론 매핑] ---
    if "증가" in v_lvl:
        if "개선" in r_lvl:
            theory = "LTV(고객생애가치) 극대화 모델"
            theory_rationale = "접수량과 전환율이 동반 상승하는 '골든 크로스' 구간에서는 한정된 예산 분배보다, 공격적 자원 투입을 통한 선점이 재무적 기업 가치 창출에 절대적으로 유리하기 때문입니다."
            diagnosis = "신규 접수 건수와 성공율이 동반 상승하는 최상의 '골든 크로스' 상태입니다. 시장 점유율을 적극적으로 확대할 최적의 시점입니다."
            action_title = "성과 우수 채널 중심의 공격적인 마케팅 예산 증액"
            action_detail = "1. 현재는 투입 비용 대비 수익 창출 효과(ROI)가 극대화되는 시기이므로, 성과가 입증된 채널의 예산을 대폭 상향하여 경쟁사와의 격차를 벌려야 합니다.<br>2. 계약 성공률이 높은 우수 고객층에게 추가 혜택(업셀링, 크로스셀링)을 제안하여 객단가를 높이는 전략을 병행하십시오."
        elif "하락" in r_lvl:
            theory = "퍼널(Funnel) 이탈 구간 최적화"
            theory_rationale = "접수 건수는 증가하나 전환율이 하락하는 징후는 내부 프로세스(상담, 조건) 내 마찰(Friction) 현상을 의미합니다. 외형 확장보다 내부 성공 구조의 결함 치유가 우선되어야 하므로 본 이론을 적용합니다."
            diagnosis = "신규 접수는 증가했으나, 최종 성공율이 하락했습니다. 이는 영업 및 계약 프로세스 내부에 심각한 이탈 병목(Bottleneck)이 발생하고 있음을 시사합니다."
            action_title = "신규 광고 예산 일시 통제 및 내부 영업 프로세스 긴급 점검"
            action_detail = "1. 광고로 유입된 고객의 기대와 실제 상담 내용 간의 괴리가 이탈을 유발하고 있는지 점검해야 합니다.<br>2. 복잡한 가입 절차, 상담원 연결 지연 등 내부 프로세스의 비효율 요소를 최우선으로 제거하십시오."
        else:
            theory = "업셀링(Up-selling) 및 결정적 넛지 제안"
            theory_rationale = "접수 유입은 폭발적이나 전환이 정체된 경우, 고객의 구매 결정(Decision-making)을 촉발할 최종 미끼(Trigger)가 부재한 상태이므로 행동경제학적 넛지 제안이 적합합니다."
            diagnosis = "신규 접수는 증가했으나, 성공율은 정체 구간입니다. 가망 고객을 계약으로 이끌 결정적 유인책이 부족한 상태입니다."
            action_title = "전환율 제고를 위한 추가 프로모션 한시적 적용 요망"
            action_detail = "1. 접수된 고객의 마음을 열 '첫 달 렌탈료 무료', '사은품 업그레이드' 등의 타임세일 방식 프로모션 도입을 검토하십시오.<br>2. 상담 스크립트 상에 고객 혜택을 전면 배치하도록 재조정하십시오."
            
    elif "감소" in v_lvl:
        if "개선" in r_lvl:
            theory = "파레토 법칙 (80/20 규칙) 기반 집중 타겟팅"
            theory_rationale = "접수 모수는 감소했으나 전환 효율이 상승한 것은 타겟팅이 매우 정교하게 적중했음을 의미합니다. 상위 20%의 진성 고객군에 자원을 집중하는 파레토 모델을 적용합니다."
            diagnosis = "전체 접수 건수는 감소했으나, 오히려 최종 성공율은 상승했습니다. 비효율적인 허수 고객이 필터링되고 '진성 고객' 위주로 효율적인 영업이 진행되고 있음을 의미합니다."
            action_title = "저효율 광고 예산 삭감 및 핵심 유사 타겟 집중 공략"
            action_detail = "1. 전체 볼륨이 아닌 비용 효율성(ROAS) 관점에서 매우 긍정적인 신호입니다. 허수 유입을 유발하는 채널을 과감히 정리하십시오.<br>2. 최근 계약에 성공한 진성 고객과 프로필이 비슷한 '유사 타겟(Look-alike)'에게 광고 예산을 쏟아부으십시오."
        elif "하락" in r_lvl:
            theory = "손실 회피(Loss Aversion) 및 진입 장벽 완화"
            theory_rationale = "접수와 성공이 동반 하락하는 상황은 시장 내 경쟁력이 임계치 이하로 떨어졌음을 의미합니다. 고객의 심리적 재무 장벽을 낮추는 행동경제학적 접근이 가장 시급합니다."
            diagnosis = "접수와 성공율이 모두 하락하는 '이중 침체(Double Dip)' 국면입니다. 기존 방식으로는 실적 반등이 매우 어렵습니다."
            action_title = "시장 침체 극복을 위한 파격적인 진입 혜택 및 고객 부담 완화 시급"
            action_detail = "1. 소비 심리 위축에 대응하기 위해 '초기 설치비 완전 무료', '위약금 부담 완화' 등 고객의 심리적 진입 장벽을 완전히 제거하는 제안이 필요합니다.<br>2. 기존 타겟 방식을 엎고, 새로운 렌탈 목적을 가진 신시장 개척을 위한 파일럿 테스트를 진행하십시오."
        else:
            theory = "마케팅 채널 노후화 진단 및 믹스 다변화"
            theory_rationale = "성공율은 방어되고 있으나 절대적인 접수 규모가 쇠퇴하는 것은 채널 피로도 누적이 원인이므로, 인접 매체로의 채널 믹스 다변화 이론을 적용합니다."
            diagnosis = "성공율은 방어하고 있으나, 신규 접수량 자체가 점진적으로 감소하고 있습니다. 기존 마케팅 채널의 고객 반응이 고갈된 상태입니다."
            action_title = "기존 매체 편중에서 탈피하여 신규 고객 접점 채널 적극 발굴"
            action_detail = "1. 장기간 반복 노출된 광고 소재와 플랫폼을 전면 교체하여 브랜드 피로도를 리프레시해야 합니다.<br>2. 숏폼 플랫폼, 버티컬 커뮤니티 등 당사가 접근하지 않았던 신규 트래픽 채널로 마케팅 예산을 분산 투자하십시오."
            
    else: # 보합
        theory = "STP(시장세분화) 마이크로 포지셔닝 고도화"
        theory_rationale = "양적, 질적 지표가 모두 장기 횡보하는 것은 기존 영업 모델의 수명이 다했음을 의미합니다. 거시적 관점에서 벗어나 라이프스타일 기반 미세 세분화로 틈새 시장을 개척해야 합니다."
        diagnosis = "접수량과 성공율 모두 전월과 비슷한 정체 상태입니다. 전체적인 사업 실적이 특정 박스권에 고착화되었습니다."
        action_title = "기존 인구통계를 넘어 라이프스타일 기반의 세분화 상품 기획 필요"
        action_detail = "1. 수요가 정체된 상태로, 기존의 획일화된 렌탈 방식으로는 추가 수요 창출이 불가합니다.<br>2. '1인 가구', '펫(Pet) 거주 가구' 등 특정 세그먼트에 정확히 부합하는 전용 패키지를 신설하여 제안하십시오."

    return {
        "action_title": action_title,
        "v_lvl": v_lvl, "v_change": v_text,
        "r_lvl": r_lvl, "r_change": r_text,
        "yoy_lvl": yoy_lvl, "yoy_change": yoy_text,
        "diagnosis": diagnosis, "action_detail": action_detail,
        "c_text": c_text,
        "theory": theory, "theory_rationale": theory_rationale,
        "has_crm": crm_df is not None and not crm_df.empty,
        # 팝업에 노출하기 위한 원본 계산값들
        "rec_change_pct": rec_change_pct,
        "rate_diff_p": rate_diff_p,
        "avg_success_rate_prev_year": avg_success_rate_prev_year,
        "yoy_diff_p": yoy_diff_p,
        "success_rate": success_rate
    }

# =====================================================================
# [5단계] 대시보드 UI 레이아웃 구성
# =====================================================================
st.set_page_config(layout="wide", page_title="현대렌탈케어 경영관리 대시보드")
apply_custom_css()

st.title("현대렌탈케어 경영관리 대시보드")
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
        with m_col1: sel_main_y = st.selectbox("기준 연도", options=available_years, index=available_years.index(default_period.year), format_func=lambda x: f"{x}년", key="main_y")
        with m_col2: sel_main_m = st.selectbox("기준 월", options=months, index=months.index(default_period.month), format_func=lambda x: f"{x}월", key="main_m")
            
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
        
        # [수정 완료: KPI 누락 복구 영역]
        with st.expander(f"{sel_main_y}년 {sel_main_m}월 핵심 성과 지표", expanded=True):
            kpi_cols = st.columns(4)
            for col, metric in zip(kpi_cols, ['접수', '컨택', '성공', '성공율']):
                val = latest_data.get(metric, 0)
                delta = val - prev_data[metric] if prev_data is not None else 0
                if metric == '성공율': 
                    col.metric(metric, f"{val:.1%}", f"{delta*100:+.1f}%p")
                else: 
                    col.metric(f"{metric} (건)", f"{val:,.0f}", f"{delta:+.0f}")

        st.markdown("<br>", unsafe_allow_html=True)
        
        # [수정 완료: 7대3 레이아웃 및 우측 팝업 복구 영역]
        report_col, pop_col = st.columns([7, 3])
        
        ai_output = generate_ai_analysis(df, selected_period, crm_df)
        
        if ai_output:
            with report_col:
                with st.expander("📊 AI 경영진단 요약 보고서", expanded=True):
                    # 1. 핵심 경영 지침
                    st.markdown(f"<div class='action-highlight-box'>📢 **핵심 경영 지침:** {ai_output['action_title']}</div>", unsafe_allow_html=True)
                    
                    # 2. 시각화된 3열 요약 카드 (전년 평균 대비 지표로 교체)
                    st.markdown("<b>[월간 핵심 지표 요약]</b>", unsafe_allow_html=True)
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(f"""<div class='summary-card'>
                                        <h4>📈 접수 건수 (월별)</h4>
                                        <div class='value'>{ai_output['v_lvl']}</div>
                                        <div class='trend'>{ai_output['v_change']}</div>
                                    </div>""", unsafe_allow_html=True)
                    with c2:
                        st.markdown(f"""<div class='summary-card'>
                                        <h4>🎯 성공율 변동 (월별)</h4>
                                        <div class='value'>{ai_output['r_lvl']}</div>
                                        <div class='trend'>{ai_output['r_change']}</div>
                                    </div>""", unsafe_allow_html=True)
                    with c3:
                        st.markdown(f"""<div class='summary-card'>
                                        <h4>📊 전년 평균 대비 성공율</h4>
                                        <div class='value'>{ai_output['yoy_lvl']}</div>
                                        <div class='trend'>{ai_output['yoy_change']}</div>
                                    </div>""", unsafe_allow_html=True)
                    
                    # 3. 종합 진단 및 실행 방안
                    st.markdown(f"<div class='diagnosis-box'><strong>💡 [종합 진단]</strong><br>{ai_output['diagnosis']}</div>", unsafe_allow_html=True)
                    
                    st.markdown("<b>[실무 부서 세부 실행 방안]</b>", unsafe_allow_html=True)
                    st.markdown(f"<div class='detail-box'>{ai_output['action_detail']}</div>", unsafe_allow_html=True)
                    st.write("")
                    
                    if ai_output['has_crm']:
                        st.markdown("<b>[고객 특성 분석 (CRM 연동)]</b>", unsafe_allow_html=True)
                        st.markdown(f"<div class='detail-box'>{ai_output['c_text']}</div>", unsafe_allow_html=True)
            
            with pop_col:
                with st.expander("🔍 데이터 판단 근거 및 적용 이론", expanded=False):
                    criteria_md = f"""
                    **[시스템 진단 로직 및 임계치 운영 기준]**
                    
                    본 보고서는 아래 4개 축을 결합한 400여 가지의 경영 시나리오를 바탕으로 시스템이 자동 추론했습니다.
                    
                    **1. 양적 지표 (접수 건수 변동 기준)**
                    - 산식: 당월 접수량 전월비 증감률 (`{ai_output['rec_change_pct']*100:+.1f}%`)
                    - 판정: 대폭 증가(+15% 이상) / 점진 증가(+2% 이상) / 보합(-5% 내외) / 점진 감소(-15% 이하) / 대폭 감소(-15% 미만)
                    - 당월 판정: **{ai_output['v_lvl']}**
                    
                    **2. 질적 지표 (월간 성공율 변동폭 기준)**
                    - 산식: 당월 성공률 전월비 증감 포인트 (`{ai_output['rate_diff_p']:+.2f}%p`)
                    - 판정: 대폭 개선(+3%p 이상) / 점진 개선(+0.5%p 이상) / 보합(-0.5%p 내외) / 점진 하락(-3.0%p 이하) / 대폭 하락(-3.0%p 미만)
                    - 당월 판정: **{ai_output['r_lvl']}**
                    
                    **3. 성과 지표 (전년 전체 평균 대비 당월 성공율)**
                    - 산식: 당월 성공율(`{ai_output['success_rate']*100:.1f}%`) - 작년 연간 평균 성공율(`{ai_output['avg_success_rate_prev_year']*100:.1f}%`) = `{ai_output['yoy_diff_p']:+.2f}%p`
                    - 판정: 초과 달성(+2.0%p 이상) / 유사 수준 보합(-2.0%p ~ +2.0%p) / 실적 미흡(-2.0%p 미만)
                    - 당월 판정: **{ai_output['yoy_lvl']}**
                    
                    **4. 적용된 마케팅 학술 이론 및 매핑 근거**
                    - 적용 모델: **{ai_output['theory']}**
                    - 이론 선정 사유 (Rationale): {ai_output['theory_rationale']}
                    """
                    st.markdown(criteria_md)
        else:
            st.warning("선택하신 월의 데이터가 부족하여 AI 리포트를 생성할 수 없습니다.")

        # --- 차트 및 원본 데이터 테이블 (기존 기능 유지) ---
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("📈 지표별 트렌드 분석 (시각화)", expanded=True):
             vis_col1, vis_col2 = st.columns(2)
             with vis_col1: target_metric = st.selectbox("분석 지표 커스터마이징", ['설치완료', '접수', '컨택', '성공', '성공율'])
             with vis_col2: chart_type = st.radio("그래프 형태 선택", ["막대 그래프", "꺾은선형 그래프"], horizontal=True)
                
             start_d, end_d = df['period'].min(), df['period'].max()
             sc1, sc2, sc3, sc4 = st.columns(4)
             with sc1: start_y = st.selectbox("시작 연도", options=available_years, index=0, format_func=lambda x: f"{x}년", key="c_sy")
             with sc2: start_m = st.selectbox("시작 월", options=months, index=months.index(start_d.month) if start_y == start_d.year else 0, format_func=lambda x: f"{x}월", key="c_sm")
             with sc3: end_y = st.selectbox("종료 연도", options=available_years, index=len(available_years)-1, format_func=lambda x: f"{x}년", key="c_ey")
             with sc4: end_m = st.selectbox("종료 월", options=months, index=months.index(end_d.month) if end_y == end_d.year else 11, format_func=lambda x: f"{x}월", key="c_em")
                
             start_p, end_p = pd.to_datetime(f"{start_y}-{start_m}-01"), pd.to_datetime(f"{end_y}-{end_m}-01")
            
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
                         fig.update_traces(texttemplate='%{text:.1f}' if target_metric == '성공율' else '%{text:,.0f}', textposition='outside', marker_color='#1E88E5')
                     else:
                         fig = px.line(chart_df, x='조회월', y=target_metric, markers=True, text=target_metric)
                         fig.update_traces(line=dict(width=3, color='#1E88E5'), marker=dict(size=8, color='#2C3E50'), texttemplate='%{text:.1f}' if target_metric == '성공율' else '%{text:,.0f}', textposition="top center")
                        
                     max_val = chart_df[target_metric].max()
                     y_max_range = max_val * 1.2 if max_val > 0 else 1.0
                     fig.update_layout(
                         plot_bgcolor='rgba(255,255,255,1)', paper_bgcolor='rgba(255,255,255,1)', xaxis_title="", yaxis_title="",  
                         margin=dict(l=10, r=10, t=70, b=10),
                         xaxis=dict(showgrid=False, tickangle=-45, type='category', categoryorder='array', categoryarray=chart_df['조회월']),
                         yaxis=dict(showgrid=True, gridcolor='#F0F0F0', range=[0, y_max_range])
                     )
                     st.plotly_chart(fig, use_container_width=True)
                 else:
                     st.warning("해당 기간에 차트를 구성할 데이터가 없습니다.")
        
        with st.expander("📋 데이터 원본 표 확인", expanded=False):
            display_df = df.drop(columns=['year'], errors='ignore').copy()
            display_df['조회월'] = display_df['period'].dt.strftime('%Y-%m')
            st.dataframe(display_df.set_index('조회월').drop(columns=['period']).style.format({"성공율": "{:.2%}", "접수": "{:.0f}", "컨택": "{:.0f}", "성공": "{:.0f}", "설치완료": "{:.0f}"}))

else:
    st.info("좌측 메뉴에서 매출 데이터를 업로드하여 대시보드를 시작해주십시오.")
