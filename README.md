python -c "
content = '''# HOTEL ROOM BOOKING SYSTEM - GRAND HORIZON HOTEL
> **Đồ án môn Kỹ thuật Phần mềm**  
> **Thời gian nộp bài:** 22:59 - 22/11/2026 | **Đóng gói:** ProgAndTest_GroupXY.zip

---


## 1. CẤU TRÚC THƯ MỤC DỰ ÁN (MÔ HÌNH MVC)
<img width="876" height="556" alt="image" src="https://github.com/user-attachments/assets/da19b715-a73a-45af-a972-b9e538684c82" />


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
## 4. QUY TẮC LÀM VIỆC VỚI GIT
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
