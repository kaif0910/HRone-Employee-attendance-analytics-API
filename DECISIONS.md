# DECISIONS.md

### 1. Indexes
I considered a unique index on `emp_code` in employees and a compound unique index on `(emp_code, date)` in attendance logs. The first prevents duplicate employee codes, while the second guarantees one attendance record per employee per date. I also considered indexes on `(date, emp_code)` for attendance listing and `(date, status)` for filtered queries. However, the index-creation code is currently commented out, so these indexes are not created by that code.

### 2. Punch-in race
Two identical punch-in requests can both check for an existing record and find none. Both may then try to insert. The code catches `DuplicateKeyError`, which returns a conflict for the losing request, but this protection requires the unique compound index to be active. Without it, both inserts could succeed.

### 3. Ties
The leaderboard sorts employees by total late minutes, then by employee code. Employees tied at the cutoff receive the same rank, and all employees with that rank are included, even if the result exceeds `limit`.

### 4. Headcount
The department summary starts with employees who joined by the month's end, groups them by department, and calculates headcount independently of attendance logs. Therefore, employees without logs are still counted.

### 5. Scaling
I would move analytics calculations into MongoDB aggregation pipelines and enable appropriate indexes to reduce data transferred and processed in Python.
