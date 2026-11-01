# พร้อมท์ขอข้อมูลจาก AI ทีม (AI1 / AI2) → ส่งกลับให้ AF

**วิธีใช้**
1. คัดลอก "พร้อมท์" ของ AI ตัวนั้น ไปวางใน OpenHands ของ AI ตัวนั้น
2. AI จะตอบกลับเป็น JSON
3. เอา JSON มาวางในไฟล์ (เช่น `ai1.json`) แล้วตรวจด้วย:
   `python3 /workspace/af_intake/intake.py ai1.json`
4. ถ้าขึ้น ✅ ส่งไฟล์ให้ AF ได้เลย

**กฎสำคัญ (ใส่ไว้ในพร้อมท์แล้ว)**
- ห้ามเดาตัวเลข — ถ้าไม่รู้ให้ใส่ `"UNKNOWN"`
- ตัวเลขต้องมาจากหลังบ้านจริง (YouTube Studio / Shopee Seller / Meta Business Suite)
- `channel_name` ห้ามเป็น UNKNOWN
- `needs_help_with` ต้องบอกว่าอยากให้ AF ช่วยอะไร

---

## พร้อมท์สำหรับ AI1 (ทำ YouTube 2 ช่อง)

```
สวัสดี เราคือ AF (Executive Management ของ AKATH) ทำงานร่วมกับ K

ขอข้อมูลจากช่อง YouTube ที่คุณดูแล 2 ช่อง เพื่อให้ผมผลิตงานที่ใช้ได้จริงให้คุณ

ข้อกำหนด:
- ห้ามเดาตัวเลข ถ้าไม่รู้ให้ใส่ "UNKNOWN"
- ตัวเลขทั้งหมดให้ดูจาก YouTube Studio > Analytics (ไม่ใช่ประมาณ)
- ถ้าเข้าไม่ได้ ให้ใส่ "UNKNOWN" และบอกเหตุผลใน blockers

ตอบกลับเป็น JSON ตามโครงนี้เท่านั้น (ไม่ต้องมีคำอธิบายอื่น):

{
  "account_label": "AI1",
  "channels": [
    {
      "channel_name": "ชื่อช่องจริง",
      "channel_url": "https://youtube.com/@... หรือ UNKNOWN",
      "niche": "หมวดเนื้อหา เช่น การเงิน/เกม/ทำอาหาร",
      "language": "th",
      "subscribers": 0,
      "total_videos": 0,
      "uploads_per_week": 0,
      "avg_views_last_10": 0,
      "top_videos": [
        {"title": "ชื่อคลิปที่คนดูมากสุด", "views": 0, "url": "ลิงก์หรือ UNKNOWN"}
      ],
      "format": "shorts หรือ long หรือ mixed",
      "monetized": false,
      "monthly_revenue_thb": 0,
      "biggest_problem": "ปัญหาที่ทำให้ช่องไม่โต",
      "needs_help_with": "อยากให้ AF ช่วยเรื่องอะไร (สคริปต์/ชื่อคลิป/แท็ก/ไอเดีย ฯลฯ)"
    }
  ],
  "other_platforms": {"facebook": "ชื่อเพจหรือ UNKNOWN", "tiktok": "หรือ UNKNOWN"},
  "shopee": {"shop_url": "หรือ UNKNOWN", "category": "หมวดสินค้าที่ขาย"},
  "assets": ["ของที่มีอยู่แล้ว เช่น คลิปเก่า 20 ไฟล์, ภาพสินค้า 50 รูป"],
  "goal_thb_per_month": 0,
  "blockers": ["สิ่งที่ติดอยู่"]
}

ทำช่องที่ 1 ให้ครบก่อน แล้วทำช่องที่ 2 ในอาร์เรย์เดียวกัน
```

---

## พร้อมท์สำหรับ AI2 (ทำ YouTube 1 ช่อง + เพจ FB + TikTok + Affiliate Shopee)

```
สวัสดี เราคือ AF (Executive Management ของ AKATH) ทำงานร่วมกับ K

ขอข้อมูลจากช่อง YouTube 1 ช่อง + เพจ Facebook + TikTok + Affiliate Shopee ที่คุณดูแล
เพื่อให้ผมผลิตงานที่ใช้ได้จริงให้คุณ

ข้อกำหนด:
- ห้ามเดาตัวเลข ถ้าไม่รู้ให้ใส่ "UNKNOWN"
- ตัวเลข YouTube ดูจาก YouTube Studio > Analytics
- ตัวเลข Facebook ดูจาก Meta Business Suite > Insights
- ตัวเลข TikTok ดูจาก TikTok Analytics
- Affiliate Shopee ดูจาก Shopee Affiliate > รายงาน (หรือ UNKNOWN)
- ถ้าเข้าไม่ได้ ให้ใส่ "UNKNOWN" และบอกเหตุผลใน blockers

ตอบกลับเป็น JSON ตามโครงนี้เท่านั้น (ไม่ต้องมีคำอธิบายอื่น):

{
  "account_label": "AI2",
  "channels": [
    {
      "channel_name": "ชื่อช่องจริง",
      "channel_url": "https://youtube.com/@... หรือ UNKNOWN",
      "niche": "หมวดเนื้อหา",
      "language": "th",
      "subscribers": 0,
      "total_videos": 0,
      "uploads_per_week": 0,
      "avg_views_last_10": 0,
      "top_videos": [
        {"title": "ชื่อคลิปที่คนดูมากสุด", "views": 0, "url": "ลิงก์หรือ UNKNOWN"}
      ],
      "format": "shorts หรือ long หรือ mixed",
      "monetized": false,
      "monthly_revenue_thb": 0,
      "biggest_problem": "ปัญหาที่ทำให้ช่องไม่โต",
      "needs_help_with": "อยากให้ AF ช่วยเรื่องอะไร"
    }
  ],
  "other_platforms": {
    "facebook_page": {
      "name": "ชื่อเพจ",
      "followers": 0,
      "posts_per_week": 0,
      "avg_reach_per_post": 0,
      "engagement_rate_pct": "UNKNOWN",
      "what_sells_best": "โพสต์แบบไหนคนสนใจสุด"
    },
    "tiktok": {
      "handle": "@...",
      "followers": 0,
      "total_videos": 0,
      "avg_views": 0,
      "best_video": {"title": "หรือคำอธิบาย", "views": 0}
    },
    "shopee_affiliate": {
      "program": "affiliate หรือ seller หรือ both",
      "commission_pct": "UNKNOWN",
      "clicks_last_30d": "UNKNOWN",
      "orders_last_30d": "UNKNOWN",
      "revenue_thb_last_30d": "UNKNOWN",
      "best_categories": ["หมวดที่ขายได้ดี"],
      "link_placement": "แปะลิงก์ที่ไหน (ไบโอ/คอมเมนต์/ในคลิป)"
    }
  },
  "shopee": {"shop_url": "หรือ UNKNOWN", "category": "หมวดสินค้า"},
  "assets": ["ของที่มีอยู่แล้ว"],
  "goal_thb_per_month": 0,
  "blockers": ["สิ่งที่ติดอยู่"]
}
```

---

## สิ่งที่ AF จะทำกับข้อมูลนี้ (บอก AI ทีมได้เลย)

| ข้อมูล | AF เอาไปทำอะไร |
|---|---|
| ชื่อช่อง + niche | ผลิตชื่อคลิป/คำอธิบาย/แท็ก เฉพาะทาง |
| top_videos + views | วิเคราะห์ว่าอะไรได้ผล แล้วทำซ้ำสูตรนั้น |
| avg_views_last_10 | รู้ฐานจริง → ตั้งเป้าเพิ่มแบบมีเหตุผล |
| biggest_problem + needs_help_with | เลือกงานที่ช่วยได้ตรงจุดที่สุด |
| shopee_affiliate | เขียนคอนเทนต์ที่พาคนไปซื้อ |
| assets | ใช้ของที่มีอยู่ ไม่ต้องผลิตซ้ำ |
| goal_thb_per_month | คำนวณว่าต้องกี่วิว/กี่ออเดอร์จึงถึงเป้า |

## หมายเหตุเรื่องความปลอดภัย

พร้อมท์นี้ขอแค่ **ตัวเลขสรุป + ชื่อช่อง + ปัญหา**
ไม่ขอรหัสผ่าน ไม่ขอคุกกี้ ไม่ขอลิงก์ล็อกอิน
AI ทีมดูตัวเลขจากหน้าจอหลังบ้านของตัวเองแล้วพิมพ์ใส่ JSON เท่านั้น
