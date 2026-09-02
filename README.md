# TMath Coding Platform

Đây là codebase của nền tảng `TMath`, một hệ thống luyện tập lập trình và tổ chức kỳ thi trực tuyến xây trên Django.

Repo này xuất phát từ nhánh DMOJ trước đây nhưng hiện đã được chỉnh sửa theo nhu cầu vận hành riêng của TMath: branding mới, cấu hình mới, giao diện quản trị riêng, API riêng, websocket realtime, import/export dữ liệu và nhiều luồng quản trị nội bộ. README này mô tả trạng thái hiện tại của dự án, không còn xem đây là repo DMOJ upstream.

## Tính năng chính

- Quản lý bài tập lập trình, test data, editorial và lời giải công khai.
- Tổ chức contest với nhiều format, bảng xếp hạng, virtual participation, MOSS và export Excel.
- Chấm bài qua bridge kết nối tới judge server bên ngoài.
- Theo dõi submission realtime qua Django Channels + Redis.
- Quản lý người dùng, tổ chức, ticket hỗ trợ, blog và navigation động.
- Hỗ trợ 2FA với TOTP và WebAuthn.
- Có API đọc dữ liệu contest, problem, submission, organization và user.
- Có các luồng tạo hàng loạt tài khoản từ form hoặc CSV.
- Có các model phục vụ curriculum/course và các extension nội bộ khác của TMath.

## Stack hiện tại

- Backend: Django 4.x
- Async/realtime: Django Channels, channels-redis
- Queue/background jobs: Celery
- Database: MariaDB/MySQL
- Cache/broker/channel layer: Redis
- Frontend assets: Tailwind CSS 4
- Markdown editor: Martor
- Admin: Django admin + Grappelli

## Cấu trúc thư mục

- `tmath/`: cấu hình Django, ASGI/WSGI, Celery, URL routing.
- `judge/`: app chính chứa models, views, bridge, API, tasks, admin.
- `templates/`: giao diện người dùng và admin.
- `resources/`: CSS, JS, assets tĩnh, submodule frontend.
- `tempdata/`: static/media/cache/problem data khi chạy local.
- `.devcontainer/`: môi trường dev bằng container.

## Dịch vụ phụ thuộc

Để chạy đầy đủ hệ thống, cần ít nhất:

- MariaDB hoặc MySQL
- Redis
- Python 3.12
- Node.js 22 và npm/pnpm
- Một judge server tương thích để nhận job chấm qua bridge


## Thiết lập môi trường local

### 1. Cài dependency hệ điều hành

Ví dụ trên Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y \
  git curl ca-certificates gnupg \
  gcc g++ make pkg-config gettext \
  python3 python3-dev python3-venv \
  default-libmysqlclient-dev \
  libxml2-dev libxslt1-dev zlib1g-dev \
  mariadb-server redis-server
```

Cài Node.js 22 hoặc phiên bản tương thích với repo.

### 2. Clone repo và submodule

```bash
git clone <repo-url> tmath
cd tmath
git submodule update --init --recursive
```

### 3. Tạo virtualenv và cài Python packages

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install mysqlclient
pip install -r requirements.txt
```

### 4. Cài package frontend

```bash
npm install
```

### 5. Chuẩn bị database và Redis

Tạo database ví dụ:

```sql
CREATE DATABASE dmoj DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_general_ci;
```

Sau đó chỉnh `tmath/local_settings.py` cho đúng:

- `DATABASES`
- `CACHES`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `CHANNEL_LAYERS`
- `SITE_FULL_URL`, `ALLOWED_HOSTS`, email, SSL và các đường dẫn cache/media

### 6. Build static assets

Repo đang dùng file nguồn `resources/main.css` để sinh ra `resources/full_style.css`:

```bash
npx @tailwindcss/cli -i resources/main.css -o resources/full_style.css
python manage.py collectstatic --noinput
python manage.py compilemessages
python manage.py compilejsi18n
```

### 7. Migrate database

```bash
python manage.py migrate
```

### 8. Tạo tài khoản quản trị

```bash
python manage.py createsuperuser
```

## Chạy local

### Web app

```bash
python manage.py runserver
```

### Celery worker

```bash
celery -A tmath worker -l info
```

### Bridge nhận kết quả từ judge

```bash
python manage.py runbridged
```

Nếu dùng websocket/realtime đầy đủ trong môi trường riêng, cần chạy ASGI server phù hợp, ví dụ Daphne/Uvicorn cho `tmath.asgi:application`.


## API và realtime

- API v1/v2 nằm trong `judge/views/api/`.
- ASGI entrypoint: `tmath/asgi.py`
- Celery app: `tmath/celery.py`
- Judge bridge: `judge/bridge/`
- Websocket consumers: `judge/consumers/`

## Gợi ý vận hành production

- Tách `local_settings.py` thành template không chứa secret.
- Đưa secret sang biến môi trường hoặc secret manager.
- Chạy web bằng Gunicorn/Uvicorn/Daphne sau reverse proxy Nginx.
- Chạy riêng các process: web, celery worker, bridge, websocket server.
- Cấu hình lại Redis/MySQL theo hạ tầng thật, không dùng `host.docker.internal`.
- Kiểm tra lại static/media path trong `tempdata/` trước khi triển khai lâu dài.

## Dev Container

Repo có sẵn `.devcontainer/` để dựng môi trường phát triển với Python 3.12 và Node.js 22. Container này chỉ chuẩn bị toolchain; database, Redis và judge server vẫn cần được cung cấp riêng.

## Ghi chú

- Nhiều comment, tên biến và một số setting vẫn còn dấu vết lịch sử từ DMOJ. Điều đó phản ánh nguồn gốc codebase, không phải định danh sản phẩm hiện tại.
- Nếu muốn biến repo này thành một bản phân phối sạch cho production hoặc public open source, nên ưu tiên dọn secret, tách cấu hình mẫu và cập nhật thêm tài liệu deploy.
# fmath
