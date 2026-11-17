python -c "
content = '''# HOTEL ROOM BOOKING SYSTEM - GRAND HORIZON HOTEL
> **Đồ án môn Kỹ thuật Phần mềm**  
> **Thời gian nộp bài:** 22:59 - 22/11/2026 | **Đóng gói:** ProgAndTest_GroupXY.zip

---


## 1. CẤU TRÚC THƯ MỤC DỰ ÁN (MÔ HÌNH MVC)

\`\`\`text
hotel_project/
├── manage.py                          <-- File điều khiển Django
├── requirements.txt                   <-- Danh sách thư viện cần cài
├── Dockerfile                         <-- File đóng gói Docker nộp cô
├── README.md                          <-- Hướng dẫn vận hành nhóm
│
├── config/                            <-- [Leader] Cấu hình hệ thống (settings, urls, wsgi)
│
├── apps/                              <-- 4 PHÂN HỆ NGHIỆP VỤ (USE CASES)
│   ├── core/                          <-- [Leader] Chứa 11 bảng CSDL (models.py)
│   ├── customer/                      <-- [Member 3] Luồng Khách hàng (UC-01 -> UC-14)
│   ├── receptionist/                  <-- [Member 2] Nghiệp vụ Lễ tân (UC-15 -> UC-24)
│   ├── manager/                       <-- [Member 2 & 4] Dashboard Quản lý (UC-25 -> UC-31)
│   └── administrator/                 <-- [Member 2] Quản trị nhân sự & Logs (UC-32 -> UC-34)
│
├── templates/                         <-- 8 MÀN HÌNH GIAO DIỆN FIGMA (UI-01 -> UI-08)
│   ├── customer/                      <-- UI-01 (Home), UI-02 (List), UI-03 (Detail), UI-04 (Booking)
│   ├── receptionist/                  <-- UI-06 (Sơ đồ phòng Room Rack)
│   └── manager/                       <-- UI-07 (Dashboard Báo cáo)
│
├── tests/                             <-- [Member 5] Code kiểm thử tự động (Unit Tests)
└── docs/                              <-- [Member 5] Bảng Test Cases & Minh chứng công cụ
\`\`\`

---

## 2. CÁC BƯỚC CÀI ĐẶT & CHẠY DỰ ÁN

### Bước 1: Clone dự án về máy
\`\`\`bash
git clone <LINK_REPO_GITHUB>
cd Hotel-booking-room-System
\`\`\`

### Bước 2: Tạo và kích hoạt môi trường ảo
\`\`\`bash
python -m venv venv
venv\\Scripts\\activate
\`\`\`

### Bước 3: Cài đặt thư viện
\`\`\`bash
pip install -r requirements.txt
\`\`\`

### Bước 4: Khởi tạo Database & Tạo tài khoản Admin
\`\`\`bash
python manage.py migrate
python manage.py createsuperuser
\`\`\`

### Bước 5: Bật Server chạy thử
\`\`\`bash
python manage.py runserver
\`\`\`
- Trang chủ khách hàng: http://127.0.0.1:8000/
## 🌳 4. QUY TẮC LÀM VIỆC VỚI GIT
1. **Tuyệt đối KHÔNG commit trực tiếp vào nhánh main**.
2. **Mỗi thành viên tự tạo nhánh riêng để làm tính năng:**
   - Bạn 2: \`git checkout -b feature/receptionist-backend\`
   - Bạn 3: \`git checkout -b feature/client-ui\`
   - Bạn 4: \`git checkout -b feature/admin-ui\`
   - Bạn 5: \`git checkout -b feature/qa-testing\`
3. **Đẩy code lên nhánh của mình và tạo Pull Request (PR):**
\`\`\`bash
git add .
git commit -m \"Mô tả việc vừa làm\"
git push origin <tên-nhánh-của-bạn>
\`\`\`
4. Vào GitHub bấm **Compare & pull request** để Trưởng nhóm duyệt code vào nhánh main.
'''
with open('README.md', 'w', encoding='utf-8') as f:
    f.write(content)
print('Xong! File README.md da duoc tao dep 100%!')
"