# REVIEW.md

I reviewed the starter code against the API contract and data model. The following defects were identified-

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | `health()` | It always returns `ok` without checking MongoDB connectivity. | Stop MongoDB and call `/health`; it still reports success. | Added a MongoDB `ping` and return HTTP 503 on failure. |
| 2 | `create_employee()` | Checking for duplicates before insertion is not concurrency-safe. It also does not validate shift times or `joined_on`. | Send simultaneous requests with the same employee code, or invalid dates. | Added a unique employee-code index, handled `DuplicateKeyError`, and validated input. |
| 3 | `create_employee()` | `created_at` uses local server time rather than a consistent UTC instant, and the response does not follow the required timestamp format. | Run the server in a different timezone and compare responses. | Store UTC datetimes and serialize timestamps as epoch milliseconds. |
| 4 | `list_employees()` | The skip calculation is incorrect: page 1 skips `page_size` records instead of zero. The total count also ignores the department filter. | Request page 1 with 10 records or filter by department and compare totals. | Used `(page - 1) * page_size`, counted matching documents, and validated pagination. |
| 5 | `list_employees()` | It lacks a stable sort and pagination bounds validation. | Repeat paginated requests or pass page 0 and an excessive page size. | Added sorting by employee code and validated page and page size. |
| 6 | `compute_late_minutes()` | It compares naive datetimes without converting the punch-in instant to IST. | Use a UTC punch-in near the shift-start boundary. | Convert punch-in to IST before comparing it with the shift start; apply the strict greater-than-10-minute rule. |
| 7 | `compute_work_hours()` | Python's built-in `round()` does not guarantee the contract's half-up rounding rule. | Test durations exactly halfway between two hundredths. | Used decimal rounding with `ROUND_HALF_UP`. |
| 8 | `compute_overtime()` | It does not correctly handle overnight shifts and does not enforce the minimum 30-minute overtime threshold. | Test a 22:00–06:00 shift or a punch-out 10 minutes after shift end. | Accounted for overnight shifts and count overtime only when it reaches 30 minutes. |
| 9 | `punch_in()` | It does not check whether the employee exists or whether the status is valid. | Punch in with an unknown employee or an invalid status. | Added employee-existence and status validation. |
| 10 | `punch_in()` | It uses local time, treats timestamps as seconds after dividing by nothing, and derives the date directly from the server's timezone. It also mishandles overnight shifts. | Send epoch milliseconds or punch in shortly after midnight during a night shift. | Validated epoch milliseconds, converted them to UTC, and derived the attendance date in IST using the employee's shift. |
| 11 | `punch_in()` | The existence check followed by insertion is vulnerable to concurrent requests. | Send two simultaneous punch-ins for the same employee and date. | Added a unique compound index on `(emp_code, date)` and handled duplicate-key errors. |
| 12 | `punch_in()` | The response includes a database datetime instead of the API's required epoch-millisecond representation. | Inspect the returned `punch_in` value. | Added response serialization for attendance timestamps and related fields. |
| 13 | `list_attendance()` | It loads all matching records into Python before sorting and paginating, which wastes memory and database/network resources. | Test with a large attendance collection. | Moved sorting, skipping, and limiting into the MongoDB query. |
| 14 | `list_attendance()` | It does not validate date strings, date-range ordering, status values, or pagination bounds. | Pass malformed dates, reversed date ranges, invalid statuses, or page 0. | Added input validation and appropriate HTTP 422 responses. |
| 15 | `list_attendance()` | It sorts and counts records in Python instead of using database sorting and counting. | Inspect database operations and test with a large dataset. | Used `count_documents()` and MongoDB sorting before pagination. |
| 16 | Missing `POST /attendance/punch-out` | The starter does not implement punch-out, work-hour calculation, overtime calculation, or half-day determination. | Call the documented punch-out route. | Implemented the route with timestamp, duration, and attendance validation. |
| 17 | Missing `PATCH /attendance/{emp_code}/{date}` | There is no attendance regularization or audit history. | Call the documented PATCH route. | Added regularization, derived-field recalculation, and history entries. |
| 18 | Missing monthly and department analytics routes | Employee monthly analytics, department summary, and late-arrival leaderboard are absent. | Call the three documented analytics routes. | Implemented the corresponding analytics endpoints using stored attendance values. |
| 19 | Missing department trend route | Daily department statistics, missing-date handling, and the seven-day moving average are absent. | Request a department trend over a date range. | Implemented daily trend output and moving-average calculations. |
| 20 | Missing admin explain route | There is no endpoint to inspect database execution plans and execution statistics. | Call `/admin/explain/attendance_list`. | Added the explain endpoint using MongoDB's `executionStats` mode. |

## Reviewed but not considered defects

- **HTTP 201 for employee creation and punch-in:** Appropriate because both operations create resources.
- **Optional `punched_at`:** This is intentional; the server can use the current time when the client does not provide one.
- **String attendance dates:** Appropriate because the data model specifies dates in `YYYY-MM-DD` format.
- **`IST = timezone(timedelta(hours=5, minutes=30))`:** A valid fixed-offset timezone for India, which does not observe daylight saving time.
- **Separate `compute_late_minutes()`, `compute_work_hours()`, and `compute_overtime()` helpers:** Keeping reusable calculation logic separate improves readability and consistency.