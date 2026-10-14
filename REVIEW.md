# REVIEW.md

List every defect you found in the starter `app/main.py` (helpers and endpoints). For each one:

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | | | | |

Also note anything you looked at and decided was **not** a defect, and why.


fix: **line number 101** - paging logic was not working correctly. The `skip` and `limit` values were not being calculated correctly based on the `page` and `page_size` parameters. This would result in incorrect data being returned for paginated requests. i found it while testing through postman and seeing that the data returned was not matching the expected page and page size. I fixed it by updating the calculation of `skip` and `limit` to correctly reflect the requested page and page size since it was skipping the first page and returning the second page instead.

fix: **line number 191**` - The date range filter was not working correctly. The `date_from` and `date_to` parameters were not being applied correctly to the query, resulting in incorrect data being returned for date range requests. I found it while testing through postman and seeing that the data returned was not matching the expected date range. I fixed it by updating the query to correctly apply the `date_from` and `date_to` filters to the query.