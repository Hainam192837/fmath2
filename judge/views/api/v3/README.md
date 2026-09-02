# API v3 Frontend

Tài liệu này mô tả các API trong thư mục `judge/views/api/v3`, gồm endpoint, input, kiểu dữ liệu trả về và các biến thể response theo đúng source hiện tại.

## Tổng quan

- Base path: `/api/v3/`
- Renderer: `application/json` qua `ORJSONRenderer`
- Version khai báo: `3.0.0`
- Auth mặc định ở cấp `NinjaAPI`: `Bearer <access_token>`
- Endpoint không yêu cầu access token:
  - `POST /api/v3/auth/login`
  - `POST /api/v3/auth/refresh`

## Quy ước dữ liệu

- Các trường thời gian đều trả về chuỗi ISO-8601, ví dụ: `"2026-04-03T10:15:30+00:00"`
- Các endpoint dạng danh sách chỉ trả về `array`, không có metadata phân trang như `count`, `next`, `previous`
- `page` và `page_size` được xử lý bằng cắt mảng thủ công:
  - `start = max(page - 1, 0) * page_size`
  - nếu vượt quá dữ liệu thì trả về `[]`
- Các trường nullable sẽ trả về `null`
- Các danh sách không có dữ liệu sẽ trả về `[]`

## Quy ước lỗi thường gặp

Các lỗi nghiệp vụ và auth được raise bằng `HttpError`, nên response lỗi thực tế là JSON dạng `{ "detail": "..." }`. Lỗi validation payload/query vẫn theo format chuẩn của Ninja.

Các trường hợp xuất hiện trong source:

- `401 Authentication required`
- `401 Invalid credentials`
- `401 Refresh token is required`
- `401 Invalid or expired refresh token`
- `401 Invalid or expired access token`
- `401 Invalid refresh token`
- `403 Permission denied`
- `404 Problem not found`
- `404 Contest not found`
- `404 User not found`
- `404 Organization not found`
- `404 Submission not found`

Ví dụ:

```json
{
  "detail": "Authentication required"
}
```

## 2. Home

### `GET /api/v3/home`

Trả về dữ liệu trang chủ cho frontend sau khi đăng nhập.

Auth:
- Bắt buộc

Response 200:

```json
{
  "posts": [
    {
      "id": 1,
      "slug": "welcome",
      "title": "Welcome",
      "summary": "Post summary",
      "publish_on": "2026-04-01T00:00:00+00:00",
      "authors": ["alice", "bob"],
      "url": "/blog/1/welcome"
    }
  ],
  "new_problems": [
    {
      "code": "A1",
      "name": "Two Sum",
      "group": "Basic",
      "types": ["Ad Hoc"],
      "points": 10.0,
      "partial": false,
      "is_public": true,
      "is_organization_private": false
    }
  ],
  "recent_comments": [
    {
      "id": 1,
      "author": "alice",
      "page": "problem",
      "page_title": "Two Sum",
      "link": "/problem/A1",
      "time": "2026-04-03T10:15:30+00:00",
      "score": 5
    }
  ],
  "current_contests": [],
  "future_contests": [],
  "stats": {
    "users": 1000,
    "problems": 500,
    "submissions": 90000,
    "judges_online": 4
  },
  "own_open_tickets": [
    {
      "id": 12,
      "title": "Need clarification"
    }
  ]
}
```

Biến thể:

- `posts`, `new_problems`, `recent_comments`, `current_contests`, `future_contests`, `own_open_tickets` có thể rỗng
- `own_open_tickets` chỉ có dữ liệu cho user hiện tại; nếu không có ticket mở thì trả về `[]`

Lỗi:

- `401 Authentication required`

---

## 3. Auth

### `POST /api/v3/auth/login`

Đăng nhập bằng username/password và nhận cặp token.

Auth:
- Không yêu cầu

Request body:

```json
{
  "username": "alice",
  "password": "secret"
}
```

Response 200:

```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "Bearer",
  "access_expires_in": 1800,
  "refresh_expires_in": 604800
}
```

Lỗi:

- `401 Invalid credentials`

### `POST /api/v3/auth/refresh`

Làm mới access token bằng refresh token.

Auth:
- Không yêu cầu

Có 2 cách truyền refresh token:

1. Qua body:

```json
{
  "refresh_token": "..."
}
```

2. Hoặc qua header `Authorization: Bearer <refresh_token>`

Response 200:

```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "Bearer",
  "access_expires_in": 1800,
  "refresh_expires_in": 604800
}
```

Biến thể:

- Nếu body không có `refresh_token`, code sẽ thử lấy token từ header bearer

Lỗi:

- `401 Refresh token is required`
- `401 Invalid or expired refresh token`

### `POST /api/v3/auth/logout`

Thu hồi access token hiện tại và tùy chọn thu hồi thêm refresh token.

Auth:
- Bắt buộc access token hợp lệ

Request body:

```json
{
  "refresh_token": "..."
}
```

`refresh_token` là optional. Có thể gọi với body rỗng hoặc không body.

Response 200:

```json
{
  "detail": "Logged out successfully. Provided tokens have been revoked."
}
```

Biến thể:

- Nếu chỉ gửi access token thì API vẫn logout và blacklist access token hiện tại
- Nếu gửi thêm `refresh_token`, token này phải thuộc cùng user đang đăng nhập

Lỗi:

- `401 Invalid or expired access token`
- `401 Invalid refresh token`

### `GET /api/v3/me`

Lấy thông tin chi tiết của user hiện tại.

Auth:
- Bắt buộc

Response:
- Cùng schema với `GET /api/v3/users/{username}`

Lỗi:

- `401 Authentication required`

---

## 4. Problems

### `GET /api/v3/problems`

Lấy danh sách problem mà user hiện tại được phép nhìn thấy.

Auth:
- Bắt buộc

Query params:

- `search: string | null`
- `partial: bool | null`
- `group: string | null`
- `type: string | null`
- `page: int = 1`
- `page_size: int = 20`

Response 200:

```json
[
  {
    "code": "A1",
    "name": "Two Sum",
    "group": "Basic",
    "types": ["Ad Hoc", "Math"],
    "points": 10.0,
    "partial": false,
    "is_public": true,
    "is_organization_private": false
  }
]
```

Biến thể:

- `group` có thể là `null`
- `types` có thể là `[]`
- nếu không có dữ liệu ở trang hiện tại thì trả về `[]`
- `search` được `strip()`, nếu chỉ chứa khoảng trắng thì coi như không filter

Lỗi:

- `401 Authentication required`

### `GET /api/v3/problems/{problem_code}`

Lấy chi tiết một problem.

Auth:
- Bắt buộc

Response 200:

```json
{
  "code": "A1",
  "name": "Two Sum",
  "group": "Basic",
  "types": ["Ad Hoc"],
  "points": 10.0,
  "partial": false,
  "is_public": true,
  "is_organization_private": false,
  "authors": ["alice"],
  "curators": ["bob"],
  "time_limit": 1.0,
  "memory_limit": 262144,
  "short_circuit": false,
  "allowed_languages": ["CPP20", "PY3"],
  "language_resource_limits": [
    {
      "language": "PY3",
      "time_limit": 2.0,
      "memory_limit": 262144
    }
  ],
  "statement": "<p>Rendered HTML</p>",
  "io_method": {},
  "can_edit": false,
  "can_submit": true,
  "online_judges": [
    {
      "name": "judge-1",
      "ping": 10.5,
      "load": 0.4
    }
  ],
  "latest_submission": {
    "id": 100,
    "status": "D",
    "result": "AC",
    "date": "2026-04-03T10:15:30+00:00"
  }
}
```

Biến thể:

- `group` có thể là `null`
- `language_resource_limits` có thể là `[]`
- `online_judges` có thể là `[]`
- `latest_submission` có thể là `null`
- `latest_submission.result` có thể là `null`
- `statement` là HTML render từ markdown, không phải markdown thô
- `io_method` là `dict[str, Any]`, shape phụ thuộc cấu hình bài

Lỗi:

- `401 Authentication required`
- `404 Problem not found`

---

## 5. Contests

### `GET /api/v3/contests`

Lấy danh sách contest mà user hiện tại được phép nhìn thấy.

Auth:
- Bắt buộc

Query params:

- `tag: string | null`
- `page: int = 1`
- `page_size: int = 20`

Response 200:

```json
[
  {
    "key": "spring-2026",
    "name": "Spring Contest",
    "start_time": "2026-04-01T08:00:00+00:00",
    "end_time": "2026-04-01T11:00:00+00:00",
    "time_limit": 10800.0,
    "is_rated": true,
    "is_private": false,
    "is_organization_private": false,
    "tags": ["dp", "school"],
    "can_join": true,
    "can_view_tasks": false,
    "is_in_contest": false
  }
]
```

Biến thể:

- `time_limit` có thể là `null`
- `tags` có thể là `[]`
- nếu trang không có dữ liệu thì trả về `[]`

Lỗi:

- `401 Authentication required`

### `GET /api/v3/contests/{contest_key}`

Lấy chi tiết contest.

Auth:
- Bắt buộc

Response 200:

```json
{
  "key": "spring-2026",
  "name": "Spring Contest",
  "start_time": "2026-04-01T08:00:00+00:00",
  "end_time": "2026-04-01T11:00:00+00:00",
  "time_limit": 10800.0,
  "is_rated": true,
  "is_private": false,
  "is_organization_private": false,
  "tags": ["dp"],
  "can_join": true,
  "can_view_tasks": false,
  "is_in_contest": false,
  "description": "<p>Contest description</p>",
  "scoreboard_visibility": "P",
  "hidden_scoreboard": false,
  "organizations": [1, 2],
  "authors": ["alice"],
  "current_user_in_contest": false,
  "can_see_rankings": true,
  "can_see_problems": true,
  "problems": [
    {
      "label": "A",
      "code": "A1",
      "name": "Two Sum",
      "order": 1,
      "points": 100,
      "partial": false,
      "max_submissions": null
    }
  ]
}
```

Biến thể:

- `time_limit` có thể là `null`
- `tags`, `organizations`, `authors`, `problems` có thể là `[]`
- `can_see_problems = false` thì `problems` luôn là `[]`
- `hidden_scoreboard` được tính từ `scoreboard_visibility`
- `description` là HTML render từ markdown
- `label` có thể là `null`
- `max_submissions` có thể là `null`

Lỗi:

- `401 Authentication required`
- `404 Contest not found`

---

## 6. Users

### `GET /api/v3/users`

Lấy danh sách user public.

Auth:
- Bắt buộc

Query params:

- `organization: int | null`
- `page: int = 1`
- `page_size: int = 20`

Response 200:

```json
[
  {
    "id": 1,
    "username": "alice",
    "display_name": "Alice",
    "rank": "candidate master",
    "points": 123.5,
    "performance_points": 456.7,
    "problem_count": 100,
    "rating": 1800,
    "organization": {
      "id": 2,
      "name": "Org name",
      "short_name": "ORG"
    },
    "current_contest_key": "spring-2026",
    "is_staff": false,
    "is_superuser": false
  }
]
```

Biến thể:

- `rating` có thể là `null`
- `organization` có thể là `null`
- `current_contest_key` có thể là `null`
- nếu trang không có dữ liệu thì trả về `[]`

Lỗi:

- `401 Authentication required`

### `GET /api/v3/users/{username}`

Lấy chi tiết một user.

Auth:
- Bắt buộc

Response 200:

```json
{
  "id": 1,
  "username": "alice",
  "display_name": "Alice",
  "rank": "candidate master",
  "points": 123.5,
  "performance_points": 456.7,
  "problem_count": 100,
  "rating": 1800,
  "organization": {
    "id": 2,
    "name": "Org name",
    "short_name": "ORG"
  },
  "current_contest_key": "spring-2026",
  "is_staff": false,
  "is_superuser": false,
  "about": "About user",
  "timezone": "UTC",
  "language": "PY3",
  "organizations": [
    {
      "id": 2,
      "name": "Org name",
      "short_name": "ORG"
    }
  ],
  "authored_problems": [
    {
      "code": "A1",
      "name": "Two Sum"
    }
  ],
  "solved_problems": ["A1", "B1"],
  "contest_history": [
    {
      "key": "spring-2026",
      "name": "Spring Contest",
      "rating": 1800,
      "rank": 1,
      "end_time": "2026-04-01T11:00:00+00:00"
    }
  ],
  "volatility": 120.5,
  "editable_by_current_user": false
}
```

Biến thể:

- `rating` có thể là `null`
- `organization` có thể là `null`
- `current_contest_key` có thể là `null`
- `language` có thể là `null`
- `volatility` có thể là `null`
- `about` luôn là string, nếu trống sẽ trả về `""`
- `organizations`, `authored_problems`, `solved_problems`, `contest_history` có thể là `[]`
- `editable_by_current_user = true` chỉ khi viewer chính là user đó

Lỗi:

- `401 Authentication required`
- `404 User not found`

---

## 7. Organizations

### `GET /api/v3/organizations`

Lấy danh sách organization.

Auth:
- Bắt buộc

Query params:

- `is_open: bool | null`
- `page: int = 1`
- `page_size: int = 20`

Response 200:

```json
[
  {
    "id": 1,
    "slug": "abc-school",
    "name": "ABC School",
    "short_name": "ABC",
    "is_open": true,
    "is_hidden": false,
    "logo_override_image": "/media/org.png",
    "member_count": 120
  }
]
```

Biến thể:

- `member_count` có thể là `null` ở schema, dù list API hiện đang annotate giá trị này
- với user không phải superuser, organization `is_hidden=true` bị ẩn khỏi danh sách
- nếu trang không có dữ liệu thì trả về `[]`

Lỗi:

- `401 Authentication required`

### `GET /api/v3/organizations/{organization_id}`

Lấy chi tiết organization.

Auth:
- Bắt buộc

Response 200:

```json
{
  "id": 1,
  "slug": "abc-school",
  "name": "ABC School",
  "short_name": "ABC",
  "is_open": true,
  "is_hidden": false,
  "logo_override_image": "/media/org.png",
  "member_count": null,
  "about": "Organization intro",
  "creation_date": "2020-01-01",
  "admins": ["alice", "bob"],
  "members_preview": [
    {
      "id": 1,
      "username": "alice",
      "display_name": "Alice",
      "rank": "master",
      "points": 100.0,
      "performance_points": 200.0,
      "problem_count": 50,
      "rating": 1800,
      "organization": {
        "id": 1,
        "name": "ABC School",
        "short_name": "ABC"
      },
      "current_contest_key": null,
      "is_staff": false,
      "is_superuser": false
    }
  ]
}
```

Biến thể:

- `member_count` ở detail hiện không được annotate, nên thường là `null`
- `admins` có thể là `[]`
- `members_preview` có thể là `[]`
- `members_preview` chỉ lấy tối đa 20 thành viên public, sort theo `-performance_points`, `-problem_count`

Lỗi:

- `401 Authentication required`
- `404 Organization not found`

---

## 8. Submissions

### `GET /api/v3/submissions`

Lấy danh sách submission trên các problem mà user hiện tại nhìn thấy được.

Auth:
- Bắt buộc

Query params:

- `user: string | null`
- `problem: string | null`
- `result: string | null`
- `page: int = 1`
- `page_size: int = 20`

Response 200:

```json
[
  {
    "id": 100,
    "problem": "A1",
    "user": "alice",
    "date": "2026-04-03T10:15:30+00:00",
    "language": "PY3",
    "time": 0.123,
    "memory": 16384.0,
    "points": 100.0,
    "result": "AC",
    "status": "D"
  }
]
```

Biến thể:

- `language` có thể là `null`
- `time`, `memory`, `points`, `result` có thể là `null`
- nếu trang không có dữ liệu thì trả về `[]`

Lỗi:

- `401 Authentication required`

### `GET /api/v3/submissions/{submission_id}`

Lấy chi tiết submission và test case tree.

Auth:
- Bắt buộc

Response 200:

```json
{
  "id": 100,
  "problem": "A1",
  "user": "alice",
  "date": "2026-04-03T10:15:30+00:00",
  "language": "PY3",
  "time": 0.123,
  "memory": 16384.0,
  "points": 100.0,
  "result": "AC",
  "status": "D",
  "case_points": 100.0,
  "case_total": 100.0,
  "cases": [
    {
      "case_id": 1,
      "batch_id": null,
      "status": "AC",
      "time": 0.01,
      "memory": 1024.0,
      "points": 10.0,
      "total": 10.0,
      "cases": null
    },
    {
      "case_id": null,
      "batch_id": 2,
      "status": null,
      "time": null,
      "memory": null,
      "points": 20.0,
      "total": 20.0,
      "cases": [
        {
          "case_id": 2,
          "batch_id": null,
          "status": "AC",
          "time": 0.02,
          "memory": 2048.0,
          "points": 10.0,
          "total": 10.0,
          "cases": null
        }
      ]
    }
  ]
}
```

Biến thể:

- `cases` là mảng hỗn hợp gồm:
  - case đơn lẻ
  - batch có `batch_id` và mảng con `cases`
- Với case đơn lẻ:
  - `case_id` có giá trị
  - `batch_id = null`
  - `cases = null`
- Với batch:
  - `batch_id` có giá trị
  - `case_id = null`
  - `status`, `time`, `memory` thường là `null`
  - `cases` là danh sách case con
- `language`, `time`, `memory`, `points`, `result` vẫn có thể là `null`
- `cases` có thể là `[]`

Lỗi:

- `401 Authentication required`
- `403 Permission denied`
- `404 Submission not found`

---

## 9. Tóm tắt schema chính

### `TokenPairSchema`

```ts
type TokenPairSchema = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  access_expires_in: number;
  refresh_expires_in: number;
};
```

### `MessageSchema`

```ts
type MessageSchema = {
  detail: string;
};
```

### `ProblemListItemSchema`

```ts
type ProblemListItemSchema = {
  code: string;
  name: string;
  group: string | null;
  types: string[];
  points: number;
  partial: boolean;
  is_public: boolean;
  is_organization_private: boolean;
};
```

### `ProblemDetailSchema`

```ts
type ProblemDetailSchema = ProblemListItemSchema & {
  authors: string[];
  curators: string[];
  time_limit: number;
  memory_limit: number;
  short_circuit: boolean;
  allowed_languages: string[];
  language_resource_limits: {
    language: string;
    time_limit: number | null;
    memory_limit: number | null;
  }[];
  statement: string;
  io_method: Record<string, unknown>;
  can_edit: boolean;
  can_submit: boolean;
  online_judges: {
    name: string;
    ping: number | null;
    load: number | null;
  }[];
  latest_submission: {
    id: number;
    status: string;
    result: string | null;
    date: string;
  } | null;
};
```

### `ContestListItemSchema`

```ts
type ContestListItemSchema = {
  key: string;
  name: string;
  start_time: string;
  end_time: string;
  time_limit: number | null;
  is_rated: boolean;
  is_private: boolean;
  is_organization_private: boolean;
  tags: string[];
  can_join: boolean;
  can_view_tasks: boolean;
  is_in_contest: boolean;
};
```

### `ContestDetailSchema`

```ts
type ContestDetailSchema = ContestListItemSchema & {
  description: string;
  scoreboard_visibility: string;
  hidden_scoreboard: boolean;
  organizations: number[];
  authors: string[];
  current_user_in_contest: boolean;
  can_see_rankings: boolean;
  can_see_problems: boolean;
  problems: {
    label: string | null;
    code: string;
    name: string;
    order: number;
    points: number;
    partial: boolean;
    max_submissions: number | null;
  }[];
};
```

### `UserSummarySchema`

```ts
type UserSummarySchema = {
  id: number;
  username: string;
  display_name: string;
  rank: string;
  points: number;
  performance_points: number;
  problem_count: number;
  rating: number | null;
  organization: {
    id: number;
    name: string;
    short_name: string;
  } | null;
  current_contest_key: string | null;
  is_staff: boolean;
  is_superuser: boolean;
};
```

### `UserDetailSchema`

```ts
type UserDetailSchema = UserSummarySchema & {
  about: string;
  timezone: string;
  language: string | null;
  organizations: {
    id: number;
    name: string;
    short_name: string;
  }[];
  authored_problems: {
    code: string;
    name: string;
  }[];
  solved_problems: string[];
  contest_history: {
    key: string;
    name: string;
    rating: number;
    rank: number;
    end_time: string;
  }[];
  volatility: number | null;
  editable_by_current_user: boolean;
};
```

### `OrganizationListItemSchema`

```ts
type OrganizationListItemSchema = {
  id: number;
  slug: string;
  name: string;
  short_name: string;
  is_open: boolean;
  is_hidden: boolean;
  logo_override_image: string;
  member_count: number | null;
};
```

### `OrganizationDetailSchema`

```ts
type OrganizationDetailSchema = OrganizationListItemSchema & {
  about: string;
  creation_date: string;
  admins: string[];
  members_preview: UserSummarySchema[];
};
```

### `SubmissionListItemSchema`

```ts
type SubmissionListItemSchema = {
  id: number;
  problem: string;
  user: string;
  date: string;
  language: string | null;
  time: number | null;
  memory: number | null;
  points: number | null;
  result: string | null;
  status: string;
};
```

### `SubmissionDetailSchema`

```ts
type SubmissionCaseSchema = {
  case_id: number | null;
  batch_id: number | null;
  status: string | null;
  time: number | null;
  memory: number | null;
  points: number | null;
  total: number | null;
  cases: SubmissionCaseSchema[] | null;
};

type SubmissionDetailSchema = SubmissionListItemSchema & {
  case_points: number;
  case_total: number;
  cases: SubmissionCaseSchema[];
};
```

### `BootstrapSchema`

```ts
type BootstrapSchema = {
  site: {
    name: string;
    long_name: string;
    admin_email: string;
    domain: string;
    language: string;
    login_return_path: string;
    meta_keywords: string;
    meta_description: string;
    has_webauthn: boolean;
    now: string;
  };
  nav_tabs: {
    key: string;
    href: string;
    label: string;
  }[];
  nav_tree: {
    key: string;
    label: string;
    path: string;
    is_admin: boolean;
    children: unknown[];
  }[];
  user: UserSummarySchema | null;
};
```

### `HomeSchema`

```ts
type HomeSchema = {
  posts: {
    id: number;
    slug: string;
    title: string;
    summary: string;
    publish_on: string;
    authors: string[];
    url: string;
  }[];
  new_problems: ProblemListItemSchema[];
  recent_comments: {
    id: number;
    author: string;
    page: string;
    page_title: string;
    link: string;
    time: string;
    score: number;
  }[];
  current_contests: ContestListItemSchema[];
  future_contests: ContestListItemSchema[];
  stats: {
    users: number;
    problems: number;
    submissions: number;
    judges_online: number;
  };
  own_open_tickets: {
    id: number;
    title: string;
  }[];
};
```
