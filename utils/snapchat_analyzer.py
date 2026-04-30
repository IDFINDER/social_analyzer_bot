# utils/snapchat_analyzer.py
import aiohttp
import logging
from utils.snapchat_auth import get_token

logger = logging.getLogger(__name__)

SNAPCHAT_API_BASE = "https://businessapi.snapchat.com"

async def get_snapchat_profile(user_id):
    """جلب بيانات ملف المستخدم الشخصي"""
    access_token = get_token(user_id)
    if not access_token:
        return None, "❌ لم يتم تفعيل Snapchat بعد.\n\n🔐 يرجى استخدام زر 'تفعيل سناب شات' أولاً."
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    try:
        async with aiohttp.ClientSession() as session:
            # محاولة جلب معلومات المستخدم
            async with session.get(f"{SNAPCHAT_API_BASE}/v1/me", headers=headers) as response:
                if response.status == 401:
                    return None, "⚠️ انتهت صلاحية التوكن. يرجى إعادة التفعيل."
                if response.status != 200:
                    return None, f"❌ فشل جلب البيانات: خطأ {response.status}"
                
                user_data = await response.json()
                
                # استخراج بيانات المستخدم
                profile = user_data.get('data', {})
                
                return {
                    'success': True,
                    'display_name': profile.get('display_name', 'غير محدد'),
                    'username': profile.get('username', 'غير محدد'),
                    'bio': profile.get('bio', 'لا يوجد'),
                    'follower_count': profile.get('follower_count', 0),
                    'following_count': profile.get('following_count', 0),
                    'public_profile_url': profile.get('public_profile_url', ''),
                    'is_verified': profile.get('is_verified', False)
                }, None
                
    except aiohttp.ClientError as e:
        logger.error(f"Network error: {e}")
        return None, f"❌ خطأ في الشبكة: {str(e)}"
    except Exception as e:
        logger.error(f"Error in get_snapchat_profile: {e}")
        return None, f"❌ حدث خطأ غير متوقع: {str(e)}"

async def format_snapchat_report(user_id):
    """تنسيق تقرير Snapchat بشكل جميل"""
    profile, error = await get_snapchat_profile(user_id)
    
    if error:
        return error
    
    verified_badge = "✅ موثق" if profile.get('is_verified') else "❌ غير موثق"
    
    report = f"""
📸 <b>تحليل حساب Snapchat</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 <b>الاسم:</b> {profile.get('display_name')}
🔖 <b>المعرف:</b> @{profile.get('username')}
✅ <b>الحالة:</b> {verified_badge}

📝 <b>السيرة الذاتية:</b>
{profile.get('bio', 'لا يوجد')[:200]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>الإحصائيات:</b>
👥 <b>المتابعون:</b> {profile.get('follower_count', 0):,}
👣 <b>يتابع:</b> {profile.get('following_count', 0):,}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔗 <b>الرابط:</b>
{profile.get('public_profile_url', 'غير متوفر')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 <b>ملاحظة:</b> هذه البيانات متاحة من الملف الشخصي العام.
📌 لمزيد من التفاصيل (المنشورات، القصص)، يلزم صلاحيات إضافية.
"""
    return report
