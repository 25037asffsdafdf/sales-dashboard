import streamlit as st
import pandas as pd
from datetime import datetime
import re
import traceback

def clean_metric_name(name):
    """지표명을 시스템 표준 포맷으로 통일"""
    name = str(name).replace(" ", "")
    if "성공율" in name or "성공률" in name or "대비성공" in name: return "성공율"
    if "설치" in name: return "설치완료"
    if "성공" in name: return "성공"
    if "컨택" in name or "콜" in name: return "컨택"
    if "접수" in name: return "접수"
    return name

def parse_sales_data(uploaded_file):
    """다중 테이블(연도별 표)을 모두 스캔하여 병합하는 로직"""
    try:
        df_raw = pd.read_excel(uploaded_file, header=None)
        all_data = []
        
        # 파일 내 모든 '구분' 행 인덱스 추출 (2025년, 2026년 등 표가 여러 개일 경우 모두 인식)
        header_rows = df_raw[df_raw[0].astype(str).str.replace(" ", "") == "구분"].index.tolist()
        
        if not header_rows:
            st.error("엑셀 파일 내에 '구분' 항목을 찾을 수 없습니다.")
            return None
            
        for i, h_idx in enumerate(header_rows):
            # 현재 표의 끝을 다음 '구분' 행 이전 또는 파일 끝으로 설정
            end_idx = header_rows[i+1] if i + 1 < len(header_rows) else len(df_raw)
            block = df_raw.iloc[h_idx:end_idx].dropna(how='all')
            
            headers = block.iloc[0]
            for _, row in block.iloc[1:].iterrows():
                metric = clean_metric_name(row[0])
                if metric not in ['접수', '컨택', '성공', '성공율', '설치완료']:
                    continue
                    
                for col_idx in range(1, len(headers)):
                    col_name = str(headers[col_idx]).replace(" ", "").split(".")[0]
                    period = None
                    
                    # '202501' 형식 또는 '2025년1월' 형식 완벽 대응
                    if re.match(r'^20\d{4}$', col_name):
                        period = pd.to_datetime(col_name, format='%Y%m')
                    elif "년" in col_name and "월" in col_name:
                        nums = re.findall(r'\d+', col_name)
                        if len(nums) >= 2:
                            period = pd.to_datetime(f"{nums[0]}{int(nums[1]):02d}", format='%Y%m')
                    
                    if period:
                        val = row[col_idx]
                        # 공란이 아닌 유효한 숫자 데이터만 추출
                        if pd.notna(val) and str(val).strip() != '':
                            try:
                                val_float = float(str(val).replace(",", ""))
                                all_data.append({'period': period, 'metric': metric, 'value': val_float})
                            except ValueError:
                                pass
                                
        if not all_data:
            st.error("유효한 수치 데이터를 추출하지 못했습니다. 날짜 형식을 확인해주십시오.")
            return None
            
        df_long = pd.DataFrame(all_data)
        # 중복 데이터 발생 시 마지막 값 우선 반영
        df_long = df_long.groupby(['period', 'metric'], as_index=False)['value'].last()
        df_pivot = df_long.pivot(index='period', columns='metric', values='value').reset_index()
        
        # 누락된 지표 강제 생성 (KeyError 방지)
        for m in ['접수', '컨택', '성공', '성공율', '설치완료']:
            if m not in df_pivot.columns:
                df_pivot[m] = 0.0
                
        df_pivot = df_pivot.sort_values('period').reset_index(drop=True)
        
        # 성공율 시스템 재계산 (엑셀의 % 서식과 일반 숫자 서식 혼용 문제 해결)
        for idx, row in df_pivot.iterrows():
            if row['접수'] > 0:
                df_pivot.at[idx, '성공율'] = row['성공'] / row['접수']
            else:
                df_pivot.at[idx, '성공율'] = 0.0
                
        return df_pivot
        
    except Exception as e:
        st.error(f"데이터 전처리 중 시스템 오류가 발생했습니다: {str(e)}")
        st.code(traceback.format_exc())
        return None

def parse_crm_data(uploaded_file):
    try:
        crm_df = pd.read_excel(uploaded_file)
        crm_df.columns = [str(col).strip().replace(" ", "") for col in crm_df.columns]
        
        if '생년월일' in crm_df.columns:
            crm_df['생년월일'] = pd.to_datetime(crm_df['생년월일'], errors='coerce')
            crm_df = crm_df.dropna(subset=['생년월일']).copy()
            current_year = datetime.now().year
            crm_df['나이'] = current_year - crm_df['생년월일'].dt.year
            crm_df['연령대'] = (crm_df['나이'] // 10 * 10).astype(int).astype(str) + '대'
            
        for col in ['성별', '성공여부']:
            if col in crm_df.columns:
                crm_df[col] = crm_df[col].astype(str).replace(r'\s+', '', regex=True)
                
        return crm_df
    except Exception:
        return None

def generate_ai_analysis(df, selected_period, crm_df=None):
    if df is None or df.empty: 
        return "분석 리포트를 생성할 수 있는 데이터가 없습니다."
        
    current_data = df[df['period'] == selected_period]
    if current_data.empty:
        return "해당 월의 데이터가 존재하지 않습니다."
        
    latest = current_data.iloc[0]
    analysis_texts = [f"### {latest['period'].strftime('%Y년 %m월')} 성과 분석 요약"]
    
    last_year_dt = latest['period'].replace(year=latest['period'].year - 1)
    ly_data = df[df['period'] == last_year_dt]
    
    if not ly_data.empty:
        ly = ly_data.iloc[0]
        rec_diff = latest['접수'] - ly['접수']
        rate_diff = (latest['성공율'] - ly['성공율']) * 100
        
        trend_rec = "증가" if rec_diff > 0 else "감소"
        analysis_texts.append(
            f"- 전년 동월 대비 성과: 접수 건수는 {abs(rec_diff):,.0f}건 {trend_rec}하였으며, "
            f"성공율은 {rate_diff:+.1f}%p 변동하였습니다."
        )
        
    if crm_df is not None and all(c in crm_df.columns for c in ['성공여부', '연령대', '성별']):
        try:
            stats = crm_df.groupby(
