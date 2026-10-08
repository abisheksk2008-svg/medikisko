from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from datetime import datetime
import sqlite3, uuid, hashlib, json, os, re

BASE = Path(__file__).resolve().parent
UPLOAD_DIR = BASE / os.getenv("UPLOAD_DIR", "uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB = BASE / "medikiosk.db"

app = FastAPI(title="MediKiosk API", version="1.0.0")
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in origins], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con=db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS patients(
      id INTEGER PRIMARY KEY AUTOINCREMENT, patient_code TEXT UNIQUE, name TEXT NOT NULL,
      age INTEGER, sex TEXT, phone TEXT, email TEXT, address TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS interviews(
      id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, symptoms TEXT, duration TEXT,
      severity TEXT, history TEXT, medications TEXT, allergies TEXT, notes TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS documents(
      id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, filename TEXT, stored_name TEXT,
      content_type TEXT, size INTEGER, sha256 TEXT, uploaded_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS analyses(
      id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, risk_level TEXT,
      summary TEXT, red_flags TEXT, recommendations TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS reviews(
      id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor TEXT,
      decision TEXT, notes TEXT, reviewed_at TEXT NOT NULL);
    """)
    con.commit(); con.close()

init_db()

class PatientIn(BaseModel):
    name:str
    age:Optional[int]=None
    sex:Optional[str]=""
    phone:Optional[str]=""
    email:Optional[str]=""
    address:Optional[str]=""

class InterviewIn(BaseModel):
    patient_id:int
    symptoms:str
    duration:Optional[str]=""
    severity:Optional[str]="Moderate"
    history:Optional[str]=""
    medications:Optional[str]=""
    allergies:Optional[str]=""
    notes:Optional[str]=""

class AnalysisIn(BaseModel):
    patient_id:int

class ReviewIn(BaseModel):
    patient_id:int
    doctor:str
    decision:str
    notes:Optional[str]=""

@app.get("/api/health")
def health():
    return {"ok":True,"service":"MediKiosk API"}

@app.get("/api/patients")
def patients():
    con=db()
    rows=con.execute("SELECT * FROM patients ORDER BY id DESC").fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/patients")
def create_patient(p:PatientIn):
    con=db()
    code="MK-"+datetime.now().strftime("%Y%m%d")+"-"+uuid.uuid4().hex[:6].upper()
    cur=con.execute("INSERT INTO patients(patient_code,name,age,sex,phone,email,address,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (code,p.name,p.age,p.sex,p.phone,p.email,p.address,datetime.now().isoformat()))
    con.commit()
    row=con.execute("SELECT * FROM patients WHERE id=?",(cur.lastrowid,)).fetchone()
    con.close()
    return dict(row)

@app.get("/api/patients/{patient_id}")
def patient(patient_id:int):
    con=db()
    p=con.execute("SELECT * FROM patients WHERE id=?",(patient_id,)).fetchone()
    if not p: con.close(); raise HTTPException(404,"Patient not found")
    i=con.execute("SELECT * FROM interviews WHERE patient_id=? ORDER BY id DESC",(patient_id,)).fetchall()
    d=con.execute("SELECT * FROM documents WHERE patient_id=? ORDER BY id DESC",(patient_id,)).fetchall()
    a=con.execute("SELECT * FROM analyses WHERE patient_id=? ORDER BY id DESC",(patient_id,)).fetchall()
    r=con.execute("SELECT * FROM reviews WHERE patient_id=? ORDER BY id DESC",(patient_id,)).fetchall()
    con.close()
    return {"patient":dict(p),"interviews":[dict(x) for x in i],"documents":[dict(x) for x in d],"analyses":[dict(x) for x in a],"reviews":[dict(x) for x in r]}

@app.post("/api/interviews")
def create_interview(i:InterviewIn):
    con=db()
    if not con.execute("SELECT 1 FROM patients WHERE id=?",(i.patient_id,)).fetchone():
        con.close(); raise HTTPException(404,"Patient not found")
    cur=con.execute("""INSERT INTO interviews(patient_id,symptoms,duration,severity,history,medications,allergies,notes,created_at)
      VALUES(?,?,?,?,?,?,?,?,?)""",(i.patient_id,i.symptoms,i.duration,i.severity,i.history,i.medications,i.allergies,i.notes,datetime.now().isoformat()))
    con.commit()
    row=con.execute("SELECT * FROM interviews WHERE id=?",(cur.lastrowid,)).fetchone()
    con.close()
    return dict(row)

@app.post("/api/documents/upload")
async def upload_document(patient_id:int=Form(...), file:UploadFile=File(...)):
    con=db()
    if not con.execute("SELECT 1 FROM patients WHERE id=?",(patient_id,)).fetchone():
        con.close(); raise HTTPException(404,"Patient not found")
    safe=re.sub(r"[^A-Za-z0-9._-]","_",file.filename or "document")
    stored=f"{uuid.uuid4().hex}_{safe}"
    path=UPLOAD_DIR/stored
    data=await file.read()
    path.write_bytes(data)
    digest=hashlib.sha256(data).hexdigest()
    cur=con.execute("""INSERT INTO documents(patient_id,filename,stored_name,content_type,size,sha256,uploaded_at)
      VALUES(?,?,?,?,?,?,?)""",(patient_id,file.filename,stored,file.content_type,len(data),digest,datetime.now().isoformat()))
    con.commit()
    row=con.execute("SELECT * FROM documents WHERE id=?",(cur.lastrowid,)).fetchone()
    con.close()
    return dict(row)

def analyze_text(symptoms, history, medications, allergies, severity):
    text=" ".join([symptoms or "",history or "",medications or "",allergies or ""]).lower()
    flags=[]
    patterns={
      "chest pain":"Possible cardiac emergency",
      "difficulty breathing":"Breathing difficulty",
      "shortness of breath":"Breathing difficulty",
      "fainting":"Loss of consciousness",
      "unconscious":"Altered consciousness",
      "severe bleeding":"Severe bleeding",
      "stroke":"Possible stroke symptom",
      "one-sided weakness":"Possible neurological emergency",
      "seizure":"Seizure reported",
      "suicidal":"Mental-health safety concern"
    }
    for k,v in patterns.items():
        if k in text and v not in flags: flags.append(v)
    risk="High" if flags else ("Moderate" if (severity or "").lower()=="severe" or len(text)>220 else "Low")
    summary=f"Reported symptoms: {symptoms or 'Not provided'}. Severity: {severity or 'Not provided'}. Automated screening found {len(flags)} potential red flag(s)."
    rec=["Doctor review is required before diagnosis or treatment decisions."]
    if flags: rec.insert(0,"Urgent clinical assessment should be considered because red-flag language was detected.")
    return risk,summary,flags,rec

@app.post("/api/analysis")
def analysis(a:AnalysisIn):
    con=db()
    row=con.execute("SELECT * FROM interviews WHERE patient_id=? ORDER BY id DESC",(a.patient_id,)).fetchone()
    if not row: con.close(); raise HTTPException(400,"Complete a patient interview first")
    risk,summary,flags,recs=analyze_text(row["symptoms"],row["history"],row["medications"],row["allergies"],row["severity"])
    cur=con.execute("INSERT INTO analyses(patient_id,risk_level,summary,red_flags,recommendations,created_at) VALUES(?,?,?,?,?,?)",
                    (a.patient_id,risk,summary,json.dumps(flags),json.dumps(recs),datetime.now().isoformat()))
    con.commit()
    out=con.execute("SELECT * FROM analyses WHERE id=?",(cur.lastrowid,)).fetchone()
    con.close()
    result=dict(out); result["red_flags"]=json.loads(result["red_flags"]); result["recommendations"]=json.loads(result["recommendations"])
    return result

@app.get("/api/dashboard")
def dashboard():
    con=db()
    total=con.execute("SELECT COUNT(*) c FROM patients").fetchone()["c"]
    interviews=con.execute("SELECT COUNT(*) c FROM interviews").fetchone()["c"]
    docs=con.execute("SELECT COUNT(*) c FROM documents").fetchone()["c"]
    high=con.execute("SELECT COUNT(*) c FROM analyses WHERE risk_level='High'").fetchone()["c"]
    recent=con.execute("""SELECT p.id,p.patient_code,p.name,p.age,p.sex,p.created_at,
       a.risk_level,a.summary FROM patients p LEFT JOIN analyses a ON a.id=(SELECT MAX(id) FROM analyses WHERE patient_id=p.id)
       ORDER BY p.id DESC LIMIT 10""").fetchall()
    con.close()
    return {"stats":{"patients":total,"interviews":interviews,"documents":docs,"high_risk":high},"recent":[dict(x) for x in recent]}

@app.post("/api/reviews")
def review(r:ReviewIn):
    con=db()
    if not con.execute("SELECT 1 FROM patients WHERE id=?",(r.patient_id,)).fetchone():
        con.close(); raise HTTPException(404,"Patient not found")
    cur=con.execute("INSERT INTO reviews(patient_id,doctor,decision,notes,reviewed_at) VALUES(?,?,?,?,?)",
                    (r.patient_id,r.doctor,r.decision,r.notes,datetime.now().isoformat()))
    con.commit()
    row=con.execute("SELECT * FROM reviews WHERE id=?",(cur.lastrowid,)).fetchone()
    con.close()
    return dict(row)
