"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))  #add this to UTC time to get IST time. This is used to ensure that the punch-in and punch-out times are stored in IST timezone in the database, regardless of the timezone of the server or client making the request.

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def attendance_date(ts: datetime, emp: dict) -> str:
    local = ts.replace(tzinfo=timezone.utc).astimezone(IST) if ts.tzinfo is None else ts.astimezone(IST)
    if emp["shift_end"] <= emp["shift_start"] and local.strftime("%H:%M") < emp["shift_end"]:
        local -= timedelta(days=1)
    return local.date().isoformat()



def api_record(doc):
    out = {k: v for k, v in doc.items() if k != "_id"}
    for key in ("punch_in", "punch_out"):
        out[key] = epoch_ms(out.get(key))
    out.setdefault("work_hours", None)
    out.setdefault("late_minutes", 0)
    out.setdefault("overtime_minutes", 0)
    out.setdefault("half_day", False)
    out.setdefault("history", [])
    for entry in out["history"]:
        entry["at"] = epoch_ms(entry.get("at"))
        for change in entry.get("changes", {}).values():
            for side in ("from", "to"):
                if isinstance(change.get(side), datetime):
                    change[side] = epoch_ms(change[side])
    return out


def epoch_ms(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def compute_late_minutes(punch_in: datetime, shift_start: str) -> int:
    h, m = map(int, shift_start.split(":"))
    start = punch_in.replace(hour=h, minute=m, second=0, microsecond=0)
    minutes = int((punch_in - start).total_seconds() / 60)
    return minutes if minutes > 10 else 0


def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    return round((punch_out - punch_in).total_seconds() / 3600, 2)


def compute_overtime(punch_out: datetime, shift_end: str, date_str: str) -> int:
    h, m = map(int, shift_end.split(":"))
    end = datetime.fromisoformat(date_str).replace(hour=h, minute=m, second=0, microsecond=0, tzinfo=IST)
    if punch_out.tzinfo is None:
        punch_out = punch_out.replace(tzinfo=IST)
    else:
        punch_out = punch_out.astimezone(IST)

    overtime_minutes = int((punch_out - end).total_seconds() / 60)
    return max(0, int(overtime_minutes))


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class EmployeeIn(BaseModel):
    emp_code: str
    name: str
    email: str
    department: str
    shift_start: str = "09:30"
    shift_end: str = "18:30"
    joined_on: str


class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None
    status: str = "PRESENT"




# --------------------------------------------------------------------------- #
# Endpoints provided
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    if db.employees.find_one({"emp_code": body.emp_code}):
        raise HTTPException(409, "emp_code already exists")
    doc = body.model_dump()
    doc["created_at"] = datetime.now()
    db.employees.insert_one(doc)
    doc.pop("_id", None)
    return doc


@app.get("/employees")
def list_employees(department: Optional[str] = None, page: int = 1, page_size: int = 20):
    q = {}
    if department:
        q["department"] = department
    skip = (page - 1) * page_size   #because of wrong page calculation in the original code, we need to calculate the number of documents to skip based on the current page and page size.
    total = db.employees.count_documents({})
    items = list(db.employees.find(q, {"_id": 0}).skip(skip).limit(page_size))
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(404, "employee not found")
    if body.status not in ("PRESENT", "WFH", "ON_DUTY"):
        raise HTTPException(400, "invalid punch-in status")
    ts = datetime.fromtimestamp(body.punched_at / 1000, timezone.utc).replace(microsecond=0, tzinfo=None) if body.punched_at else datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    d = attendance_date(ts, emp)
    if db.attendance_logs.find_one({"emp_code": body.emp_code, "date": d}):
        raise HTTPException(409, "already punched in for this date")
    doc = {
        "emp_code": body.emp_code,
        "date": d,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(ts, emp["shift_start"]),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }
    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "already punched in for this date")
    return api_record(doc)


@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    q = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, "date_from cannot be greater than date_to")
    if status:
        if status not in ("PRESENT", "WFH", "ON_DUTY", "ABSENT", "LEAVE"):
            raise HTTPException(422, "invalid status")
        q["status"] = status
    total = db.attendance_logs.count_documents(q)
    docs = list(db.attendance_logs.find(q, {"_id": 0}).sort([("date", DESCENDING), ("emp_code", ASCENDING)]).skip((page - 1) * page_size).limit(page_size))
    return {"items": [api_record(d) for d in docs], "total": total, "page": page, "page_size": page_size}



# --------------------------------------------------------------------------- #
# TODO - the rest of the contract (see openapi.yaml):
#   POST  /attendance/punch-out -- done
#   PATCH /attendance/{emp_code}/{date} 
#   GET   /analytics/employees/{emp_code}/monthly
#   GET   /analytics/departments/summary
#   GET   /analytics/leaderboard/late
#   GET   /analytics/departments/{department}/trend
#   GET   /admin/explain/{endpoint}
# --------------------------------------------------------------------------- #



class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None



@app.post("/attendance/punch-out", status_code=201)
def punch_out(body: PunchOutIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    ts = datetime.fromtimestamp(body.punched_at / 1000) if body.punched_at else datetime.now()
    d = ts.date().isoformat()
    doc = db.attendance_logs.find_one({"emp_code": body.emp_code, "date": d})
    if not doc:
        raise HTTPException(404, "no punch-in found for this date")
    if doc["punch_out"]:
        raise HTTPException(409, "already punched out for this date")
    update_data = {
        "punch_out": ts,
        "work_hours": compute_work_hours(doc["punch_in"], ts),
        "late_minutes": doc["late_minutes"],
        "overtime_minutes": compute_overtime(ts, emp["shift_end"], datetime.fromisoformat(doc["date"]).isoformat()),
    }
    res = db.attendance_logs.update_one({"_id": doc["_id"]}, {"$set": update_data})
    if not res.modified_count:
        raise HTTPException(500, "failed to update attendance log")
    doc.update(update_data)
    doc["id"] = str(doc.pop("_id"))
    return doc


class RegularizeAttendanceIn(BaseModel):
    status: str
    punch_in: Optional[datetime] = None
    punch_out: Optional[datetime] = None
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)

@app.patch("/attendance/{emp_code}/{date}")
def update_attendance(emp_code: str, date: str, body: RegularizeAttendanceIn):
    doc = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not doc:
        raise HTTPException(404, "attendance log not found")    
