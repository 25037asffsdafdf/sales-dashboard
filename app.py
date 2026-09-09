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
                line-height: 1.7;
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
# [4단계] 100-Case 다차원 매트릭스 리포트 엔진
# =====================================================================
def generate_ai_analysis(df, selected_period, crm_df=None):
    current_data = df[df['period'] == selected_period]
    if current_data.empty or current_data.iloc[0]['접수'] == 0:
        return None
        
    latest = current_data.iloc[0]
    prev_month_dt = latest['period'] - pd.DateOffset(months=1)
    prev_data_df = df[df['period'] == prev_month_dt]
    
    # 1. 월간 지표 산출
    rec_val = latest['접수']
    success_rate = latest['성공율']
    rec_change_pct = 0.0
    rate_diff_p = 0.0
    if not prev_data_df.empty and prev_data_df.iloc[0]['접수'] > 0:
        prev = prev_data_df.iloc[0]
        rec_change_pct = (rec_val - prev['접수']) / prev['접수']
        rate_diff_p = (success_rate - prev['성공율']) * 100

    # 2. 전년 평균 비교 산출
    current_year = selected_period.year
    prev_year = current_year - 1
    df_prev_year = df[df['period'].dt.year == prev_year]
    
    avg_success_rate_prev_year = 0.0
    yoy_diff_p = 0.0
    if not df_prev_year.empty and df_prev_year['접수'].sum() > 0:
        avg_success_rate_prev_year = df_prev_year['성공'].sum() / df_prev_year['접수'].sum()
        yoy_diff_p = (success_rate - avg_success_rate_prev_year) * 100

    # --- 축 1: 접수 건수 변동 (5단계) ---
    if rec_change_pct >= 0.15: v_lvl, v_text = "대폭 증가", f"전월비 {rec_change_pct*100:+.1f}%"
    elif rec_change_pct >= 0.02: v_lvl, v_text = "점진 증가", f"전월비 {rec_change_pct*100:+.1f}%"
    elif -0.05 <= rec_change_pct < 0.02: v_lvl, v_text = "보합(유지)", f"전월비 {rec_change_pct*100:+.1f}%"
    elif -0.15 <= rec_change_pct < -0.05: v_lvl, v_text = "점진 감소", f"전월비 {rec_change_pct*100:+.1f}%"
    else: v_lvl, v_text = "대폭 감소", f"전월비 {rec_change_pct*100:+.1f}%"
        
    # --- 축 2: 성공율 변동폭 (5단계) ---
    if rate_diff_p >= 3.0: r_lvl, r_text = "대폭 개선", f"전월비 {rate_diff_p:+.1f}%p"
    elif rate_diff_p >= 0.5: r_lvl, r_text = "점진 개선", f"전월비 {rate_diff_p:+.1f}%p"
    elif -0.5 <= rate_diff_p < 0.5: r_lvl, r_text = "보합(유지)", f"전월비 {rate_diff_p:+.1f}%p"
    elif -3.0 <= rate_diff_p < -0.5: r_lvl, r_text = "점진 하락", f"전월비 {rate_diff_p:+.1f}%p"
    else: r_lvl, r_text = "대폭 하락", f"전월비 {rate_diff_p:+.1f}%p"

    # --- 축 3: 전년 대비 성과 (4단계) ---
    if avg_success_rate_prev_year == 0:
        yoy_lvl, yoy_text = "비교 불가", "전년 데이터 없음"
    elif yoy_diff_p >= 2.0:
        yoy_lvl, yoy_text = "초과 달성", f"작년 평균비 {yoy_diff_p:+.1f}%p"
    elif yoy_diff_p >= -2.0:
        yoy_lvl, yoy_text = "유사 수준(보합)", f"작년 평균비 {yoy_diff_p:+.1f}%p"
    else:
        yoy_lvl, yoy_text = "실적 미흡", f"작년 평균비 {yoy_diff_p:+.1f}%p"

    # ==============================================================================
    # 🧠 모듈형 조립 알고리즘 (V 5종 × R 5종 × Y 4종 = 100가지 상황별 동적 출력)
    # ==============================================================================
    
    # [블록 A: 시장 상태 진단 및 이론 매핑]
    if "증가" in v_lvl:
        if "개선" in r_lvl:
            theory = "LTV(고객생애가치) 극대화 모델"
            theory_rationale = "접수량과 전환 효율이 동반 상승하는 '확장기'입니다. 자원의 보수적 통제보다 점유율 선점을 위한 공격적 예산 투입이 절대적으로 유리한 시점입니다."
            diagnosis = f"신규 접수가 <b>[{v_lvl}]</b>함과 동시에 성공율 역시 <b>[{r_lvl}]</b>하고 있는 최상의 선순환 구조입니다."
        elif "하락" in r_lvl:
            theory = "영업 퍼널(Funnel) 병목 최적화"
            theory_rationale = "접수 유입은 늘었으나 최종 계약이 꺾이는 전형적인 마찰(Friction) 현상입니다. 모객 외형 확대보다 영업 전환 구조의 내부 결함을 우선 치유해야 합니다."
            diagnosis = f"신규 접수는 <b>[{v_lvl}]</b>했으나 최종 성공율은 오히려 <b>[{r_lvl}]</b> 중입니다. 영업 퍼널 곳곳에 고객 유실 요인이 작동하고 있습니다."
        else:
            theory = "업셀링(Up-selling) 및 추가 가치 제안"
            theory_rationale = "유입량은 원활하나 효율이 정체되어 있습니다. 가망 고객의 구매 의사결정을 촉발시킬 '결정적 트리거(프로모션 등)'가 부재한 상태입니다."
            diagnosis = f"신규 접수 건수가 <b>[{v_lvl}]</b>하고 있으나, 성공율은 <b>[{r_lvl}]</b> 상태를 면하지 못해 추가적인 도약 지점을 찾지 못하고 있습니다."
            
    elif "감소" in v_lvl:
        if "개선" in r_lvl:
            theory = "파레토 법칙 (80/20 집중 타겟팅)"
            theory_rationale = "모객량은 줄었으나 체결율이 높아진 것은 타겟 정교화가 적중했음을 시사합니다. 대중 광고비를 삭감하고 진성 타겟 위주로 자원을 효율화하는 것이 타당합니다."
            diagnosis = f"신규 접수량은 <b>[{v_lvl}]</b>했으나 세일즈 집중력 상승으로 성공율은 오히려 <b>[{r_lvl}]</b>했습니다. 허수 유입이 성공적으로 필터링되었습니다."
        elif "하락" in r_lvl:
            theory = "손실 회피(Loss Aversion) 진입 장벽 완화"
            theory_rationale = "유입량과 체결율이 동반 붕괴하는 더블 딥 상황입니다. 고객이 느끼는 초기 재무적 장벽이나 약정 부담을 파격적으로 해제해야만 반등이 가능합니다."
            diagnosis = f"신규 접수량과 성공율이 동시에 <b>[{v_lvl}]/[{r_lvl}]</b>하는 위기 상황입니다. 비즈니스 활력 자체가 심각하게 침체되어 있습니다."
        else:
            theory = "마케팅 채널 피로도 진단 및 믹스 다변화"
            theory_rationale = "효율은 보합권에서 방어 중이나 유입 통로 자체가 마르고 있습니다. 기존 광고 매체의 피로도 누적이 원인이므로 신규 트래픽 채널 발굴이 시급합니다."
            diagnosis = f"성공율 효율은 방어 중이나, 신규 접수량 자체가 <b>[{v_lvl}]</b>하고 있어 장기적인 모객 저하가 예측됩니다."
            
    else: # 보합
        if "개선" in r_lvl:
            theory = "영업 접점(MOT) 전환 효율성 고도화"
            theory_rationale = "모객은 멈춰 있으나 영업 사원의 체결 능력이 극대화된 상태입니다. 스크립트 최적화 및 영업 인센티브 체계를 강화하여 효율을 끝까지 쥐어짜야 합니다."
            diagnosis = f"접수량은 <b>[{v_lvl}]</b> 중이나 내부 영업력 강화를 통해 성공율을 <b>[{r_lvl}]</b>시키며 실적 방어에 성공하고 있습니다."
        elif "하락" in r_lvl:
            theory = "제품 경쟁력 및 CVP(고객가치제안) 재수립"
            theory_rationale = "모객은 평이한데 체결이 무너지는 것은 상품 자체의 매력도가 떨어졌음을 의미합니다. 근본적인 상품 패키징이나 가격 혜택을 재정비해야 합니다."
            diagnosis = f"접수량은 <b>[{v_lvl}]</b> 상태이나 성공율이 <b>[{r_lvl}]</b>하며 기존 상품 라인업의 시장 소구력이 약화되고 있습니다."
        else:
            theory = "STP(시장세분화) 마이크로 포지셔닝"
            theory_rationale = "양적/질적 지표가 모두 장기 횡보하는 것은 기존 모델의 수명이 다했음을 의미합니다. 특정 라이프스타일에 맞춘 틈새 시장을 개척해야 합니다."
            diagnosis = f"접수 수량과 가입 성공율 모두 뚜렷한 변동 없는 <b>[{v_lvl}]</b> 및 <b>[{r_lvl}]</b> 상태입니다. 전체 실적이 고착화되었습니다."

    # [블록 B: 전년비 성과 결합에 따른 최종 액션 지침 조립]
    if "초과" in yoy_lvl:
        action_title = f"성과 초과 달성에 따른 [{theory}] 전략 전면 확대"
        action_detail = (
            f"1. 당월 최종 성공율이 작년 연간 평균을 <b>확연히 초과 달성({yoy_diff_p:+.1f}%p)</b>하며 매우 양호한 모멘텀을 형성하고 있습니다.<br>"
            f"2. 위 진단에 따라 마케팅 비용 통제 한도를 상향하고, 성과 우수 채널 및 부서에 즉각적인 인센티브를 부여하여 시장 점유율을 독식해야 합니다."
        )
    elif "보합" in yoy_lvl:
        action_title = f"전년 수준 유지 및 [{theory}] 기반의 안정적 자원 방어"
        action_detail = (
            f"1. 당월 성공율이 작년 평균 대비 <b>유사 수준({yoy_diff_p:+.1f}%p)</b>에 안착하여 급격한 하락 리스크를 1차적으로 방어 중입니다.<br>"
            f"2. 전체 예산 규모는 현 수준으로 보수적 유지하되, 위 진단에서 도출된 취약 구간의 리소스를 빼내어 우수 구간으로 이동시키는 '리밸런싱'이 요구됩니다."
        )
    elif "미흡" in yoy_lvl:
        action_title = f"전년비 실적 미달에 따른 긴급 비용 통제 및 [{theory}] 처방 적용"
        action_detail = (
            f"1. 월간 등락에 관계없이, 당월 성공율이 작년 연간 평균에 비해서는 여전히 <b>실적 미흡({yoy_diff_p:+.1f}%p)</b> 구간에 고립되어 있습니다.<br>"
            f"2. 저효율 마케팅 캠페인을 전면 동결하고, 위 진단된 문제점을 해결하기 위한 내부 프로세스 재정비에 총력을 기울이십시오."
        )
    else:
        action_title = f"기준점 재수립 및 [{theory}] 중심의 영업 전략 구축"
        action_detail = (
            f"1. 비교를 위한 작년 데이터가 확인되지 않아 당월 단독 수치만으로 리포트를 발행합니다.<br>"
            f"2. 현재의 실적을 새로운 베이스라인(Baseline)으로 삼고, 위 진단에 부합하는 타겟 대응 매뉴얼을 수립하십시오."
        )

    # --- [부가 정보: CRM 코호트 특성 (분리된 추가 통찰)] ---
    c_text = "CRM 데이터 연동 시, 주력 고객군과 취약 고객군을 자동 판별합니다."
    if crm_df is not None and not crm_df.empty:
        try:
            curr_y_df = crm_df[crm_df['연도'] == latest['period'].year]
            if not curr_y_df.empty:
                stats = curr_y_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean()).sort_values(ascending=False)
                if not stats.empty and len(stats) > 0:
                    best = stats.index[0]
                    worst = stats.index[-1]
                    c_text = f"현재 계약 체결이 가장 수월한 최우수 타겟은 <b>[{best[0]} {best}]</b>이며, 영업 마찰이 가장 심각한 취약 타겟은 <b>[{worst[0]} {worst}]</b>로 분석되었습니다."
        except: pass

    return {
        "action_title": action_title,
        "v_lvl": v_lvl, "v_change": v_text,
        "r_lvl": r_lvl, "r_change": r_text,
        "yoy_lvl": yoy_lvl, "yoy_change": yoy_text,
        "diagnosis": diagnosis, "action_detail": action_detail,
        "c_text": c_text,
        "theory": theory, "theory_rationale": theory_rationale,
        "has_crm": crm_df is not None and not crm_df.empty,
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
        
        # [핵심 성과 지표 KPI]
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
        
        # [7대3 레이아웃: AI 보고서 및 우측 판단 근거 팝업]
        report_col, pop_col = st.columns([7, 3])
        
        ai_output = generate_ai_analysis(df, selected_period, crm_df)
        
        if ai_output:
            with report_col:
                with st.expander("📊 100-Case 자동 진단 요약 보고서", expanded=True):
                    # 1. 100-Case 조합 결론 액션 타이틀
                    st.markdown(f"<div class='action-highlight-box'>📢 **핵심 경영 지침:** {ai_output['action_title']}</div>", unsafe_allow_html=True)
                    
                    # 2. 3열 메트릭 카드
                    st.markdown("<b>[월간 핵심 지표 요약]</b>", unsafe_allow_html=True)
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(f"""<div class='summary-card'>
                                        <h4>📈 접수 건수 (월간)</h4>
                                        <div class='value'>{ai_output['v_lvl']}</div>
                                        <div class='trend'>{ai_output['v_change']}</div>
                                    </div>""", unsafe_allow_html=True)
                    with c2:
                        st.markdown(f"""<div class='summary-card'>
                                        <h4>🎯 성공율 변동 (월간)</h4>
                                        <div class='value'>{ai_output['r_lvl']}</div>
                                        <div class='trend'>{ai_output['r_change']}</div>
                                    </div>""", unsafe_allow_html=True)
                    with c3:
                        st.markdown(f"""<div class='summary-card'>
                                        <h4>📊 전년 평균비 성공율</h4>
                                        <div class='value'>{ai_output['yoy_lvl']}</div>
                                        <div class='trend'>{ai_output['yoy_change']}</div>
                                    </div>""", unsafe_allow_html=True)
                    
                    # 3. 진단 블록 및 액션 결합 문장 출력
                    st.markdown(f"<div class='diagnosis-box'><strong>💡 [종합 진단]</strong><br>{ai_output['diagnosis']}</div>", unsafe_allow_html=True)
                    
                    st.markdown("<b>[실무 부서 세부 실행 방안]</b>", unsafe_allow_html=True)
                    st.markdown(f"<div class='detail-box'>{ai_output['action_detail']}</div>", unsafe_allow_html=True)
                    st.write("")
                    
                    if ai_output['has_crm']:
                        st.markdown("<b>[고객 특성 분석 (CRM 부록)]</b>", unsafe_allow_html=True)
                        st.markdown(f"<div class='detail-box'>{ai_output['c_text']}</div>", unsafe_allow_html=True)
            
            with pop_col:
                with st.expander("🔍 시스템 판단 근거 및 적용 이론", expanded=False):
                    criteria_md = f"""
                    **[시스템 100-Case 로컬 조립 기준표]**
                    
                    본 보고서는 5(양적) × 5(질적) × 4(성과) = 총 100가지의 경우의 수 중 데이터에 부합하는 최적의 매트릭스를 로컬 연산하여 도출합니다.
                    
                    **1. 양적 지표 (접수 건수 변동)**
                    - 산식: 전월 대비 증감률 ({ai_output['rec_change_pct']*100:+.1f}%)
                    - 판정 기준: 대폭 증가(+15% 이상) / 점진 증가(+2% 이상) / 보합(-5% 내외) / 점진 감소(-15% 이하) / 대폭 감소(-15% 미만)
                    - 당월 시스템 판정: **{ai_output['v_lvl']}**
                    
                    **2. 질적 지표 (당월 성공율 변동폭)**
                    - 산식: 전월 대비 증감 포인트 ({ai_output['rate_diff_p']:+.2f}%p)
                    - 판정 기준: 대폭 개선(+3%p 이상) / 점진 개선(+0.5%p 이상) / 보합(-0.5%p 내외) / 점진 하락(-3.0%p 이하) / 대폭 하락(-3.0%p 미만)
                    - 당월 시스템 판정: **{ai_output['r_lvl']}**
                    
                    **3. 성과 지표 (전년 전체 평균 대비 당월 성공율)**
                    - 산식: 당월 성공율({ai_output['success_rate']*100:.1f}%) - 작년 연간 평균 성공율({ai_output['avg_success_rate_prev_year']*100:.1f}%) = {ai_output['yoy_diff_p']:+.2f}%p
                    - 판정 기준: 초과 달성(+2.0%p 이상) / 유사 수준 보합(-2.0%p ~ +2.0%p) / 실적 미흡(-2.0%p 미만)
                    - 당월 시스템 판정: **{ai_output['yoy_lvl']}**
                    
                    **4. 적용된 마케팅 학술 이론 및 매핑 사유**
                    - 적용 모델: **{ai_output['theory']}**
                    - 이론 매핑 사유 (Rationale): {ai_output['theory_rationale']}
                    """
                    st.markdown(criteria_md)
        else:
            st.warning("선택하신 월의 데이터가 부족하여 AI 리포트를 생성할 수 없습니다.")

        # --- 차트 및 원본 데이터 테이블 ---
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
