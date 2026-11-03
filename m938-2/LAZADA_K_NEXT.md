# สำหรับ K — Lazada Open Platform: K ทำครบแล้ว ✅

K ยืนยัน **เบอร์มือถือ (SMS)** สำเร็จ → ข้อมูลโปรไฟล์ทุกช่องขึ้น **ok หมด**
**ไม่ต้องทำอะไรเพิ่มแล้ว** AF ดูแลทุกอย่างต่อเอง

## สถานะปัจจุบัน

| ขั้น | สถานะ |
|---|---|
| สมัครบัญชี developer (AF ทำเอง) | ✅ เสร็จ |
| กรอกโปรไฟล์ + ยืนยันอีเมล (AF) | ✅ เสร็จ |
| ยืนยันเบอร์มือถือ SMS (**K ทำ**) | ✅ เสร็จ |
| ยื่นขอหมวดหมู่แอป `Seller In-house APP` (AF) | ✅ ยื่นแล้ว — รอ Lazada อนุมัติ |
| **Lazada ตรวจสอบโปรไฟล์** | ⏳ **"Under review · 1-3 วันทำการ"** (คิวของ Lazada) |
| สร้าง App + คัดลอก Key/Secret (AF) | ⏳ รออนุมัติแล้ว AF ทำต่ออัตโนมัติ |

## AF ทำต่อเองอัตโนมัติ (ไม่ต้องรบกวน K)

AF ตั้งระบบ **autopilot** รันทุก 15 นาที ไว้แล้ว:
- ระหว่างรออนุมัติ → แค่บันทึกสถานะ
- **พอ Lazada อนุมัติ → สร้าง App ให้ทันที** + เก็บ App Key/Secret ลง
  `/workspace/.secrets/lazada.json`
- หลังจากนั้น AF ใช้ API จัดการสินค้า/ออเดอร์บนร้าน Lazada ของ K เอง

## ถ้า K อยากดู

- หน้าจอ noVNC: `https://work-2-fpiyshleayaejilh.prod-runtime.all-hands.dev/vnc.html?autoconnect=1&resize=scale` (รหัส `af938pod`)
- หน้าสถานะ: `https://isvconsole.lazada.com/web/isv/basic-info.html`
- ไฟล์หลักฐาน: `out/lazada_profile_under_review.png`, `out/lazada_appcat_pending.png`

## หมายเหตุ

- รหัสบัญชี developer อยู่ที่ `/workspace/.secrets/lazada-dev.json` (ไม่อยู่ใน git)
- **ยังเหลือ 1 จุดที่ต้องใช้บัญชี Lazada seller ของ K** — ตอนกด **authorize แอป** (AF จะพิมพ์ลิงก์ให้กดครั้งเดียว)
