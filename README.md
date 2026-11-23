# Task Manager REST API

A production-grade Django & Django REST Framework (DRF) REST API for intelligent task management. The API allows creating tasks in plain natural language (e.g., *"Remind me to pay rent on the 1st of every month"*), managing subtasks and automated task breakdown, enforcing safe idempotent retries, providing uniform error responses, and supporting rich filtering, search, ordering, and pagination.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Architecture](#project-architecture)
- [Setup & Running Instructions](#setup--running-instructions)
  - [Prerequisites](#prerequisites)
  - [Docker Setup (Recommended)](#option-1-docker-setup-recommended)
  - [Local Setup](#option-2-local-setup)
- [API Endpoints Overview](#api-endpoints-overview)
- [Detailed API Specifications & Examples](#detailed-api-specifications--examples)
  - [1. Standard Task CRUD](#1-standard-task-crud)
  - [2. Consistent Error Response Shape](#2-consistent-error-response-shape)
  - [3. Natural Language Task Creation (/from-text/)](#3-natural-language-task-creation-api-tasks-from-text)
  - [4. Subtasks and Task Breakdown](#4-subtasks-and-task-breakdown)
  - [5. Idempotent Creation (Idempotency-Key Header)](#5-idempotent-creation-idempotency-key-header)
  - [6. Filtering, Search, Ordering, and Pagination](#6-filtering-search-ordering-and-pagination)
- [Natural Language Parser Function Signature](#natural-language-parser-function-signature)
- [AI Testing & Hardening Critique](#ai-testing--hardening-critique)
- [OpenAPI Specification](#openapi-specification)

---

## Features

- **Natural Language Parsing**: Accepts unstructured sentences, extracting structured titles, descriptions, due dates (such as *"tomorrow"*, *"on the 1st"*), priorities, and recurrences.
- **"Never Trust The Output" Rule**: All parser outputs pass through strict `TaskSerializer` validation before saving. If parser output is invalid or fails, it returns `502 Bad Gateway` and writes nothing to the database.
- **Swappable LLM Architecture**: Built behind `parse_task_text`. Includes an optional LLM wrapper mode checking `LLM_API_KEY` (returning `503 Service Unavailable` if the key is missing).
- **Subtasks & Atomic Breakdown**: Supports 1-level hierarchical subtasks with cascade delete. `breakdown` splits a task into actionable items and commits atomically (all-or-nothing). A subtask cannot be given subtasks or broken down (rejects with `400 Bad Request`).
- **Safe Idempotent Retries**: Accepts an `Idempotency-Key` header on creation and breakdown endpoints. Replaying the same request body returns the cached response with zero duplicate database writes. Replaying the same key with a modified payload returns `422 Unprocessable Entity`.
- **One Consistent Error Shape**: All 400, 404, 422, 502, and 503 error responses strictly conform to:
  ```json
  {
    "error": {
      "code": "VALIDATION_ERROR",
      "message": "Validation failed",
      "details": [{ "field": "title", "issue": "must not be empty" }]
    }
  }
  ```
- **Combined Query Capabilities**: Filtering (`completed`, `priority`, `due_date`, `is_parent`), full-text search (`title`, `description`), ordering (`due_date`, `created_at`, `priority`), and page-number pagination work seamlessly in a single request.

---

## Tech Stack

- **Framework**: Django 6.1.1
- **REST Framework**: Django REST Framework (DRF) 3.18.1
- **Filtering**: django-filter 26.1
- **Database**: PostgreSQL 16 Alpine
- **Configuration**: python-decouple 3.8
- **Containerization**: Docker & Docker Compose

---

## Project Architecture

```text
task_manager/
├── manage.py
├── requirements.txt
├── DockerFile
├── docker-compose.yml
├── openapi.yaml
├── task_manager.postman_collection.json
├── README.md
├── logs/
│   └── app.out.console.log
├── task_manager/
│   ├── __init__.py
│   ├── asgi.py
│   ├── urls.py
│   ├── wsgi.py
│   └── settings/
│       ├── __init__.py          # Dynamic environment selector (DJANGO_ENV)
│       ├── base.py              # Core settings, DRF configuration, static files
│       ├── database.py          # Decoupled PostgreSQL database settings
│       ├── development.py       # Development profile (DEBUG=True, ALLOWED_HOSTS=['*'])
│       ├── logger.py            # Console and rotating file logging
│       ├── production.py        # Strict production security & SSL settings
│       └── QA.py                # QA preview host patterns and test mailer
└── tasks/
    ├── __init__.py
    ├── admin.py                 # Task Django Admin registration
    ├── ai.py                    # Natural language parser & task breakdown logic
    ├── errors.py                # Error helper & custom exception handler
    ├── filters.py               # Django-filter FilterSet for Task
    ├── idempotency.py           # Idempotency header cache and conflict handler
    ├── models.py                # Task model with self-referential ForeignKey
    ├── serializers.py           # TaskSerializer & SubtaskSummarySerializer
    ├── tests.py                 # Automated test suite (23 test cases)
    ├── urls.py                  # DefaultRouter URL routing
    └── views.py                 # TaskViewSet ModelViewSet implementation
```

---

## Setup & Running Instructions

### Prerequisites
- Docker & Docker Compose (or Python 3.10+ and a local PostgreSQL instance).

---

### Option 1: Docker Setup (Recommended)

1. **Clone or navigate to the directory**:
   ```bash
   cd task_manager
   ```

2. **Verify or configure your environment file (`.env`)**:
   ```env
   DJANGO_ENV=development
   DEBUG=True
   SECRET_KEY=django-insecure-8f3a9e2c1b4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e
   APP_PORT=8000
   LOG_LEVEL=INFO
   POSTGRES_DB=task_manager_db
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=postgres
   POSTGRES_HOST=db
   POSTGRES_PORT=5432
   POSTGRES_HOST_PORT=5433
   # Optional: set your key if using the LLM mode
   # LLM_API_KEY=your-api-key-here
   ```

3. **Start the containers**:
   ```bash
   docker compose up --build -d
   ```

4. **Run migrations inside the web container**:
   ```bash
   docker compose exec web python manage.py migrate
   ```

5. **Execute automated tests**:
   ```bash
   docker compose exec web python manage.py test
   ```
   The API is accessible at `http://localhost:8000/api/tasks/`.

---

### Option 2: Local Setup

1. **Create and activate a virtual environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. **Install project dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run database migrations**:
   ```bash
   python manage.py migrate
   ```

4. **Start the development server**:
   ```bash
   python manage.py runserver
   ```

---

## API Endpoints Overview

| Method | Endpoint | Description | Idempotent |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/tasks/` | List, filter, search, order, and paginate tasks | Safe |
| `POST` | `/api/tasks/` | Create a new task | Supports `Idempotency-Key` |
| `GET` | `/api/tasks/{id}/` | Retrieve task details and nested subtasks | Safe |
| `PUT` | `/api/tasks/{id}/` | Update all task fields | Yes |
| `PATCH` | `/api/tasks/{id}/` | Partially update a task | Yes |
| `DELETE` | `/api/tasks/{id}/` | Delete task and cascade delete its subtasks | Yes |
| `POST` | `/api/tasks/from-text/` | Create task from natural language text | Supports `Idempotency-Key` |
| `GET` | `/api/tasks/{id}/subtasks/` | List all child subtasks of a parent | Safe |
| `POST` | `/api/tasks/{id}/subtasks/` | Create a single subtask for a parent | No |
| `POST` | `/api/tasks/{id}/breakdown/` | Atomically break down a task into subtasks | Supports `Idempotency-Key` |

---

## Detailed API Specifications & Examples

### 1. Standard Task CRUD

#### `POST /api/tasks/`
**Request Payload**:
```json
{
  "title": "Prepare Annual Taxes",
  "description": "Gather W-2s, receipts, and file before deadline",
  "priority": "high",
  "due_date": "2026-04-15",
  "completed": false
}
```
**Response (`201 Created`)**:
```json
{
  "id": 1,
  "title": "Prepare Annual Taxes",
  "description": "Gather W-2s, receipts, and file before deadline",
  "completed": false,
  "due_date": "2026-04-15",
  "priority": "high",
  "recurrence": null,
  "parent": null,
  "created_at": "2026-11-23T12:00:00Z",
  "updated_at": "2026-11-23T12:00:00Z",
  "subtasks": []
}
```

---

### 2. Consistent Error Response Shape

Every error response (`400`, `404`, `422`, `502`, `503`) strictly adheres to this structure:

#### Example: Validation Error (`400 Bad Request`)
If `title` is empty and `due_date` is impossible (e.g. `2026-02-30`):
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed",
    "details": [
      { "field": "title", "issue": "must not be empty" },
      { "field": "due_date", "issue": "must be a real YYYY-MM-DD date" }
    ]
  }
}
```

#### Example: Not Found (`404 Not Found`)
```http
GET /api/tasks/99999/
```
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Task not found",
    "details": []
  }
}
```

---

### 3. Natural Language Task Creation (`/api/tasks/from-text/`)

**Request**:
```json
{
  "text": "Remind me to pay rent on the 1st of every month"
}
```
**Response (`201 Created`)**:
```json
{
  "id": 2,
  "title": "Pay rent",
  "description": "Remind me to pay rent on the 1st of every month",
  "completed": false,
  "due_date": "2026-12-01",
  "priority": "medium",
  "recurrence": "on the 1st of every month",
  "parent": null,
  "created_at": "2026-11-23T12:05:00Z",
  "updated_at": "2026-11-23T12:05:00Z",
  "subtasks": []
}
```

- **Validation Safeguard**: If the parser outputs an empty title or invalid date, it triggers `502 Bad Gateway` with `PARSER_VALIDATION_ERROR` and nothing is saved.
- **LLM Key Safeguard**: Passing `"use_llm": true` when `LLM_API_KEY` is unset returns `503 Service Unavailable`.

---

### 4. Subtasks and Task Breakdown

#### Create a Subtask (`POST /api/tasks/{id}/subtasks/`)
```json
{
  "title": "Gather receipts",
  "description": "Collect utility and business receipts for deduction",
  "priority": "medium"
}
```
**Response (`201 Created`)**:
```json
{
  "id": 3,
  "title": "Gather receipts",
  "description": "Collect utility and business receipts for deduction",
  "completed": false,
  "due_date": null,
  "priority": "medium",
  "recurrence": null,
  "parent": 1,
  "created_at": "2026-11-23T12:10:00Z",
  "updated_at": "2026-11-23T12:10:00Z",
  "subtasks": []
}
```

#### Automatic Atomic Breakdown (`POST /api/tasks/{id}/breakdown/`)
Splits the task into subtasks based on clauses or action templates.
**Response (`201 Created`)**:
```json
[
  {
    "id": 4,
    "title": "Research and prepare requirements for Prepare Annual Taxes",
    "description": "Subtask generated from parent task 'Prepare Annual Taxes'",
    "completed": false,
    "due_date": "2026-04-15",
    "priority": "high",
    "parent": 1
  },
  {
    "id": 5,
    "title": "Execute implementation for Prepare Annual Taxes",
    "description": "Subtask generated from parent task 'Prepare Annual Taxes'",
    "completed": false,
    "due_date": "2026-04-15",
    "priority": "high",
    "parent": 1
  }
]
```

- **Hierarchy Guard**: Attempting to add a subtask to or break down a task that is itself a subtask returns `400 Bad Request` (`INVALID_SUBTASK` or `INVALID_BREAKDOWN`).
- **Cascade Deletion**: Deleting the parent task automatically deletes all its child subtasks.

---

### 5. Idempotent Creation (`Idempotency-Key` Header)

Send an optional `Idempotency-Key: <unique-key>` header with `POST /api/tasks/`, `POST /api/tasks/from-text/`, or `POST /api/tasks/{id}/breakdown/`.

1. **First Request**: Returns `201 Created` and persists the record.
2. **Duplicate Request (Same Body)**: Returns the stored `201 Created` response immediately without writing duplicate rows or re-running parsers.
3. **Conflicting Request (Same Key, Different Body)**: Returns `422 Unprocessable Entity`:
   ```json
   {
     "error": {
       "code": "IDEMPOTENCY_CONFLICT",
       "message": "Idempotency key already used with a different request body",
       "details": []
     }
   }
   ```
4. **Failed Requests**: Only successful responses (`2xx`) are cached. If a request fails with `400 Bad Request`, the client can correct the body and retry with the same key.

---

### 6. Filtering, Search, Ordering, and Pagination

All query parameters combine cleanly:
```http
GET /api/tasks/?completed=false&priority=high&search=Proposal&ordering=-due_date&page=1&page_size=10
```

**Response (`200 OK`)**:
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Finalize Proposal",
      "description": "Proposal budget and scope",
      "completed": false,
      "due_date": "2026-12-01",
      "priority": "high",
      "recurrence": null,
      "parent": null,
      "subtasks": []
    }
  ]
}
```

---

## Natural Language Parser Function Signature

The parser in [`tasks/ai.py`](file:///D:/projects/airtribe/projects/task_manager/tasks/ai.py) is intentionally decoupled so it can be swapped for an OpenAI, Anthropic, or Gemini LLM call without altering view or serializer logic:

```python
def parse_task_text(text: str, today: Optional[datetime.date] = None) -> Dict[str, Any]:
    """
    Parses natural language task text into a structured task dictionary.
    
    Args:
        text: Raw natural language string from the client.
        today: Reference date for relative calculations (defaults to datetime.date.today()).
        
    Returns:
        dict: {
            "title": str,                  # Cleaned action title (e.g. 'Pay rent')
            "description": str,            # Original or expanded description
            "due_date": Optional[str],     # 'YYYY-MM-DD' formatted string or None
            "recurrence": Optional[str],   # 'monthly', 'on the 1st of every month', etc.
            "priority": str                # 'low', 'medium', or 'high'
        }
        
    Raises:
        ValueError: If input text is empty or non-string.
    """
```

---

## AI Testing & Hardening Critique

In accordance with Step 8, an initial test checklist was generated and then hardened.

### What the Initial AI Checklist Missed:
1. **Impossible Calendar Dates**: The initial checklist checked for string formats (`YYYY-MM-DD`) but missed non-existent calendar dates like `2026-02-30`. Added explicit validation ensuring real date parsing.
2. **Whitespace-Only Inputs**: Strings containing only spaces (`"   "`) previously bypassed empty string checks. Added regex stripping and serializer validation.
3. **Idempotency Key Conflict & Retry Lifecycle**: Missed verifying that the same idempotency key with a *different* body yields `422`, and that a *failed* request (e.g. 400 validation error) must NOT lock the key, allowing the client to fix and retry.
4. **Subtask Nesting Depth**: Missed testing that a subtask cannot itself become a parent (limiting depth to 1 level to avoid circular references and unbounded hierarchy).
5. **Atomic Rollback on Breakdown**: Missed testing that if the second or third subtask dictionary in a breakdown is invalid, the entire operation rolls back and zero subtasks are created.
6. **"Never Trust Parser Output" Guard**: Added mock tests simulating a parser returning an empty title or invalid type to verify `502 Bad Gateway` is raised and no row is committed.

All 23 hardened test cases are automated and pass in [`tasks/tests.py`](file:///D:/projects/airtribe/projects/task_manager/tasks/tests.py).

---

## OpenAPI Specification

A complete OpenAPI 3.0 specification is available at [**`openapi.yaml`**](file:///D:/projects/airtribe/projects/task_manager/openapi.yaml). You can import it into Swagger Editor, Postman, or Echo API to inspect all schemas, endpoints, and error responses.
