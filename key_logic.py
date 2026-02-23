from datetime import datetime, timedelta
from fastapi import Header, HTTPException
from database import get_connection

def activation_required(x_activation_code: str = Header(...)):
    """
    التحقق من صلاحية كود التفعيل.
    - إذا كان الاشتراك لم يبدأ بعد (started_at = NULL) يتم بدؤه الآن.
    - يتم التحقق من انتهاء المدة والحد الأقصى للاستخدام.
    - لا يتم خصم الاستخدام هنا، بل بعد نجاح الطلب.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, is_active, started_at, expires_at,
               duration_minutes, duration_days,
               usage_limit, usage_count
        FROM activation_codes
        WHERE code=?
    """, (x_activation_code,))

    row = cur.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=403, detail="كود التفعيل غير صحيح")

    (code_id, active, started_at, expires_at,
     duration_minutes, duration_days,
     usage_limit, usage_count) = row

    if not active:
        conn.close()
        raise HTTPException(status_code=403, detail="تم إيقاف الاشتراك")

    now = datetime.utcnow()

    # 🔥 بدء الاشتراك عند أول استخدام فقط
    if not started_at:
        # حساب مدة الاشتراك
        delta = timedelta(
            minutes=duration_minutes or 0,
            days=duration_days or 0
        )
        new_expiry = now + delta

        cur.execute("""
            UPDATE activation_codes
            SET started_at=?, expires_at=?
            WHERE id=?
        """, (now.isoformat(), new_expiry.isoformat(), code_id))

        conn.commit()

        # تحديث المتغير المحلي
        expires_at = new_expiry.isoformat()
        started_at = now.isoformat()

    # التحقق من انتهاء المدة
    if expires_at and datetime.fromisoformat(expires_at) < now:
        conn.close()
        raise HTTPException(status_code=403, detail="انتهت مدة الاشتراك")

    # التحقق من الحد الأقصى للاستخدام (لكن لا نخصم هنا)
    if usage_limit is not None and usage_count >= usage_limit:
        conn.close()
        raise HTTPException(status_code=403, detail="تم استهلاك جميع الاستخدامات المسموحة")

    conn.close()
    return code_id
