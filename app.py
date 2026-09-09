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
    # [1단계] 실적 변동율 산출 및 기초 체력 확인
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
    
    # 1축: 손님 온도계 (유입량 기준)
    if rec_change_pct >= 0.15: rec_state = "폭증(대박)"
    elif rec_change_pct >= 0.02: rec_state = "성장(좋음)"
    elif -0.05 <= rec_change_pct < 0.02: rec_state = "정체(보통)"
    elif -0.15 <= rec_change_pct < -0.05: rec_state = "감소(나쁨)"
    else: rec_state = "급락(위험)"
        
    # 2축: 지갑 온도계 (계약률 기준)
    if rate_diff_p >= 3.0: rate_state = "급증(대박)"
    elif rate_diff_p >= 0.5: rate_state = "개선(좋음)"
    elif -0.5 <= rate_diff_p < 0.5: rate_state = "유지(보통)"
    elif -3.0 <= rate_diff_p < -0.5: rate_state = "하락(나쁨)"
    else: rate_state = "급락(위험)"

    # 3축: 기초 체력 (절대 계약률)에 따른 동적 메시지 조립 (150가지 확장용)
    if success_rate >= 0.30:
        base_health = "이미 10명 중 3명 이상이 계약하는 '매우 튼튼한 체력'을 가진 상태에서,"
    elif success_rate >= 0.10:
        base_health = "업계 평균적인 계약률을 유지하고 있는 상태에서,"
    else:
        base_health = "10명 중 1명도 계약시키기 힘든 '체력이 많이 약해진' 상태에서,"

    # ----------------------------------------------------
    # [2단계] 비전공자/CEO 맞춤형 직관적 처방 (5대 메인 그룹)
    # ----------------------------------------------------
    if "폭증" in rec_state or "성장" in rec_state:
        if "급증" in rate_state or "개선" in rate_state:
            theme = "최고의 황금기 (광고비 집중 투자)"
            key_issue = f"{base_health} 이번 달은 손님도 늘고, 지갑도 더 잘 엽니다."
            one_line_action = "📢 [공격 투자] 장사가 너무 잘 되는 시기입니다. 예산을 아끼지 말고 잘 나오는 광고에 돈을 더 쓰세요!"
            detail_action = "- 지금 들어오는 손님들은 우리 물건을 아주 마음에 들어 합니다.\n- 물 들어올 때 노 저어야 합니다. 가장 계약을 잘 하는 손님층을 찾아 맞춤형 추가 혜택을 던지세요."
        elif "하락" in rate_state or "급락" in rate_state:
            theme = "밑빠진 독에 물 붓기 (내부 수리 시급)"
            key_issue = f"{base_health} 가게에 손님은 많이 오는데, 물건은 안 사고 그냥 나가는 사람이 늘었습니다."
            one_line_action = "📢 [광고 일시중지] 밖에서 사람을 데려오는 광고를 잠시 멈추고, 손님이 왜 계약을 안 하고 나가는지 원인을 찾으세요!"
            detail_action = "- 손님이 기대했던 것과 실제 상담 내용이 달라서 실망하고 나갔을 확률이 높습니다.\n- 상담원들이 고객을 설득하는 대본(스크립트)을 당장 매력적으로 고쳐야 합니다."
        else:
            theme = "무난한 양적 성장"
            key_issue = f"{base_health} 손님은 늘었지만, 지갑을 여는 비율은 지난달과 비슷합니다."
            one_line_action = "📢 [현상 유지 및 혜택 추가] 늘어난 손님들을 확실한 내 고객으로 만들기 위해 작은 미끼(사은품 등)를 하나 더 던져보세요."
            detail_action = "- 지금의 광고 방식은 아주 좋습니다. 다만 마지막에 계약서에 사인하게 만들 '결정적 한 방'이 부족합니다."
            
    elif "감소" in rec_state or "급락" in rec_state:
        if "급증" in rate_state or "개선" in rate_state:
            theme = "소수 정예 알짜배기 장사"
            key_issue = f"{base_health} 전체 손님 수는 줄었지만, 찾아온 사람들은 아주 확실하게 지갑을 열었습니다."
            one_line_action = "📢 [타겟 집중] 아무나 오게 하는 넓은 광고를 끊고, 진짜 살 사람만 콕 집어서 유혹하세요!"
            detail_action = "- 찔러보기식 가짜 손님이 줄고 진짜 손님만 남았습니다. 비효율적인 마케팅 비용이 줄어들어 회사 이익엔 오히려 좋습니다.\n- 이번 달 계약한 사람들과 나이, 사는 곳이 비슷한 사람들에게만 광고를 집중하세요."
        elif "하락" in rate_state or "급락" in rate_state:
            theme = "심각한 비상사태 (더블 딥)"
            key_issue = f"{base_health} 구경 오는 손님도 끊겼고, 어쩌다 온 손님도 비싸다며 도망가고 있습니다."
            one_line_action = "📢 [파격 제안] 손님들이 가격과 위약금에 극심한 부담을 느끼고 있습니다. 말도 안 되는 파격 조건을 내거세요!"
            detail_action = "- 불경기 탓이 큽니다. '첫 달 렌탈비 0원'이나 '위약금 안심 보장' 등 손해를 보지 않을 거라는 핑곗거리를 쥐어줘야 합니다.\n- 기존과 똑같은 방식으로 영업하면 다음 달엔 더 힘들어집니다."
        else:
            theme = "모객 채널의 노후화"
            key_issue = f"{base_health} 손님들의 발길이 점점 줄어들고 있습니다."
            one_line_action = "📢 [새로운 간판 달기] 매일 똑같은 광고에 사람들이 질렸습니다. 전혀 새로운 곳에서 손님을 찾아야 합니다."
            detail_action = "- 우리가 평소에 안 하던 방식(예: 인스타그램 숏폼, 당근마켓 광고 등)으로 새로운 사람들의 눈길을 끌어야 합니다."
            
    else: # 정체
        theme = "제자리 걸음 (돌파구 필요)"
        key_issue = f"{base_health} 문의하는 사람도, 계약하는 사람도 지난달과 똑같이 멈춰있습니다."
        one_line_action = "📢 [새로운 상품 조합] 뻔한 나이/성별 영업에서 벗어나, '1인 가구 패키지' 같은 완전히 새로운 상품을 만드세요!"
        detail_action = "- 몇 달째 실적이 안 바뀐다면 시장이 우리에게 질렸다는 뜻입니다.\n- '강아지를 키우는 집 전용', '원룸 전용' 등 손님의 생활 방식에 맞춘 재밌는 상품 조합을 내세워야 합니다."

    # ----------------------------------------------------
    # [3단계] UI 가독성 및 판단 근거 투명화 리포트 (마크다운)
    # ----------------------------------------------------
    analysis_texts = []
    analysis_texts.append(f"### 📊 {latest['period'].strftime('%Y년 %m월')} CEO 및 임원 보고용 비즈니스 진단")
    
    # 1. 가장 시급한 핵심 Action (최상단)
    analysis_texts.append(f"### {one_line_action}")
    analysis_texts.append("\n---")
    
    # 2. 🧠 AI는 왜 이렇게 진단했을까요? (판단 기준의 투명한 공개 - 핵심 요청 사항)
    reasoning_text = f"""
**💡 AI 진단 기준 및 판단 근거 (유치원생도 이해하는 쉬운 설명)**

AI는 복잡한 숫자 대신 우리 비즈니스를 두 개의 **'건강 온도계'**로 진단했습니다.

1. **🚪 손님 온도계 (신규 유입량)**: 지난달보다 손님이 얼마나 더 가게에 들어왔는가?
   - *(+15% 이상: 폭증 / +2% 이상: 성장 / -5%~+1%: 정체 / -5% 이하: 감소 / -15% 이하: 급락)*
   - 👉 **우리 회사의 이번 달**: 지난달보다 신규 유입이 **{rec_change_pct*100:+.1f}%** 변했으므로 **[{rec_state}]** 상태입니다.

2. **💳 지갑 온도계 (계약 성공률)**: 들어온 손님 100명 중 몇 명이 진짜로 지갑을 열었는가?
   - *(+3%p 이상: 급증 / +0.5%p 이상: 개선 / -0.4%~+0.4%: 유지 / -0.5% 이하: 하락 / -3%p 이하: 급락)*
   - 👉 **우리 회사의 이번 달**: 지난달보다 실제 계약률이 **{rate_diff_p:+.1f}%p** 변했으므로 **[{rate_state}]** 상태입니다.

**결론적으로 {key_issue}** 
따라서 AI는 현재 우리 비즈니스의 상태를 **[{theme}]** 국면으로 규정하고 아래와 같은 실천 방안을 제안합니다.
    """
    analysis_texts.append(reasoning_text)
    analysis_texts.append("\n---")

    # 3. 비전공자도 이해하기 쉬운 상세 실천 방안
    analysis_texts.append(f"### 📋 실무 부서를 위한 구체적 행동 지침(Action Plan)\n{detail_action}")
    
    # 4. CRM 연동 코호트
    if crm_df is not None and all(c in crm_df.columns for c in ['성공여부', '연령대', '성별', '연도']):
        analysis_texts.append("\n---\n### 👥 우리 고객 특성 한눈에 보기 (CRM 기반)")
        analysis_texts.append("가입 이력을 토대로 우리 제품을 가장 좋아하는 고객 그룹과 가장 계약율이 저조했던 그룹을 찾아낸 표입니다.")
        
        table_crm = "| 분석 연도 | 제품을 가장 좋아하는 그룹 | 계약 성공이 어려운 그룹 | 실패 극복을 위한 해결 방책 |\n|---|---|---|---|\n"
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
                    action_plan = "모바일 계약서 간소화 (적는 단계 줄이기)"
                elif "50대" in worst[0] or "60대" in worst[0]:
                    action_plan = "설명서 글자 크기 확대 및 안심 해피콜 지원"
                else:
                    action_plan = "맞춤형 렌탈 요금 결합 할인 제시"
                
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
