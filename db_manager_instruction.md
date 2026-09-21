# Hướng Dẫn Triển Khai & Bảo Mật NocoDB Bằng Session Django Admin (FMath/DMOJ)

Tài liệu này hướng dẫn cách cấu hình NocoDB chạy trên subdomain riêng (`db.yourdomain.com`), được bảo vệ vòng ngoài bằng **Nginx `auth_request`** thông qua session của Django Admin (`yourdomain.com`), đồng thời tự động bypass màn hình đăng nhập thứ hai của NocoDB.

> **Lưu ý về Source Code:** Hàm `verify_admin` và route `/api/verify-admin/` đã có sẵn trong source code dự án trên GitHub. Khi triển khai trên VPS mới hoặc cập nhật máy chủ, chỉ cần `git pull` và thiết lập các biến môi trường/cấu hình cục bộ.

---

## 1. Kiến Trúc Hoạt Động

1. **Người dùng truy cập `https://db.yourdomain.com`**:
   * Nginx chặn request và gửi subrequest nội bộ (`/internal_check_admin`) sang endpoint Django (`/api/verify-admin/`).
   * Django đọc Cookie `sessionid` dùng chung toàn domain (`.yourdomain.com`).
   * Nếu đã đăng nhập và là `is_staff` hoặc `is_superuser` $\rightarrow$ Trả về `HTTP 200`.
   * Nếu chưa đăng nhập hoặc không có quyền admin $\rightarrow$ Trả về `HTTP 403`.

2. **Xử lý phản hồi từ Nginx**:
   * Nếu nhận `401`/`403`/`502`: Nginx chuyển hướng về trang login chính `https://yourdomain.com/accounts/login/?next=https://db.yourdomain.com/`.
   * Nếu nhận `200`: Nginx chuyển tiếp request vào container NocoDB (cổng 8080 nội bộ), tự động đính kèm Cookie `refresh_token` để đăng nhập sẵn tài khoản quản trị NocoDB.

---

## 2. Cập Nhật Source Code & Cấu Hình Django

### 2.1. Cập nhật mã nguồn từ GitHub
Kéo code mới nhất đã chứa endpoint `verify_admin` về VPS:

```bash
cd /home/ubuntu/tmath
git pull origin main  # hoặc nhánh tương ứng của bạn
```

*(Kiểm tra nhanh: Route `/api/verify-admin/` đã có sẵn trong `tmath/urls.py`)*.

### 2.2. Cấu hình Cookie và SSL Header trong `local_settings.py`

Mở file cấu hình cục bộ:
```bash
nano /home/ubuntu/tmath/tmath/local_settings.py
```

Bổ sung/kiểm tra các thiết lập sau:

```python
# Cho phép chia sẻ session qua tất cả subdomain
SESSION_COOKIE_DOMAIN = '.yourdomain.com'
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = 'Lax'

# Báo cho Django biết ứng dụng chạy sau Nginx reverse proxy HTTPS
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Danh sách nguồn tin cậy CSRF
CSRF_TRUSTED_ORIGINS = [
    'https://yourdomain.com',
    'https://*.yourdomain.com',
]
```

> **Lưu ý:** Tuyệt đối không bật `CSRF_COOKIE_DOMAIN = '.yourdomain.com'` để tránh lỗi `403 CSRF verification failed`.

### 2.3. Kiểm tra cú pháp và khởi động lại Backend
```bash
python3 manage.py check
sudo supervisorctl restart all
```

---

## 3. Khởi Chạy NocoDB (Docker)

Chạy NocoDB lắng nghe riêng trên cổng nội bộ `127.0.0.1:8080`, cho phép kết nối đến cơ sở dữ liệu trên máy chủ:

```bash
sudo docker rm -f nocodb 2>/dev/null
sudo docker run -d --name nocodb \
  --restart always \
  -p 127.0.0.1:8080:8080 \
  -e NC_ALLOW_LOCAL_EXTERNAL_DBS=true \
  -e NC_JWT_EXPIRES_IN=3650d \
  nocodb/nocodb:latest
```

*Tham số `-e NC_JWT_EXPIRES_IN=3650d` đặt thời hạn token NocoDB là 10 năm để session duy trì liên tục.*

---

## 4. Lấy Token Quản Trị NocoDB (Cho Auto-Bypass)

1. Tạm thời truy cập vào NocoDB để tạo tài khoản quản trị đầu tiên.
2. Mở công cụ nhà phát triển trên trình duyệt (**F12**), chuyển sang tab **Application** (hoặc **Storage**) $\rightarrow$ **Cookies** $\rightarrow$ chọn domain NocoDB.
3. Tìm cookie có tên **`refresh_token`** và sao chép toàn bộ giá trị chuỗi của nó (ví dụ: `7ca2d6f6f8dafd0e9f...`).

---

## 5. Cấu Hình Nginx Reverse Proxy (`db_nocodb`)

Tạo file cấu hình Nginx cho subdomain:

```bash
sudo nano /etc/nginx/sites-available/db_nocodb
```

Nội dung file:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name db.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name db.yourdomain.com;

    # Cấu hình chứng chỉ SSL Let's Encrypt
    ssl_certificate /etc/letsencrypt/live/db.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/db.yourdomain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Chuyển hướng khi chưa đăng nhập hoặc không đủ quyền
    error_page 401 403 502 = @login_redirect;
    location @login_redirect {
        return 302 https://yourdomain.com/accounts/login/?next=https://$host$request_uri;
    }

    # 1. Điểm kiểm tra session admin qua HTTPS của domain chính
    location = /internal_check_admin {
        internal;
        proxy_pass https://yourdomain.com/api/verify-admin/;
        proxy_ssl_server_name on;
        proxy_ssl_verify off;

        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Host yourdomain.com;
        proxy_set_header Cookie $http_cookie;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    # 2. Proxy vào NocoDB khi đã xác thực thành công
    location / {
        auth_request /internal_check_admin;

        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Gắn kèm cookie refresh_token để tự động đăng nhập NocoDB
        proxy_set_header Cookie "refresh_token=DIEN_CHUOI_REFRESH_TOKEN_TAI_DAY; $http_cookie";
    }
}
```

*Kích hoạt cấu hình và tải lại Nginx:*

```bash
sudo ln -sf /etc/nginx/sites-available/db_nocodb /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

*(Nếu chưa có chứng chỉ SSL cho subdomain, chạy lệnh: `sudo certbot --nginx -d db.yourdomain.com`)*.

---

## 6. Kiểm Thử & Vận Hành

| Tình huống kiểm thử | Kết quả mong đợi |
| :--- | :--- |
| Mở cửa sổ ẩn danh vào `https://db.yourdomain.com` | Nginx chặn và chuyển hướng ngay về trang login: `https://yourdomain.com/accounts/login/?next=https://db.yourdomain.com/` |
| Đăng nhập tài khoản user thường (học sinh) | Bị chặn và chuyển hướng về trang login (do endpoint trả `403`) |
| Đăng nhập tài khoản Admin trên `yourdomain.com` rồi vào `https://db.yourdomain.com` | Vào thẳng dashboard quản trị NocoDB, không cần đăng nhập lại |

---

## 7. Các Lưu Ý Khi Bảo Trì

* **Khi xóa toàn bộ cookie trình duyệt:** Hãy đăng nhập lại tại trang chính `yourdomain.com` trước khi vào subdomain để đảm bảo cookie `sessionid` mang đúng scope `.yourdomain.com`.
* **Nếu đổi password tài khoản Admin NocoDB:** Cập nhật lại giá trị `refresh_token` mới trong file Nginx cấu hình `db_nocodb` và reload lại Nginx.