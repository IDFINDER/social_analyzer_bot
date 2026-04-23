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
    فحص توافر اسم المستخدم على يوتيوب فقط (حالياً)
    
    المعاملات:
    - username: اسم المستخدم المراد فحصه (بدون @)
    
    الإرجاع:
    - dict: نتائج الفحص
    """
    results = {}
    
    # إزالة @ إذا وجدت
    if username.startswith('@'):
        username = username[1:]
    
    # تعريف المنصات (يوتيوب فقط يعمل، الباقي قيد التطوير)
    platforms = {
        'youtube': {
            'url': f'https://www.youtube.com/@{username}',
            'name': '🎬 يوتيوب',
            'active': True  # مفعل
        },
        'instagram': {
            'url': f'https://www.instagram.com/{username}/',
            'name': '📸 انستقرام',
            'active': False,
            'message': '🚧 قيد التطوير'
        },
        'tiktok': {
            'url': f'https://www.tiktok.com/@{username}',
            'name': '🎵 تيك توك',
            'active': False,
            'message': '🚧 قيد التطوير'
        },
        'facebook': {
            'url': f'https://www.facebook.com/{username}',
            'name': '📘 فيسبوك',
            'active': False,
            'message': '🚧 قيد التطوير'
        }
    }
    
    async with aiohttp.ClientSession() as session:
        for platform, info in platforms.items():
            if info.get('active', False):
                # فحص المنصة النشطة
                result = await check_platform(session, platform, info['url'], info['name'], username)
                results[platform] = result
            else:
                # منصة غير مفعلة
                results[platform] = {
                    'name': info['name'],
                    'status': 'pending',
                    'message': info.get('message', '🚧 قيد التطوير'),
                    'detail': 'سيتم إضافة هذه المنصة قريباً',
                    'url': info['url']
                }
    
    return results


async def check_platform(session, platform, url, display_name, username):
    """
    فحص منصة واحدة
    """
    try:
        async with session.get(url, timeout=10, allow_redirects=True) as response:
            # التحقق من حالة الاستجابة
            if response.status == 200:
                status = 'taken'
                message = '❌ غير متاح'
                detail = 'هذا الاسم مستخدم بالفعل'
            elif response.status == 404:
                status = 'available'
                message = '✅ متاح'
                detail = 'يمكنك استخدام هذا الاسم'
            else:
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
    
    return {
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
    available = sum(1 for r in results.values() if r.get('status') == 'available')
    taken = sum(1 for r in results.values() if r.get('status') == 'taken')
    pending = sum(1 for r in results.values() if r.get('status') == 'pending')
    unknown = total - available - taken - pending
    
    text = f"🔍 <b>نتيجة فحص اليوزرنيم @{username}</b>\n\n"
    text += f"📊 <b>ملخص سريع:</b>\n"
    text += f"• ✅ متاح: {available}\n"
    text += f"• ❌ محجوز: {taken}\n"
    text += f"• 🚧 قيد التطوير: {pending}\n"
    if unknown > 0:
        text += f"• ⚠️ غير معروف: {unknown}\n"
    
    text += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📋 <b>التفاصيل:</b>\n\n"
    
    for platform, data in results.items():
        if data.get('status') == 'pending':
            icon = "🚧"
        elif data.get('status') == 'available':
            icon = "✅"
        elif data.get('status') == 'taken':
            icon = "❌"
        else:
            icon = "⚠️"
        
        text += f"{icon} <b>{data['name']}</b>: {data['message']}\n"
        text += f"   <i>{data['detail']}</i>\n\n"
    
    text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"💡 <b>نصيحة:</b>\n"
    
    if available > 0:
        text += f"• يمكنك استخدام @{username} على يوتيوب 🎬\n"
        text += f"• قم بالتسجيل الآن قبل أن ينتهي الاسم!\n"
    if taken > 0:
        text += f"• الاسم @{username} مستخدم على يوتيوب ❌\n"
        text += f"• جرب إضافة أرقام أو كلمات مثل: {username}_official, {username}1\n"
    
    text += f"\n🚀 <b>قريباً:</b> سنضيف فحصاً لبقية المنصات (انستقرام، تيك توك، فيسبوك)"
    
    return text


async def check_single_platform(username, platform='youtube'):
    """
    فحص منصة واحدة (افتراضياً يوتيوب)
    """
    if platform != 'youtube':
        return {
            'name': '🎬 يوتيوب' if platform == 'youtube' else platform,
            'status': 'pending',
            'message': '🚧 قيد التطوير',
            'detail': 'هذه المنصة ستتوفر قريباً',
            'url': '#'
        }
    
    if username.startswith('@'):
        username = username[1:]
    
    url = f'https://www.youtube.com/@{username}'
    
    async with aiohttp.ClientSession() as session:
        result = await check_platform(session, platform, url, '🎬 يوتيوب', username)
        return result
