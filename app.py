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
            /* 진단 박스 시각화 CSS */
            .diagnosis-box {
                background-color: #F4F6F9;
                padding: 20px;
                border-radius: 8px;
                border-left: 6px solid #1E88E5;
                margin: 15px 0px;
                font-size: 1.05em;
                line-height: 1.6;
            }
            .action-highlight {
                color: #B71C1C;
                font-weight: 800;
                font-size: 1.15em;
            }
            /* 지표 요약 테이블 시각화 CSS */
            .summary-table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }
            .summary-table th, .summary-table td {
                border: 1px solid #e0e0e0;
                padding: 12px;
                text-align: left;
            }
            .summary-table th {
                background-color: #F8F9FA;
                font-weight: bold;
                width: 30%;
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
                    y, m = int(nums[0]), int(nums[1])
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
# [4단계] 400가지 경우의 수 기반: 보수적 경영 리포트 생성 엔진
# =====================================================================
def generate_ai_analysis(df, selected_period, crm_df=None):
    current_data = df[df['period'] == selected_period]
    if current_data.empty or current_data.iloc[0]['접수'] == 0:
        return {"report": "선택하신 월의 실적 데이터가 충분하지 않습니다.", "criteria": ""}
        
    latest = current_data.iloc[0]
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
        
    # --- [경우의 수 1축: 신규 유입량 변동 (5단계)] ---
    if rec_change_pct >= 0.15: v_lvl, v_text = "대폭 증가", "신규 유입량이 전월 대비 크게 확대"
    elif rec_change_pct >= 0.02: v_lvl, v_text = "점진 증가", "신규 유입량이 전월 대비 점진적 상승세"
    elif -0.05 <= rec_change_pct < 0.02: v_lvl, v_text = "보합(유지)", "신규 유입량이 전월과 유사한 수준 유지"
    elif -0.15 <= rec_change_pct < -0.05: v_lvl, v_text = "점진 감소", "신규 유입량이 전월 대비 점진적 하락세"
    else: v_lvl, v_text = "대폭 감소", "신규 유입량이 전월 대비 크게 위축"
        
    # --- [경우의 수 2축: 계약 성공률 변동 (5단계)] ---
    if rate_diff_p >= 3.0: r_lvl, r_text = "대폭 개선", "최종 전환율이 눈에 띄게 개선"
    elif rate_diff_p >= 0.5: r_lvl, r_text = "점진 개선", "최종 전환율이 안정적으로 상승"
    elif -0.5 <= rate_diff_p < 0.5: r_lvl, r_text = "보합(유지)", "최종 전환율이 정체 구간에 진입"
    elif -3.0 <= rate_diff_p < -0.5: r_lvl, r_text = "점진 하락", "최종 전환율이 하락 추세로 전환"
    else: r_lvl, r_text = "대폭 하락", "최종 전환율이 심각한 수준으로 이탈"

    # --- [경우의 수 3축: 기초 체력 / 절대 전환율 (4단계)] ---
    if success_rate >= 0.30: b_lvl, b_text = "안정적 고효율", "전체 유입 인원의 30% 이상이 계약하는 견고한 수익 구조"
    elif success_rate >= 0.20: b_lvl, b_text = "양호한 효율", "업계 평균을 상회하는 안정적인 계약 구조"
    elif success_rate >= 0.10: b_lvl, b_text = "평균 효율", "추가적인 효율 개선이 요구되는 평균적 수준"
    else: b_lvl, b_text = "전환 취약", "유입 인원 대비 실제 계약 비중이 10% 미만인 심각한 수익 누수 구간"

    # --- [경우의 수 4축: CRM 코호트 특성 (4단계)] ---
    c_lvl, c_text = "특정 쏠림 없음", "전 연령대 및 성별에 걸쳐 고른 분포"
    best_cohort, worst_cohort = "-", "-"
    
    if crm_df is not None and not crm_df.empty:
        try:
            curr_y_df = crm_df[crm_df['연도'] == latest['period'].year]
            if not curr_y_df.empty:
                stats = curr_y_df.groupby(['연령대', '성별'])['성공여부'].apply(lambda x: (x == '성공').mean()).sort_values(ascending=False)
                if not stats.empty and len(stats) > 0:
                    best = stats.index[0]
                    worst = stats.index[-1]
                    best_cohort = f"{best[0]} {best[1]}"
                    worst_cohort = f"{worst[0]} {worst[1]}"
                    
                    if "20대" in best[0] or "30대" in best[0]: c_lvl = "청년층 중심"
                    elif "40대" in best[0] or "50대" in best[0]: c_lvl = "중장년층 중심"
                    elif "60대" in best[0]: c_lvl = "시니어층 중심"
                    
                    c_text = f"현재 주력 타겟은 [{best_cohort}]이며, 이탈이 가장 잦은 취약 타겟은 [{worst_cohort}]입니다."
        except: pass

    # --- [총 400가지 경우의 수 기반: 적용 마케팅 이론 및 행동 지침 동적 산출] ---
    if "증가" in v_lvl:
        if "개선" in r_lvl:
            theory = "LTV(고객생애가치) 극대화 모델"
            theory_rationale = "유입량과 전환율이 동반 상승하는 '골든 크로스' 구간에서는, 한정된 예산의 분배보다 공격적인 자원 투입을 통한 시장 점유율 선점이 재무적 기업 가치 창출에 절대적으로 유리하기 때문입니다."
            diagnosis = f"신규 유입량이 {v_text}됨과 동시에 최종 전환율이 {r_text}되고 있습니다. {b_text}를 기반으로 성장이 가속화되는 최적의 확장 국면입니다."
            action_title = "우수 마케팅 채널에 대한 예산 증액 및 타겟 범위 확대 요망"
            action_detail = (
                "1. 현재 투입되는 고객 획득 비용(CAC) 대비 장기적 수익 가치가 매우 높게 측정됩니다.\n"
                "2. 기존 예산의 보수적 통제를 해제하고, 성과가 입증된 채널을 중심으로 공격적인 예산 편성이 필요합니다."
            )
        elif "하락" in r_lvl:
            theory = "퍼널(Funnel) 이탈 구간 및 병목 현상 최적화"
            theory_rationale = "유입량은 증가하나 전환율이 하락하는 징후는 영업 프로세스 내 심각한 마찰(Friction) 현상을 의미합니다. 무의미한 외형 확장보다 내부 전환 구조의 결함을 치유하는 것이 우선되어야 하므로 본 이론을 적용합니다."
            diagnosis = f"신규 유입량은 {v_text}되었으나, 최종 전환율이 {r_text}되고 있습니다. {b_text} 상태로, 양적 성장 대비 질적 효율이 훼손되고 있습니다."
            action_title = "신규 광고 예산 투입의 일시적 보류 및 내부 상담 프로세스 점검 시급"
            action_detail = (
                "1. 광고 메시지와 실제 상담 시 제공되는 혜택 간의 괴리가 이탈을 유발하고 있는지 점검이 요구됩니다.\n"
                "2. 가입 절차의 복잡성 및 상담 지연 등 내부 프로세스의 병목(Bottleneck) 구간을 최우선으로 수리해야 합니다."
            )
        else:
            theory = "업셀링(Up-selling) 및 추가 가치 제안"
            theory_rationale = "양적 유입은 원활하나 전환이 정체된 경우, 가망 고객의 구매 결정(Decision-making)을 촉발할 '결정적 트리거'가 부재한 상태이므로 한시적 프로모션 제안 이론이 가장 적합합니다."
            diagnosis = f"신규 유입량은 {v_text}된 반면, 전환율은 {r_text}인 상태입니다. 양적 유입은 성공적이나 효율은 정체되어 있습니다."
            action_title = "전환율 제고를 위한 추가 프로모션 한시적 적용 요망"
            action_detail = (
                "1. 늘어난 유입량을 실제 계약으로 이끌어낼 마감 임박 프로모션 등 '결정적 유인책'이 부재합니다.\n"
                "2. 가입 시 제공되는 기본 사은품 외에 객단가가 높은 상품에 대한 결합 할인 등을 제시하십시오."
            )
            
    elif "감소" in v_lvl:
        if "개선" in r_lvl:
            theory = "파레토 법칙 (80/20 규칙) 기반 핵심 타겟 집중 전략"
            theory_rationale = "유입 모수는 감소했으나 전환 효율이 상승하는 국면은 마케팅의 질적 타겟팅이 적중했음을 시사합니다. 상위 20%의 진성 고객군에 자원을 집중하는 것이 최적의 대안이므로 본 모델을 채택합니다."
            diagnosis = f"신규 유입량은 {v_text}되었으나, 반대로 전환율은 {r_text}되었습니다. 진성 고객 위주로 {b_text}를 확보 중입니다."
            action_title = "불특정 다수 대상의 매스(Mass) 마케팅 축소 및 유사 타겟팅 고도화"
            action_detail = (
                "1. 허수 유입이 제거되고 진성 고객의 비중이 늘어나 전반적인 마케팅 비용 효율성은 상승했습니다.\n"
                "2. 최근 계약을 체결한 고객군과 인구통계학적 요인이 유사한 '맞춤형 타겟'에만 광고를 노출하십시오."
            )
        elif "하락" in r_lvl:
            theory = "손실 회피(Loss Aversion) 및 진입 장벽 완화 이론"
            theory_rationale = "유입과 전환이 동반 하락하는 더블 딥(Double-dip) 상황은 시장 내 브랜드 경쟁력이 임계치 이하로 떨어졌음을 의미합니다. 고객의 심리적 재무 장벽을 낮추는 행동경제학적 접근이 가장 시급합니다."
            diagnosis = f"신규 유입량이 {v_text}됨과 동시에 전환율도 {r_text}되는 이중 침체(Double Dip) 국면입니다. {b_text}가 위협받고 있습니다."
            action_title = "초기 가입에 대한 재무적 부담 최소화 및 위약금 유예 등 선제적 혜택 도입 시급"
            action_detail = (
                "1. 대내외적 요인으로 인해 소비 심리가 위축되었으므로 일반적인 상품 안내로는 전환을 이끌어낼 수 없습니다.\n"
                "2. '초기 렌탈료 1개월 면제' 또는 '해지 위약금 부담 완화' 등 고객의 재무적 리스크를 없애는 조치가 요구됩니다."
            )
        else:
            theory = "채널 노후화 진단 및 다변화 전략"
            theory_rationale = "전환율은 방어되고 있으나 절대적인 모객 규모가 점진 쇠퇴하는 것은 기존 매체 채널의 피로도 누적이 원인이므로, 인접 매체로의 채널 믹스 다변화 이론을 적용합니다."
            diagnosis = f"신규 유입량이 {v_text}되는 추세 속에서 전환율은 {r_text}입니다. 기존 마케팅 채널의 피로도가 누적된 상태입니다."
            action_title = "기존 매체 편중에서 탈피하여 신규 고객 접점 채널 발굴 요망"
            action_detail = (
                "1. 동일한 광고 소재와 채널이 장기간 반복 노출됨에 따라 고객의 반응률이 현저히 저하되었습니다.\n"
                "2. 타겟 연령층이 주로 소비하는 신규 매체(예: 숏폼 플랫폼, 버티컬 커뮤니티 등)로의 전환을 기획하십시오."
            )
            
    else: # 보합
        theory = "STP(시장세분화, 표적시장, 포지셔닝) 고도화"
        theory_rationale = "양적/질적 지표가 모두 장기 횡보하는 것은 기존 획일적 영업 모델의 수명이 다했음을 의미합니다. 거시적 관점에서 벗어나 라이프스타일 기반의 미세 세분화로 틈새 시장을 개척해야 합니다."
        diagnosis = f"유입량과 전환율 모두 전월 대비 {r_lvl} 상태입니다. 전체적인 사업 실적이 {b_text} 수준에서 고착화되었습니다."
        action_title = "거시적 기준(성별/연령)을 넘어 라이프스타일 기반의 마이크로 세분화 상품 기획 필요"
        action_detail = (
            "1. 시장의 수요가 정체된 상태로, 기존의 획일화된 렌탈 상품 라인업으로는 신규 수요 창출이 불가합니다.\n"
            "2. '1인 가구', '펫(Pet) 거주 가구' 등 특정 라이프스타일에 부합하는 결합 패키지를 신설하여 제안하십시오."
        )

    # ----------------------------------------------------
    # [5단계] 출력용 마크다운 리포트 조립 (시각화 극대화)
    # ----------------------------------------------------
    report_md = f"#### 📌 핵심 경영 지침\n"
    report_md += f"<div style='margin-bottom:20px;'><span class='action-highlight'>{action_title}</span></div>"
    
    # 지표 요약 테이블 시각화
    report_md += "**[월간 핵심 지표 요약]**\n"
    report_md += "<table class='summary-table'>"
    report_md += f"<tr><th>📈 <strong>신규 유입량</strong></th><td><strong>{v_lvl}</strong> (전월 대비 {rec_change_pct*100:+.1f}%)</td></tr>"
    report_md += f"<tr><th>🎯 <strong>계약 성공률</strong></th><td><strong>{r_lvl}</strong> (전월 대비 {rate_diff_p:+.1f}%p)</td></tr>"
    report_md += f"<tr><th>🔋 <strong>기초 체력</strong></th><td><strong>{b_lvl}</strong> (최종 성공률 {success_rate*100:.1f}%)</td></tr>"
    report_md += "</table>\n\n"

    # 종합 진단 하이라이트 박스
    report_md += f"<div class='diagnosis-box'><strong>💡 [종합 진단]</strong><br>{diagnosis}</div>\n\n"
    
    report_md += "**[실무 부서 세부 실행 방안]**\n"
    report_md += f"{action_detail}\n\n"
    
    if crm_df is not None:
        report_md += "**[고객 코호트(Cohort) 분석 기반 특이사항]**\n"
        report_md += f"- {c_text}\n"
        report_md += f"- (실행 권고) 취약 타겟({worst_cohort})에 대한 무리한 영업보다 우수 타겟({best_cohort}) 대상의 교차 판매(Cross-selling)에 집중할 것을 권장합니다.\n"

    # --- [팝업용: 데이터 진단 기준표 및 로직 설명 (오류 수정 완료)] ---
    criteria_md = f"""
**[시스템 진단 로직 및 임계치 운영 기준]**

본 보고서는 아래 4개 축을 결합한 400여 가지의 경영 시나리오를 바탕으로 자동 추론되었습니다.

**1. 양적 지표 (접수량 변동 기준)**
- 측정값: 당월 접수량 전월비 증감률 (`{rec_change_pct*100:+.1f}%`)
- 5단계 판정: 대폭 증가(+15% 이상) / 점진 증가(+2% 이상) / 보합(-5% ~ +2%) / 점진 감소(-15% ~ -5%) / 대폭 감소(-15% 미만)
- 당월 판정: **{v_lvl}**

**2. 질적 지표 (계약 전환율 변동 기준)**
- 측정값: 당월 성공률 전월비 증감폭 (`{rate_diff_p:+.2f}%p`)
- 5단계 판정: 대폭 개선(+3%p 이상) / 점진 개선(+0.5%p 이상) / 보합(-0.5%p ~ +0.5%p) / 점진 하락(-3.0%p ~ -0.5%p) / 대폭 하락(-3.0%p 미만)
- 당월 판정: **{r_lvl}**

**3. 기초 체력 (절대 전환율 기준)**
- 측정값: 당월 절대 성공률 (`{success_rate*100:.1f}%`)
- 4단계 판정: 안정적 고효율(30% 이상) / 양호한 효율(20% 이상) / 평균 효율(10% 이상) / 전환 취약(10% 미만)
- 당월 판정: **{b_lvl}**

**4. 적용된 경영/마케팅 학술 이론 및 매핑 근거**
- 적용 모델: **{theory}**
- 이론 선정 사유 (Rationale): {theory_rationale}
    """
    
    return {"report": report_md, "criteria": criteria_md}

# =====================================================================
# [6단계] 대시보드 UI 레이아웃 구성
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
        with st.expander(f"{sel_main_y}년 {sel_main_m}월 핵심 성과 지표", expanded=True):
            kpi_cols = st.columns(4)
            for col, metric in zip(kpi_cols, ['접수', '컨택', '성공', '성공율']):
                val = latest_data.get(metric, 0)
                delta = val - prev_data[metric] if prev_data is not None else 0
                if metric == '성공율': col.metric(metric, f"{val:.1%}", f"{delta*100:+.1f}%p")
                else: col.metric(f"{metric} (건)", f"{val:,.0f}", f"{delta:+.0f}")
                    
        st.markdown("<br>", unsafe_allow_html=True)
        
        # --- 리포트 및 판단 근거 UI 레이아웃 분리 (Expander 처리 반영) ---
        report_col, pop_col = st.columns([7, 3])
        
        ai_output = generate_ai_analysis(df, selected_period, crm_df)
        
        with report_col:
            # 보고서를 열고 닫을 수 있도록 Expander 적용
            with st.expander("📊 경영진단 요약 보고서", expanded=True):
                st.markdown(ai_output["report"], unsafe_allow_html=True)
            
        with pop_col:
            # 근거 팝업은 기본적으로 닫아두어 화면을 깔끔하게 유지
            with st.expander("🔍 데이터 판단 근거 및 적용 이론", expanded=False):
                st.markdown(ai_output["criteria"], unsafe_allow_html=True)
                
        st.markdown("<br>", unsafe_allow_html=True)

        # --- 차트 영역 ---
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

