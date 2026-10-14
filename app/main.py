"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""
import os
from datetime import datetime, timedelta, timezone, date as date_type
from calendar import monthrange
from typing import Optional, Literal
from decimal import Decimal, ROUND_HALF_UP
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
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



@app.post("/attendance/punch-out", status_code=200)
def punch_out(body: PunchOutIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(404, "employee not found")
    ts = datetime.fromtimestamp(body.punched_at / 1000, timezone.utc).replace(microsecond=0, tzinfo=None) if body.punched_at else datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    # Choose the most recent open record punched in no later than this instant;
    # this supports overnight shifts.
    doc = db.attendance_logs.find_one(
        {"emp_code": body.emp_code, "punch_in": {"$ne": None, "$lte": ts}, "punch_out": None},
        sort=[("punch_in", DESCENDING)],
    )
    if not doc:
        prior = db.attendance_logs.find_one({"emp_code": body.emp_code, "punch_in": {"$ne": None, "$lte": ts}}, sort=[("punch_in", DESCENDING)])
        if prior and prior.get("punch_out") is not None:
            raise HTTPException(409, "already punched out for this date")
        raise HTTPException(404, "no punch-in found")
    elapsed = (ts - doc["punch_in"]).total_seconds()
    if elapsed <= 0 or elapsed > 24 * 3600:
        raise HTTPException(422, "punch-out must be after punch-in and within 24 hours")
    hours = compute_work_hours(doc["punch_in"], ts)
    update_data = {
        "punch_out": ts,
        "work_hours": hours,
        "overtime_minutes": compute_overtime(ts, emp["shift_end"], doc["date"], emp["shift_start"]),
        "half_day": hours < 4.50,
        "late_minutes": doc.get("late_minutes", 0),
    }
    result = db.attendance_logs.update_one({"_id": doc["_id"], "punch_out": None}, {"$set": update_data})
    if not result.modified_count:
        raise HTTPException(409, "already punched out for this date")
    doc.update(update_data)
    return api_record(doc)


class RegularizeAttendanceIn(BaseModel):
    status: str
    punch_in: Optional[datetime] = None
    punch_out: Optional[datetime] = None
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)


def validate_date_string(value: str):
    try:
        parsed = date_type.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(422, "date must be YYYY-MM-DD")
    if parsed.isoformat() != value:
        raise HTTPException(422, "date must be YYYY-MM-DD")
    return parsed

@app.patch("/attendance/{emp_code}/{date}")
def update_attendance(emp_code: str, date: str, body: RegularizeAttendanceIn):
    validate_date_string(date)
    emp = db.employees.find_one({"emp_code": emp_code})
    doc = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not emp or not doc:
        raise HTTPException(404, "employee or attendance log not found")
    incoming = body.model_dump(exclude_unset=True)
    if ("punch_in" in incoming and incoming["punch_in"] is None) or ("punch_out" in incoming and incoming["punch_out"] is None):
        raise HTTPException(422, "punch timestamps must be epoch milliseconds, not null")
    status = incoming.get("status", doc.get("status"))
    if status in ("ABSENT", "LEAVE") and ("punch_in" in incoming or "punch_out" in incoming):
        raise HTTPException(422, "ABSENT/LEAVE cannot be supplied with punch times")
    old = {k: doc.get(k) for k in ("status", "punch_in", "punch_out", "work_hours", "late_minutes", "overtime_minutes", "half_day")}
    new_status = status
    if new_status in ("ABSENT", "LEAVE"):
        new_in = new_out = None
        derived = {"work_hours": None, "late_minutes": 0, "overtime_minutes": 0, "half_day": False}
    else:
        new_in = datetime.fromtimestamp(incoming["punch_in"] / 1000, timezone.utc).replace(microsecond=0, tzinfo=None) if "punch_in" in incoming else doc.get("punch_in")
        new_out = datetime.fromtimestamp(incoming["punch_out"] / 1000, timezone.utc).replace(microsecond=0, tzinfo=None) if "punch_out" in incoming else doc.get("punch_out")
        if new_in is None:
            raise HTTPException(422, "presence status requires punch_in")
        if attendance_date(new_in, emp) != date:
            raise HTTPException(422, "punch_in must belong to the attendance date")
        if new_out is not None:
            elapsed = (new_out - new_in).total_seconds()
            if elapsed <= 0 or elapsed > 24 * 3600:
                raise HTTPException(422, "punch_out must be after punch_in and within 24 hours")
            hours = compute_work_hours(new_in, new_out)
            derived = {"work_hours": hours, "late_minutes": compute_late_minutes(new_in, emp["shift_start"]),
                       "overtime_minutes": compute_overtime(new_out, emp["shift_end"], date, emp["shift_start"]), "half_day": hours < 4.50}
        else:
            derived = {"work_hours": None, "late_minutes": compute_late_minutes(new_in, emp["shift_start"]), "overtime_minutes": 0, "half_day": False}
    proposed = {"status": new_status, "punch_in": new_in, "punch_out": new_out, **derived}
    changes = {}
    for key, value in proposed.items():
        previous = old.get(key)
        if previous != value:
            changes[key] = {"from": previous, "to": value}
    if not changes:
        raise HTTPException(422, "regularization does not change the record")
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    history_entry = {"at": now, "by": incoming["regularized_by"], "reason": incoming["reason"], "changes": changes}
    update_fields = dict(proposed)
    # Compare-and-set on history length to avoid silently losing concurrent audit entries.
    history = doc.get("history", [])
    result = db.attendance_logs.update_one(
        {"_id": doc["_id"], "history": {"$size": len(history)}},
        {"$set": update_fields, "$push": {"history": history_entry}},
    )
    if not result.modified_count:
        raise HTTPException(409, "attendance record changed concurrently; retry")
    doc.update(update_fields)
    doc.setdefault("history", []).append(history_entry)
    return api_record(doc)

def month_bounds(month: str):
    try:
        first = date_type.fromisoformat(month + "-01")
    except (ValueError, TypeError):
        raise HTTPException(422, "month must be YYYY-MM")
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(422, "month must be YYYY-MM")
    last = date_type(first.year, first.month, monthrange(first.year, first.month)[1])
    return first.isoformat(), last.isoformat()

def month_logs(month: str, extra_filter=None):
    first, last = month_bounds(month)
    q = {"date": {"$gte": first, "$lte": last}}
    if extra_filter:
        q.update(extra_filter)
    return list(db.attendance_logs.find(q, {"_id": 0}))

def workday_count(start: date_type, end: date_type) -> int:
    if end < start:
        return 0
    return sum(1 for offset in range((end - start).days + 1) if (start + timedelta(days=offset)).weekday() < 5)

def round_num(value, places=2):
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal("1." + "0" * places), rounding=ROUND_HALF_UP))

def present_fraction(doc):
    if doc.get("status") not in ("PRESENT", "WFH", "ON_DUTY"):
        return 0.0
    return 0.5 if doc.get("half_day", False) el





@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(emp_code: str, month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")):
    emp = db.employees.find_one({"emp_code": emp_code}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "employee not found")
    first_s, last_s = month_bounds(month)
    first, last = date_type.fromisoformat(first_s), date_type.fromisoformat(last_s)
    start = max(first, date_type.fromisoformat(emp["joined_on"]))
    working_days = workday_count(start, last) if start <= last else 0
    logs = month_logs(month, {"emp_code": emp_code})
    present_days = sum(present_fraction(d) for d in logs if date_type.fromisoformat(d["date"]).weekday() < 5)
    late = [d for d in logs if d.get("late_minutes", 0) > 0]
    pct = round_num(present_days / working_days * 100, 2) if working_days else None
    return {"emp_code": emp_code, "month": month, "working_days": working_days, "present_days": round_num(present_days),
            "leave_days": sum(d.get("status") == "LEAVE" for d in logs), "late_count": len(late),
            "total_late_minutes": sum(d.get("late_minutes", 0) for d in logs),
            "total_overtime_minutes": sum(d.get("overtime_minutes", 0) for d in logs), "attendance_pct": pct}


@app.get("/analytics/departments/summary")
def department_summary(month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), department: Optional[str] = None):
    _, last_s = month_bounds(month)
    employees_q = {"joined_on": {"$lte": last_s}}
    if department is not None:
        employees_q["department"] = department
    employees = list(db.employees.find(employees_q, {"_id": 0}))
    by_dept = {}
    for emp in employees:
        by_dept.setdefault(emp["department"], []).append(emp)
    logs = month_logs(month)
    emp_dept = {e["emp_code"]: e["department"] for e in employees}
    grouped = {}
    for d in logs:
        dep = emp_dept.get(d.get("emp_code"))
        if dep is not None:
            grouped.setdefault(dep, []).append(d)
    items = []
    for dep in sorted(by_dept):
        rows = grouped.get(dep, [])
        present_days = sum(present_fraction(d) for d in rows if date_type.fromisoformat(d["date"]).weekday() < 5)
        late = [d for d in rows if d.get("late_minutes", 0) > 0]
        hours = [d["work_hours"] for d in rows if d.get("status") in ("PRESENT", "WFH", "ON_DUTY") and d.get("work_hours") is not None]
        items.append({"department": dep, "headcount": len(by_dept[dep]), "present_days": round_num(present_days),
                      "avg_work_hours": round_num(sum(hours) / len(hours)) if hours else None,
                      "late_count": len(late), "total_late_minutes": sum(d.get("late_minutes", 0) for d in late),
                      "leave_count": sum(d.get("status") == "LEAVE" for d in rows),
                      "on_duty_count": sum(d.get("status") == "ON_DUTY" for d in rows)})
    return {"month": month, "items": items}



