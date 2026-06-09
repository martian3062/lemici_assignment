# lemici_assignment

FlowDesk data modeling intern assignment submission plus a runnable Django REST Framework prototype.

## Files

- `data_modeling_intern_assignment.pdf` - Original assignment brief.
- `flowdesk_assignment_submission.md` - Written markdown submission.
- `flowdesk_assignment_submission.pdf` - PDF version of the submission.

## Run Locally

Use the project-local virtualenv only:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health/
```

Core endpoints:

- `POST /api/documents`
- `POST /api/documents/{document_id}/review-actions`
- `GET /api/documents/{document_id}/timeline`

Pass a demo user id from `seed_demo` as the `X-User-Id` request header.

## Test

```powershell
.\.venv\Scripts\python.exe manage.py test
```
