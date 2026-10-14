# Employee Attendance & Analytics API

A RESTful API built with **FastAPI** and **MongoDB** to manage employee records, track attendance, handle punch-in/punch-out operations, and generate attendance analytics.

## Features

- **Employee Management** — Create and list employees with department filtering and pagination.
- **Attendance Tracking** — Record employee punch-in and punch-out timestamps.
- **Attendance Regularization** — Correct attendance records with a reason and audit history.
- **Attendance Calculations** — Calculate late arrivals, overtime, and working hours.
- **Analytics** — Generate monthly employee reports, department summaries, late-arrival leaderboards, and department attendance trends.
- **Query Optimization** — MongoDB indexes and aggregation pipelines for efficient data retrieval.
- **Query Explain** — Inspect MongoDB query execution statistics.
- **Health Check** — Check API and database availability.

## Tech Stack

- Python
- FastAPI
- MongoDB
- PyMongo
- Uvicorn

## Prerequisites

Make sure you have installed:

- Python 3.10+
- MongoDB running locally or a MongoDB connection URI
- pip

## Installation

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd <your-project-directory>
```

### 2. Create a virtual environment

**Windows PowerShell**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root and configure your MongoDB connection string and database name according to your application's configuration.

Example:

```env
MONGODB_URI=mongodb://localhost:27017
DATABASE_NAME=employee_attendance
```

> Ensure that the variable names match those used in your application code.

### 5. Start the API

From the project root, run:

```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at:

- **Base URL:** `http://localhost:8000`
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Check API/database health |
| POST | `/employees` | Create an employee |
| GET | `/employees` | List employees with filters and pagination |
| POST | `/attendance/punch-in` | Record punch-in |
| POST | `/attendance/punch-out` | Record punch-out |
| GET | `/attendance` | Retrieve attendance records |
| PATCH | `/attendance/{emp_code}/{date}` | Regularize attendance |
| GET | `/analytics/employees/{emp_code}/monthly` | Employee monthly analytics |
| GET | `/analytics/departments/summary` | Department attendance summary |
| GET | `/analytics/leaderboard/late` | Late-arrival leaderboard |
| GET | `/analytics/departments/{department}/trend` | Department attendance trend |
| GET | `/admin/explain/{endpoint}` | Inspect query execution statistics |

Refer to `/docs` for the exact request schemas, parameters, and response formats.

## Example Requests

### Create an employee

```http
POST /employees
Content-Type: application/json
```

```json
{
  "emp_code": "EMP0099",
  "name": "Demo Employee",
  "email": "demo99@example.com",
  "department": "Engineering",
  "shift_start": "09:30",
  "shift_end": "18:30",
  "joined_on": "2026-10-01"
}
```

### Record punch-in

```http
POST /attendance/punch-in
Content-Type: application/json
```

```json
{
  "emp_code": "EMP0099",
  "punched_at": 1791950400000,
  "status": "PRESENT"
}
```

The `punched_at` value is an example Unix timestamp in milliseconds. Use a valid timestamp for your test date.

### Retrieve attendance records

```http
GET /attendance?emp_code=EMP0001&date_from=2026-07-01&date_to=2026-07-31&page=1&page_size=10
```

### Retrieve monthly employee analytics

```http
GET /analytics/employees/EMP0001/monthly?month=2026-07
```

## Business Rules

- API timestamps are represented as Unix epoch milliseconds.
- Attendance dates use the `YYYY-MM-DD` format.
- Shift times use the `HH:MM` format in Indian Standard Time (IST).
- Attendance calculations account for overnight shifts.
- An employee can have only one attendance record per attendance date.
- Late arrival is counted only when the employee is more than 10 minutes late.
- Overtime is counted only when the employee works at least 30 minutes beyond the shift end.
- Working hours are rounded to two decimal places using half-up rounding.
- A working duration below 4.50 hours is classified as a half day.
- Attendance regularization records changes in audit history.

## Database Indexing

The API uses MongoDB indexes to improve query performance and enforce data integrity.

Expected indexes include:

- Unique employee code.
- Unique employee attendance record per date.
- Date and employee code index for attendance queries.
- Date and status index for attendance filtering.

Indexes must be created by the application or database setup before relying on them.

## Testing

1. Start MongoDB.
2. Start the FastAPI server.
3. Open `http://localhost:8000/docs`.
4. Execute the endpoints using Swagger UI.
5. Test valid requests, invalid inputs, missing employees, duplicate records, and date boundaries.
6. Check query execution statistics using the admin explain endpoints.

## Project Structure

```text
project/
├── app/
│   └── main.py
├── requirements.txt
├── .env
├── DATA_MODEL.md
├── openapi.yaml
├── REVIEW.md
└── README.md
```

## Notes

- Do not commit `.env` files or database credentials.
- Ensure MongoDB is running and the configured database URI is correct.
- The API endpoint list and environment variable names should match the final implementation.
