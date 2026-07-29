# Admin API — Frontend Handoff

## What shipped

The backend now exposes an administrator-only API for dashboard metrics, user management, workspace review, onboarding-question management, and audit history. All routes are under `/api/v1/admin` and require an active user whose account role is `admin`.

Use the access token returned by `POST /api/v1/auth/admin/login`:

```http
Authorization: Bearer <access_token>
```

Non-admin users receive `403`. Suspended users (`is_active: false`) also receive `403`. Refresh tokens must not be used as bearer tokens; they are rejected by protected endpoints.

## Endpoints

### Dashboard

`GET /api/v1/admin/dashboard`

```json
{
  "total_users": 120,
  "active_users": 118,
  "admin_users": 2,
  "total_workspaces": 245,
  "workspaces_last_7_days": 18,
  "validation_completed": 76,
  "recent_workspaces": [
    {
      "id": 41,
      "user_id": 17,
      "username": "founder@example.com",
      "name": "Market research",
      "description": "Optional context",
      "state": "GATHERING_INFO",
      "created_at": "2026-07-29T08:30:00Z",
      "updated_at": "2026-07-29T09:15:00Z"
    }
  ]
}
```

### Users

`GET /api/v1/admin/users?search=jane&limit=25&offset=0`

The `search` parameter matches email/username. `limit` is 1–100; `offset` is zero-based.

```json
{
  "users": [
    {
      "id": 17,
      "username": "jane@example.com",
      "role": "user",
      "is_active": true,
      "workspace_count": 3
    }
  ],
  "pagination": { "total": 1, "limit": 25, "offset": 0 }
}
```

`GET /api/v1/admin/users/{user_id}` returns one item with the same shape.

`PATCH /api/v1/admin/users/{user_id}` updates a role and/or account status:

```json
{ "role": "admin", "is_active": true }
```

Allowed role values are `user` and `admin`. The API prevents an administrator from suspending or demoting themself and prevents removal of the last active administrator. These changes are audited.

### Workspace review

`GET /api/v1/admin/workspaces?user_id=17&search=market&limit=25&offset=0`

Both filters are optional. The response uses the same `pagination` shape as users and returns a `workspaces` array of workspace summaries.

`GET /api/v1/admin/workspaces/{workspace_id}` returns the summary plus `idea`, `conversation_history`, and `validation_result`. Opening this endpoint creates an audit event, so use it only when the full workspace context is needed.

### Interactive onboarding questions

These are the routes that should replace the frontend mock service.

| Operation | Route |
|---|---|
| List | `GET /api/v1/admin/interactive-questions?limit=100&offset=0` |
| Create | `POST /api/v1/admin/interactive-questions` |
| Update | `PUT /api/v1/admin/interactive-questions/{question_id}` |
| Delete | `DELETE /api/v1/admin/interactive-questions/{question_id}` |

Create/update request:

```json
{
  "question": "What best describes your role?",
  "question_type": "radio",
  "options": ["Founder", "Investor", "Student"],
  "required": true,
  "is_active": true,
  "sort_order": 10
}
```

Supported `question_type` values are:

- `text` — `options` must be empty.
- `radio`, `dropdown`, `multi_select` — must contain at least one non-blank, unique option.

Question response:

```json
{
  "id": 101,
  "questionId": 101,
  "question": "What best describes your role?",
  "question_type": "radio",
  "options": ["Founder", "Investor", "Student"],
  "required": true,
  "is_active": true,
  "sort_order": 10,
  "created_at": "2026-07-29T09:30:00Z",
  "updated_at": "2026-07-29T09:30:00Z"
}
```

The list endpoint returns `{ "questions": [...], "pagination": {...} }`, rather than a bare array. Keep both `id` and `questionId` supported in frontend types; they currently contain the same value for compatibility with the existing UI.

Internally the backend maps existing questionnaire storage types to the frontend contract:

| Frontend | Stored type |
|---|---|
| `text` | `textarea` |
| `radio` | `radiobuttons` |
| `dropdown` | `dropdown` |
| `multi_select` | `checkboxes` |

### Audit history

`GET /api/v1/admin/audit-events?action=user.updated&limit=50&offset=0`

The `action` filter is optional. Current actions include `user.updated`, `workspace.viewed`, `interactive_question.created`, `interactive_question.updated`, and `interactive_question.deleted`.

## Error handling

- `401`: missing, invalid, expired, or refresh-token bearer credential.
- `403`: valid authenticated account without admin permission, or a suspended account.
- `404`: requested user, workspace, or question does not exist.
- `422`: invalid request shape or invalid question options/type combination.
- `429`: endpoint rate limit exceeded.

All timestamps are ISO 8601 UTC timestamps. The backend exposes the complete contract through Swagger in development at `/docs`.
