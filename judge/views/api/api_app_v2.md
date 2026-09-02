# API App V2

Tài liệu này mô tả các endpoint trong `judge/views/api/api_app_v2.py`.

Base path:

```text
/app/v2/
```

Content-Type:

```text
application/json
```

## Cơ chế xác thực

`api_app_v2` dùng JWT tách riêng 2 loại token:

- `access_token`: dùng để gọi các API được bảo vệ
- `refresh_token`: chỉ dùng để làm mới token

Header cho các API yêu cầu đăng nhập:

```http
Authorization: Bearer <access_token>
```

Lưu ý:

- `refresh_token` không dùng để gọi API nghiệp vụ
- `logout` sẽ blacklist `access_token` hiện tại
- muốn blacklist luôn `refresh_token`, client phải gửi thêm `refresh_token` trong body

## Quy ước lỗi

Các API có thể trả lỗi theo dạng:

```json
{
  "detail": "Error message"
}
```

Một số mã lỗi thường gặp:

- `401`: token không hợp lệ, hết hạn, sai loại token, sai thông tin đăng nhập
- `403`: không có quyền truy cập contest/problem hoặc không ở trong contest
- `404`: contest/problem/submission không tồn tại
- `429`: quá nhiều submission đang chờ chấm

---

## 1. Authentication

### POST `/auth/login/`

Chức năng:

- Đăng nhập bằng `username` và `password`
- Trả về cả `access_token` và `refresh_token`

Auth:

- Không yêu cầu

Request body:

```json
{
  "username": "alice",
  "password": "secret"
}
```

Response:

```json
{
  "access_token": "<jwt_access_token>",
  "refresh_token": "<jwt_refresh_token>",
  "token_type": "Bearer",
  "access_expires_in": 1800,
  "refresh_expires_in": 604800
}
```

Các trường:

- `access_token`: JWT dùng cho API nghiệp vụ
- `refresh_token`: JWT dùng để gọi `/auth/refresh/`
- `token_type`: luôn là `Bearer`
- `access_expires_in`: thời gian sống của access token, đơn vị giây
- `refresh_expires_in`: thời gian sống của refresh token, đơn vị giây

### POST `/auth/refresh/`

Chức năng:

- Làm mới cặp token bằng `refresh_token`

Auth:

- Không yêu cầu access token

Request body:

```json
{
  "refresh_token": "<jwt_refresh_token>"
}
```

Hoặc có thể truyền qua header:

```http
Authorization: Bearer <jwt_refresh_token>
```

Response:

```json
{
  "access_token": "<jwt_access_token>",
  "refresh_token": "<jwt_refresh_token>",
  "token_type": "Bearer",
  "access_expires_in": 1800,
  "refresh_expires_in": 604800
}
```

### POST `/auth/logout/`

Chức năng:

- Logout và blacklist `access_token` hiện tại
- Nếu có `refresh_token` trong body, blacklist luôn refresh token đó

Auth:

- Yêu cầu `access_token`

Request body:

```json
{
  "refresh_token": "<jwt_refresh_token>"
}
```

`refresh_token` là tùy chọn, nhưng nên gửi để revoke đầy đủ.

Response:

```json
{
  "detail": "Logged out successfully. Provided tokens have been revoked."
}
```

### GET `/auth/me/`

Chức năng:

- Lấy thông tin user hiện tại

Auth:

- Yêu cầu `access_token`

Response:

```json
{
  "id": 10,
  "username": "alice",
  "email": "alice@example.com",
  "display_name": "Alice",
  "rank": "user",
  "points": 120.5,
  "performance_points": 98.25,
  "problem_count": 42,
  "current_contest_key": "exam-math-01",
  "is_staff": false,
  "is_superuser": false
}
```

Các trường:

- `current_contest_key`: `null` nếu user chưa ở contest nào

---

## 2. Contest APIs

### GET `/contests/`

Chức năng:

- Lấy danh sách contest exam mà user nhìn thấy
- Bỏ qua contest đã kết thúc

Auth:

- Yêu cầu `access_token`

Response:

```json
[
  {
    "pk": 1,
    "key": "exam-math-01",
    "name": "Exam Math 01",
    "topic": "Algebra",
    "description": "Contest description",
    "start_time": "2026-04-01T08:00:00+00:00",
    "end_time": "2026-04-01T10:00:00+00:00",
    "is_joinable": true,
    "is_in_contest": false,
    "is_accessible": true,
    "user_count": 120,
    "version_update": 3
  }
]
```

### GET `/contest/{contest_key}/`

Chức năng:

- Lấy chi tiết contest
- Có thể kèm danh sách problem nếu user được xem problem

Auth:

- Yêu cầu `access_token`

Response:

```json
{
  "pk": 1,
  "key": "exam-math-01",
  "name": "Exam Math 01",
  "topic": "Algebra",
  "description": "Contest description",
  "start_time": "2026-04-01T08:00:00+00:00",
  "end_time": "2026-04-01T10:00:00+00:00",
  "is_joinable": true,
  "is_in_contest": true,
  "is_accessible": true,
  "user_count": 120,
  "version_update": 3,
  "hidden_scoreboard": false,
  "scoreboard_visibility": "V",
  "can_see_problems": true,
  "can_see_rankings": true,
  "current_user_in_contest": true,
  "problems": [
    {
      "code": "SUMA",
      "title": "A + B",
      "order": 1,
      "points": 100,
      "partial": false,
      "time_limit": 1.0,
      "memory_limit": 262144,
      "max_submissions": null,
      "label": "A"
    }
  ]
}
```

Giải thích:

- `hidden_scoreboard`: scoreboard có đang bị ẩn theo cấu hình contest hay không
- `scoreboard_visibility`: giá trị raw từ model contest
- `can_see_problems`: user có được xem danh sách problem hay không
- `can_see_rankings`: user có được xem bảng xếp hạng đầy đủ hay không
- `current_user_in_contest`: user hiện tại có đang ở contest này không

### POST `/contest/{contest_key}/join/`

Chức năng:

- Tham gia contest
- Hỗ trợ `access_code` nếu contest yêu cầu

Auth:

- Yêu cầu `access_token`

Request body:

```json
{
  "access_code": "123456"
}
```

`access_code` là tùy chọn.

Response:

```json
{
  "detail": "Successfully joined the contest"
}
```

### POST `/contest/{contest_key}/leave/`

Chức năng:

- Rời contest hiện tại

Auth:

- Yêu cầu `access_token`

Response:

```json
{
  "detail": "Successfully left the contest"
}
```

### GET `/contest/{contest_key}/problems/`

Chức năng:

- Lấy danh sách problem trong contest

Auth:

- Yêu cầu `access_token`

Response:

```json
[
  {
    "code": "SUMA",
    "title": "A + B",
    "order": 1,
    "points": 100,
    "partial": false,
    "time_limit": 1.0,
    "memory_limit": 262144,
    "max_submissions": null,
    "label": "A"
  }
]
```

### GET `/contest/{contest_key}/leaderboard/`

Chức năng:

- Lấy bảng xếp hạng contest

Auth:

- Yêu cầu `access_token`

Response:

```json
[
  {
    "rank": "1",
    "user_id": 10,
    "username": "alice",
    "points": 300.0,
    "cumulative_time": 5400.0,
    "tiebreaker": 0.0,
    "is_disqualified": false,
    "participation_type": 0,
    "participation_rating": 1520,
    "organization": "School A",
    "problem_cells": [
      {
        "has_data": true,
        "points": 100.0,
        "time": 600.0,
        "status": "AC",
        "is_pretested": false
      },
      {
        "has_data": false,
        "points": null,
        "time": null,
        "status": null,
        "is_pretested": null
      }
    ]
  }
]
```

Giải thích:

- `rank`: hạng, đang được trả về dạng chuỗi
- `participation_type`:
  - `0`: live participation
  - `> 0`: virtual participation
  - giá trị cụ thể phụ thuộc model `ContestParticipation`
- `problem_cells`: trạng thái từng bài trong scoreboard

---

## 3. Problem APIs

### GET `/contest/{contest_key}/problems/{problem_code}/`

Chức năng:

- Lấy chi tiết problem trong contest
- Trả về statement đã render HTML
- Trả về thông tin submission hiện tại của user với bài này nếu có

Auth:

- Yêu cầu `access_token`

Response:

```json
{
  "code": "SUMA",
  "title": "A + B",
  "order": 1,
  "points": 100,
  "partial": false,
  "time_limit": 1.0,
  "memory_limit": 262144,
  "max_submissions": null,
  "label": "A",
  "statement": "<p>Problem statement</p>",
  "allowed_languages": ["cpp17", "py3"],
  "io_method": {
    "type": "stdio"
  },
  "version_update": 5,
  "has_submission": true,
  "latest_submission_id": 345,
  "latest_submission_version": 4
}
```

Giải thích:

- `statement`: HTML đã render từ markdown
- `allowed_languages`: danh sách `language.key`
- `latest_submission_id`: id của `Submission`, không phải `ContestSubmission`

### GET `/contest/{contest_key}/problems/{problem_code}/submission/{submission_id}/`

Chức năng:

- Lấy source code hiện tại của một `ContestSubmission`
- `submission_id` trên URL là `ContestSubmission.id`

Auth:

- Yêu cầu `access_token`

Ràng buộc:

- Submission phải thuộc đúng contest hiện tại
- Submission phải thuộc đúng problem
- Submission phải thuộc participation hiện tại của user

Response:

```json
{
  "contest_submission_id": 12,
  "submission_id": 345,
  "language_key": "py3",
  "source": "print('hello')",
  "version_update": 4,
  "submitted_at": "2026-04-01T08:30:00+00:00"
}
```

Giải thích:

- `contest_submission_id`: id của `ContestSubmission`
- `submission_id`: id của `Submission`
- `source`: source code hiện tại đang lưu

### POST `/contest/{contest_key}/problems/{problem_code}/submit/`

Chức năng:

- Submit mới hoặc cập nhật submission hiện tại của user cho bài đó trong contest
- Nếu đã có `ContestSubmission`, API sẽ cập nhật source hiện tại thay vì tạo thêm một `ContestSubmission` mới

Auth:

- Yêu cầu `access_token`

Request body:

```json
{
  "language_key": "py3",
  "source": "print('hello')"
}
```

Response:

```json
{
  "detail": "Submitted successfully",
  "submission_id": 345,
  "replaced_existing": true
}
```

Giải thích:

- `submission_id`: id của `Submission`
- `replaced_existing`:
  - `true`: đã có submission cũ và API cập nhật lại submission đó
  - `false`: API tạo submission mới

### GET `/contest/{contest_key}/problems/{problem_code}/submissions/`

Chức năng:

- Lấy danh sách submission của user hiện tại cho một problem trong contest

Auth:

- Yêu cầu `access_token`

Response:

```json
[
  {
    "submission_id": 345,
    "language_key": "py3",
    "source": "print('hello')",
    "status": "AC",
    "result": "AC",
    "status_display": "Accepted",
    "points": 100.0,
    "case_points": 100.0,
    "case_total": 100.0,
    "time": 0.012,
    "memory": 2048.0,
    "is_graded": true,
    "is_pretested": false,
    "version_update": 4,
    "submitted_at": "2026-04-01T08:30:00+00:00"
  }
]
```

Giải thích:

- `status`: trạng thái ngắn, lấy từ `submission.short_status`
- `result`: kết quả chấm, có thể `null` nếu chưa chấm xong
- `status_display`: chuỗi hiển thị đầy đủ
- `source`: source code hiện tại
- `is_graded`: đã chấm xong hay chưa

---

## 4. Ghi chú triển khai hiện tại

- `login` và `refresh` đều trả về cặp token mới
- `logout` blacklist token bằng cache
- blacklist có TTL bằng thời gian sống còn lại của token
- `refresh_token` chỉ bị blacklist nếu client gửi nó vào `/auth/logout/`
- Các API contest/problem hiện đang bám theo participation hiện tại của user

## 5. Mapping nhanh schema

### `MessageSchema`

```json
{
  "detail": "string"
}
```

### `TokenPairSchema`

```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "Bearer",
  "access_expires_in": 1800,
  "refresh_expires_in": 604800
}
```

### `UserProfileSchema`

```json
{
  "id": 0,
  "username": "string",
  "email": "string",
  "display_name": "string",
  "rank": "string",
  "points": 0.0,
  "performance_points": 0.0,
  "problem_count": 0,
  "current_contest_key": "string or null",
  "is_staff": false,
  "is_superuser": false
}
```

### `ContestProblemItemSchema`

```json
{
  "code": "string",
  "title": "string",
  "order": 1,
  "points": 100,
  "partial": false,
  "time_limit": 1.0,
  "memory_limit": 262144,
  "max_submissions": null,
  "label": "A"
}
```

### `SubmissionItemSchema`

```json
{
  "submission_id": 345,
  "language_key": "py3",
  "source": "string or null",
  "status": "AC",
  "result": "AC",
  "status_display": "Accepted",
  "points": 100.0,
  "case_points": 100.0,
  "case_total": 100.0,
  "time": 0.01,
  "memory": 2048.0,
  "is_graded": true,
  "is_pretested": false,
  "version_update": 4,
  "submitted_at": "2026-04-01T08:30:00+00:00"
}
```
