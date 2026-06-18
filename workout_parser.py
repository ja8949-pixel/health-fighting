"""운동 텍스트 파서 + 운동 사전 (헬스장 기구 → 근육 그룹 자동 분류)"""

import re
from datetime import date
from typing import Optional

# ── 운동 사전 ────────────────────────────────────────────────────────────────
# (매칭 패턴, 근육 그룹, 주요 타겟 근육)  ※ 구체적 이름 먼저 배치
EXERCISE_DB = [
    # 등
    ("렛풀다운",      "등", "광배근, 대원근"),
    ("랫풀다운",      "등", "광배근, 대원근"),
    ("시티드로우",    "등", "광배근, 승모근"),
    ("씨티드로우",    "등", "광배근, 승모근"),
    ("티바로우",      "등", "등 전체"),
    ("백익스텐션",    "등", "척추기립근"),
    ("데드리프트",    "등", "척추기립근, 광배근"),
    ("하이로우",      "등", "광배근 하부"),
    ("로우로우",      "등", "등 상부"),
    ("암풀다운",      "등", "광배근"),
    ("케이블로우",    "등", "광배근, 승모근"),
    ("원암로우",      "등", "광배근"),
    ("바벨로우",      "등", "등 전체"),
    ("풀업",          "등", "광배근, 대원근"),
    ("턱걸이",        "등", "광배근, 대원근"),
    ("풀다운",        "등", "광배근"),
    ("로우",          "등", "광배근, 승모근"),
    # 가슴
    ("인클라인체스트프레스", "가슴", "대흉근 상부"),
    ("디클라인체스트프레스", "가슴", "대흉근 하부"),
    ("인클라인벤치",  "가슴", "대흉근 상부"),
    ("디클라인벤치",  "가슴", "대흉근 하부"),
    ("체스트프레스",  "가슴", "대흉근"),
    ("벤치프레스",    "가슴", "대흉근"),
    ("케이블크로스",  "가슴", "대흉근 내측"),
    ("팩덱플라이",    "가슴", "대흉근 내측"),
    ("팩덱",          "가슴", "대흉근 내측"),
    ("리버스플라이",  "어깨·팔", "후면 삼각근"),
    ("인클라인",      "가슴", "대흉근 상부"),
    ("디클라인",      "가슴", "대흉근 하부"),
    ("체스트",        "가슴", "대흉근"),
    ("벤치",          "가슴", "대흉근"),
    ("플라이",        "가슴", "대흉근"),
    ("딥스",          "가슴", "대흉근 하부, 삼두"),
    # 어깨·팔
    ("숄더프레스",    "어깨·팔", "전면 삼각근"),
    ("오버헤드프레스","어깨·팔", "전면 삼각근"),
    ("밀리터리프레스","어깨·팔", "전면 삼각근"),
    ("레터럴레이즈",  "어깨·팔", "측면 삼각근"),
    ("사이드레이즈",  "어깨·팔", "측면 삼각근"),
    ("프론트레이즈",  "어깨·팔", "전면 삼각근"),
    ("리어델트",      "어깨·팔", "후면 삼각근"),
    ("페이스풀",      "어깨·팔", "후면 삼각근"),
    ("프리처컬",      "어깨·팔", "이두근"),
    ("암컬머신",      "어깨·팔", "이두근"),
    ("해머컬",        "어깨·팔", "이두근, 상완근"),
    ("케이블컬",      "어깨·팔", "이두근"),
    ("트라이셉스푸시다운", "어깨·팔", "삼두근"),
    ("트라이셉스",    "어깨·팔", "삼두근"),
    ("케이블푸시다운","어깨·팔", "삼두근"),
    ("오버헤드익스텐션", "어깨·팔", "삼두근"),
    ("스컬크러셔",    "어깨·팔", "삼두근"),
    ("레터럴",        "어깨·팔", "측면 삼각근"),
    ("사레레",        "어깨·팔", "측면 삼각근"),
    ("숄더",          "어깨·팔", "삼각근"),
    ("아령",          "어깨·팔", "삼각근, 이두"),
    ("덤벨",          "어깨·팔", "삼각근, 이두"),
    ("삼두",          "어깨·팔", "삼두근"),
    ("이두",          "어깨·팔", "이두근"),
    ("암컬",          "어깨·팔", "이두근"),
    ("컬",            "어깨·팔", "이두근"),
    ("푸시다운",      "어깨·팔", "삼두근"),
    ("트라이",        "어깨·팔", "삼두근"),
    # 하체
    ("레그프레스",    "하체", "대퇴사두근, 둔근"),
    ("레그익스텐션",  "하체", "대퇴사두근"),
    ("레그컬",        "하체", "햄스트링"),
    ("라잉레그컬",    "하체", "햄스트링"),
    ("시티드레그컬",  "하체", "햄스트링"),
    ("핵스쿼트",      "하체", "대퇴사두근, 둔근"),
    ("브이스쿼트",    "하체", "대퇴사두근, 둔근"),
    ("불가리안",      "하체", "대퇴사두근, 둔근"),
    ("카프레이즈",    "하체", "종아리"),
    ("이너타이",      "하체", "내전근"),
    ("아웃타이",      "하체", "중둔근"),
    ("힙쓰러스트",    "하체", "둔근"),
    ("글루트브릿지",  "하체", "둔근"),
    ("스텝업",        "하체", "대퇴사두근, 둔근"),
    ("스쿼트",        "하체", "대퇴사두근, 둔근"),
    ("런지",          "하체", "대퇴사두근, 둔근"),
    ("햄스트링",      "하체", "햄스트링"),
    ("카프",          "하체", "종아리"),
    ("힙",            "하체", "둔근"),
    ("이너",          "하체", "내전근"),
    ("레그",          "하체", "대퇴사두근"),
    # 복근
    ("시트크런치",    "복근", "상복부"),
    ("케이블크런치",  "복근", "상복부"),
    ("레그레이즈",    "복근", "하복부"),
    ("니업",          "복근", "하복부"),
    ("로만체어",      "복근", "하복부, 장요근"),
    ("트위스트머신",  "복근", "외복사근"),
    ("로터리토르소",  "복근", "외복사근"),
    ("크런치",        "복근", "상복부"),
    ("플랭크",        "복근", "코어 전체"),
    ("트위스트",      "복근", "외복사근"),
    ("복근",          "복근", "복직근"),
    ("코어",          "복근", "코어 전체"),
    ("윗몸",          "복근", "복직근"),
    ("싯업",          "복근", "복직근"),
    ("시저스",        "복근", "하복부"),
    # 유산소
    ("러닝",          "유산소", "전신 지구력"),
    ("달리기",        "유산소", "전신 지구력"),
    ("사이클",        "유산소", "전신 지구력"),
    ("스피닝",        "유산소", "전신 지구력"),
    ("트레드밀",      "유산소", "전신 지구력"),
    ("걷기",          "유산소", "전신 지구력"),
    ("워킹",          "유산소", "전신 지구력"),
    ("조깅",          "유산소", "전신 지구력"),
    ("로잉",          "유산소", "전신 지구력"),
    ("바이크",        "유산소", "전신 지구력"),
    ("줄넘기",        "유산소", "전신 지구력"),
    ("버피",          "유산소", "전신"),
]

MUSCLE_META = {
    "등":      {"icon": "🔙", "color": "#4FC3F7"},
    "가슴":    {"icon": "🫁", "color": "#FF6B9D"},
    "어깨·팔": {"icon": "💪", "color": "#FFD54F"},
    "하체":    {"icon": "🦵", "color": "#66BB6A"},
    "복근":    {"icon": "⬜", "color": "#FF8A65"},
    "유산소":  {"icon": "🏃", "color": "#AB47BC"},
    "기타":    {"icon": "🏋️", "color": "#90A4AE"},
}


def get_muscle_group(exercise_name: str) -> tuple:
    """운동 이름 → (근육 그룹, 타겟 상세) 반환"""
    name_lower = exercise_name.strip().lower().replace(" ", "")
    for pattern, group, target in EXERCISE_DB:
        p = pattern.lower().replace(" ", "")
        if p in name_lower or name_lower in p:
            return group, target
    return "기타", ""


def parse_date_line(text: str) -> Optional[dict]:
    pattern = r'(\d{2})\.(\d{2})\.(\d{2}).*?-\s*(.+)'
    m = re.search(pattern, text.strip())
    if not m:
        return None
    yy, mm, dd, time_str = m.group(1), m.group(2), m.group(3), m.group(4).strip()
    h_match = re.search(r'(\d+)h', time_str)
    min_match = re.search(r'(\d+)m(?!in)', time_str)
    hours = int(h_match.group(1)) if h_match else 0
    mins = int(min_match.group(1)) if min_match else 0
    return {
        "date": f"20{yy}-{mm}-{dd}",
        "total_minutes": hours * 60 + mins if (hours or mins) else None,
        "total_time_str": time_str,
    }


def parse_exercise_line(text: str) -> list:
    tokens = text.strip().split()
    exercises = []
    for token in tokens:
        m = re.match(r'^([가-힣a-zA-Z]+)(\d+)(m?)$', token)
        if m:
            name, num, unit = m.group(1), int(m.group(2)), m.group(3)
            muscle_group, target_detail = get_muscle_group(name)
            if unit == 'm':
                exercises.append({
                    "exercise_name": name, "sets": None, "duration": num,
                    "type": "cardio", "muscle_group": "유산소", "target_detail": "전신 지구력",
                })
            else:
                exercises.append({
                    "exercise_name": name, "sets": num, "duration": None,
                    "type": "weight", "muscle_group": muscle_group, "target_detail": target_detail,
                })
        else:
            m2 = re.match(r'^([가-힣a-zA-Z]+)$', token)
            if m2:
                name = m2.group(1)
                muscle_group, target_detail = get_muscle_group(name)
                exercises.append({
                    "exercise_name": name, "sets": None, "duration": None,
                    "type": "unknown", "muscle_group": muscle_group, "target_detail": target_detail,
                })
    return exercises


def parse_full_input(text: str) -> dict:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return {"date": str(date.today()), "total_minutes": None, "total_time_str": "", "exercises": [], "raw_text": text}
    result = {"raw_text": text, "exercises": []}
    date_info = parse_date_line(lines[0])
    if date_info:
        result.update(date_info)
        exercise_lines = lines[1:]
    else:
        result.update({"date": str(date.today()), "total_minutes": None, "total_time_str": ""})
        exercise_lines = lines
    for line in exercise_lines:
        result["exercises"].extend(parse_exercise_line(line))
    return result
