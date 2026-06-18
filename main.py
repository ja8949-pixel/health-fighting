"""운동 기록 앱 - FastAPI 백엔드"""

import os
import uuid
from datetime import date as _date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import get_db, create_tables, Workout, WorkoutDetail, User, IS_POSTGRES, DATABASE_URL
from workout_parser import parse_full_input, MUSCLE_META

load_dotenv()

app = FastAPI(title="운동 기록 앱")

BASE_DIR = Path(__file__).parent
IS_VERCEL = bool(os.getenv("VERCEL"))

# Vercel은 /tmp만 쓰기 가능. 로컬은 static/uploads 사용
UPLOAD_DIR = Path("/tmp/uploads") if IS_VERCEL else BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 로컬 개발용 static 마운트 (Vercel에서는 /api/uploads/ 엔드포인트로 대체)
if not IS_VERCEL:
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
def startup():
    create_tables()


# ── 업로드 파일 서빙 (Vercel /tmp + 로컬 static/uploads 양쪽 지원) ───────────
@app.get("/api/uploads/{filename}")
async def serve_upload(filename: str):
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    return FileResponse(path)


# ── 메인 페이지 ───────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── DB 상태 확인 (디버깅용) ───────────────────────────────────────────────────
@app.get("/api/dbstatus")
def db_status(db: Session = Depends(get_db)):
    try:
        user_cnt = db.query(User).count()
        workout_cnt = db.query(Workout).count()
        db_type = "PostgreSQL (영구저장 ✅)" if IS_POSTGRES else "SQLite"
        location = "외부 DB" if IS_POSTGRES else ("/tmp (임시⚠️)" if IS_VERCEL else "로컬 파일 (영구저장 ✅)")
        return {
            "db_type": db_type,
            "location": location,
            "is_persistent": IS_POSTGRES or (not IS_VERCEL),
            "users": user_cnt,
            "workouts": workout_cnt,
        }
    except Exception as e:
        return {"error": str(e)}


# ── 로그인 (이름 + 비밀번호 4자리) ──────────────────────────────────────────────
@app.post("/api/login")
async def login(
    name: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        raise HTTPException(400, "이름을 입력해 주세요.")
    if not password.isdigit() or len(password) != 4:
        raise HTTPException(400, "비밀번호는 숫자 4자리를 입력해 주세요.")

    user = db.query(User).filter(
        User.name == name,
        User.password == password,
    ).first()

    if not user:
        # 같은 이름의 다른 비밀번호 사용자가 있는지 확인
        existing = db.query(User).filter(User.name == name).first()
        if existing:
            raise HTTPException(401, "비밀번호가 틀렸어요.")
        # 신규 사용자 생성
        user = User(name=name, password=password)
        db.add(user)
        db.commit()
        db.refresh(user)

    return {"user_id": user.id, "name": user.name, "is_new": False, "message": "ok"}


# ── 파싱 미리보기 ─────────────────────────────────────────────────────────────
@app.post("/api/parse-preview")
async def parse_preview(request: Request):
    body = await request.json()
    text = body.get("text", "")
    override_date = body.get("date")
    override_hours = body.get("hours")
    override_minutes = body.get("minutes")

    parsed = parse_full_input(text) if text.strip() else {
        "raw_text": "", "exercises": [], "date": "", "total_minutes": None, "total_time_str": ""
    }
    if override_date:
        parsed["date"] = override_date
    total = (override_hours or 0) * 60 + (override_minutes or 0)
    if total > 0:
        parsed["total_minutes"] = total
        h, m = override_hours or 0, override_minutes or 0
        parsed["total_time_str"] = f"{h}h {m}m" if h and m else (f"{h}h" if h else f"{m}m")

    return parsed


# ── 운동 기록 목록 ─────────────────────────────────────────────────────────────
@app.get("/api/workouts")
def list_workouts(user_id: int, db: Session = Depends(get_db)):
    workouts = (
        db.query(Workout)
        .filter(Workout.user_id == user_id)
        .order_by(Workout.date.desc(), Workout.created_at.desc())
        .all()
    )
    result = []
    for w in workouts:
        details = sorted(w.details, key=lambda x: x.order_index)
        result.append({
            "id": w.id,
            "date": w.date,
            "total_minutes": w.total_minutes,
            "total_time_str": w.total_time_str,
            "photo_url": w.photo_url,
            "raw_text": w.raw_text,
            "created_at": w.created_at.isoformat() if w.created_at else None,
            "details": [
                {
                    "id": d.id,
                    "exercise_name": d.exercise_name,
                    "sets": d.sets,
                    "duration": d.duration,
                    "exercise_type": d.exercise_type,
                    "muscle_group": d.muscle_group or "기타",
                    "target_detail": d.target_detail or "",
                    "order_index": d.order_index,
                }
                for d in details
            ],
        })
    return result


# ── 운동 기록 생성 ─────────────────────────────────────────────────────────────
@app.post("/api/workouts")
async def create_workout(
    text: str = Form(""),
    user_id: int = Form(...),
    workout_date: Optional[str] = Form(None),
    hours: Optional[int] = Form(None),
    mins: Optional[int] = Form(None),
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    # 사용자 존재 확인
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "사용자를 찾을 수 없습니다.")

    parsed = parse_full_input(text)
    if workout_date:
        parsed["date"] = workout_date
    total = (hours or 0) * 60 + (mins or 0)
    if total > 0:
        parsed["total_minutes"] = total
        h, m = hours or 0, mins or 0
        parsed["total_time_str"] = f"{h}h {m}m" if h and m else (f"{h}h" if h else f"{m}m")
    if not parsed.get("date"):
        parsed["date"] = str(_date.today())

    photo_url = None
    if photo and photo.filename:
        ext = Path(photo.filename).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}:
            raise HTTPException(400, "지원하지 않는 파일 형식입니다.")
        content = await photo.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(400, "파일 크기는 10MB 이하여야 합니다.")
        filename = f"{uuid.uuid4().hex}{ext}"
        with open(UPLOAD_DIR / filename, "wb") as f:
            f.write(content)
        # /api/uploads/ 경로로 통일 (Vercel + 로컬 모두 동작)
        photo_url = f"/api/uploads/{filename}"

    workout = Workout(
        user_id=user_id,
        date=parsed["date"],
        total_minutes=parsed.get("total_minutes"),
        total_time_str=parsed.get("total_time_str", ""),
        photo_url=photo_url,
        raw_text=text,
    )
    db.add(workout)
    db.flush()

    for idx, ex in enumerate(parsed.get("exercises", [])):
        db.add(WorkoutDetail(
            workout_id=workout.id,
            exercise_name=ex["exercise_name"],
            sets=ex.get("sets"),
            duration=ex.get("duration"),
            exercise_type=ex.get("type", "weight"),
            muscle_group=ex.get("muscle_group", "기타"),
            target_detail=ex.get("target_detail", ""),
            order_index=idx,
        ))

    db.commit()
    db.refresh(workout)
    return {"id": workout.id, "date": workout.date, "message": "저장 완료"}


# ── 운동 기록 삭제 ─────────────────────────────────────────────────────────────
@app.delete("/api/workouts/{workout_id}")
def delete_workout(workout_id: int, user_id: int, db: Session = Depends(get_db)):
    workout = db.query(Workout).filter(
        Workout.id == workout_id,
        Workout.user_id == user_id,
    ).first()
    if not workout:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    if workout.photo_url:
        # URL에서 파일명만 추출해 UPLOAD_DIR 기준으로 삭제
        photo_path = UPLOAD_DIR / Path(workout.photo_url).name
        if photo_path.exists():
            photo_path.unlink()
    db.delete(workout)
    db.commit()
    return {"message": "삭제 완료"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
