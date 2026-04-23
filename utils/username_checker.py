# -*- coding: utf-8 -*-
"""
دوال فحص توافر اليوزرنيم على المنصات المختلفة
"""

import aiohttp
import asyncio
import logging

logger = logging.getLogger(__name__)


async def check_username_availability(username):
    """
    فحص توافر اسم المستخدم على جميع المنصات
    
    المعاملات:
    - username: اسم المستخدم المراد فحصه (بدون @)
    
    الإرجاع:
    - dict: نتائج الفحص لكل منصة
    """
    results = {}
    
    # إزالة @ إذا وجدت
    if username.startswith('@'):
        username = username[1:]
    
    # تعريف المنصات وروابط الفحص
    platforms = {
        'youtube': {
            'url': f'https://www.youtube.com/@{username}',
            'name': '🎬 يوتيوب'
        },
        'instagram': {
            'url': f'https://www.instagram.com/{username}/',
            'name': '📸 انستقرام'
        },
        'tiktok': {
            'url': f'https://www.tiktok.com/@{username}',
            'name': '🎵 تيك توك'
        },
        'facebook': {
            'url': f'https://www.facebook.com/{username}',
            'name': '📘 فيسبوك'
        }
    }
    
    # فحص جميع المنصات بشكل متوازي (أسرع)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for platform, info in platforms.items():
            tasks.append(check_platform(session, platform, info['url'], info['name'], username))
        
        # انتظار جميع المهام
        platform_results = await asyncio.gather(*tasks)
        
        # تجميع النتائج
        for platform, result in platform_results:
            results[platform] = result
    
    return results


async def check_platform(session, platform, url, display_name, username):
    """
    فحص منصة واحدة
    """
    try:
        async with session.get(url, timeout=10, allow_redirects=True) as response:
            # التحقق من حالة الاستجابة
            if response.status == 200:
                status = 'taken'  # الاسم محجوز
                message = '❌ غير متاح'
                detail = 'هذا الاسم مستخدم بالفعل'
            elif response.status == 404:
                status = 'available'  # الاسم متاح
                message = '✅ متاح'
                detail = 'يمكنك استخدام هذا الاسم'
            else:
                # حالات أخرى (مثل 403, 429, إلخ)
                status = 'unknown'
                message = '⚠️ غير معروف'
                detail = f'لم نتمكن من التحقق (الرمز: {response.status})'
    except asyncio.TimeoutError:
        status = 'error'
        message = '⏰ مهلة'
        detail = 'استغرق الفحص وقتاً طويلاً'
    except Exception as e:
        logger.error(f"Error checking {platform}: {e}")
        status = 'error'
        message = '❌ خطأ'
        detail = str(e)[:50]
    
    return platform, {
        'name': display_name,
        'status': status,
        'message': message,
        'detail': detail,
        'url': url
    }


def format_check_result(results, username):
    """
    تنسيق نتائج الفحص إلى نص جميل
    """
    # إحصائيات سريعة
    total = len(results)
    available = sum(1 for r in results.values() if r['status'] == 'available')
    taken = sum(1 for r in results.values() if r['status'] == 'taken')
    unknown = total - available - taken
    
    text = f"🔍 <b>نتيجة فحص اليوزرنيم @{username}</b>\n\n"
    text += f"📊 <b>ملخص سريع:</b>\n"
    text += f"• ✅ متاح: {available}\n"
    text += f"• ❌ محجوز: {taken}\n"
    text += f"• ⚠️ غير معروف: {unknown}\n\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📋 <b>التفاصيل:</b>\n\n"
    
    for platform, data in results.items():
        icon = "✅" if data['status'] == 'available' else "❌" if data['status'] == 'taken' else "⚠️"
        text += f"{icon} <b>{data['name']}</b>: {data['message']}\n"
        text += f"   <i>{data['detail']}</i>\n\n"
    
    text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"💡 <b>نصيحة:</b>\n"
    
    if available > 0:
        text += f"• يمكنك استخدام @{username} على {available} منصة\n"
    if taken > 0:
        text += f"• الاسم @{username} محجوز على {taken} منصة\n"
        text += f"• جرب إضافة أرقام أو كلمات مثل: {username}_official, _{username}, {username}1\n"
    
    return text


async def check_single_platform(username, platform):
    """
    فحص منصة واحدة فقط (للاستخدام السريع)
    
    المعاملات:
    - username: اسم المستخدم
    - platform: اسم المنصة (youtube, instagram, tiktok, facebook)
    """
    platforms_urls = {
        'youtube': f'https://www.youtube.com/@{username}',
        'instagram': f'https://www.instagram.com/{username}/',
        'tiktok': f'https://www.tiktok.com/@{username}',
        'facebook': f'https://www.facebook.com/{username}'
    }
    
    names = {
        'youtube': '🎬 يوتيوب',
        'instagram': '📸 انستقرام',
        'tiktok': '🎵 تيك توك',
        'facebook': '📘 فيسبوك'
    }
    
    if platform not in platforms_urls:
        return None
    
    async with aiohttp.ClientSession() as session:
        result = await check_platform(
            session, 
            platform, 
            platforms_urls[platform], 
            names.get(platform, platform), 
            username
        )
        return result[1]  # إرجاع البيانات فقط
