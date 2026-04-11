# -*- coding: utf-8 -*-
"""
دوال قاعدة البيانات للبوت الجديد
"""

import os
import logging
import hashlib
import random
import string
from datetime import datetime, date, timedelta
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# ========== إعدادات Supabase ==========
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
BOT_NAME = os.environ.get('BOT_NAME', 'social_analyzer')
FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '2'))
GEMINI_DAILY_LIMIT = int(os.environ.get('GEMINI_DAILY_LIMIT', '5'))

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY are required")

# عميل عام (للوظائف العادية - قراءة فقط)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# عميل مدير (للعمليات الحساسة - كتابة/حذف/تحديث)
if SUPABASE_SERVICE_KEY:
    supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
else:
    supabase_admin = supabase
    logger.warning("⚠️ SUPABASE_SERVICE_ROLE_KEY not set, using anon key for admin operations")


# ========== دوال المستخدمين (قراءة فقط - supabase) ==========

def get_or_create_user(user_id, first_name, username, language_code):
    """جلب أو إنشاء مستخدم"""
    try:
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()
        
        if response.data:
            user = response.data[0]
            logger.info(f"✅ مستخدم موجود مسبقاً: {user_id}")
            if user.get('first_name') != first_name or user.get('username') != username:
                supabase.table('users').update({
                    'first_name': first_name,
                    'username': username or '',
                    'language_code': language_code or ''
                }).eq('user_id', user_id).execute()
            return user
        
        new_user = {
            'user_id': user_id,
            'first_name': first_name,
            'username': username or '',
            'language_code': language_code or '',
            'status': 'free'
        }
        response = supabase.table('users').insert(new_user).execute()
        logger.info(f"✅ تم إنشاء مستخدم جديد: {user_id}")
        return response.data[0]
        
    except Exception as e:
        logger.error(f"Error in get_or_create_user: {e}")
        return None


def get_user_info(user_id):
    """جلب معلومات المستخدم"""
    try:
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        return None


def get_user_usage(user_id):
    """الحصول على استخدامات المستخدم للبوت الحالي"""
    try:
        response = supabase.table('bot_usage').select('*').eq('user_id', user_id).eq('bot_name', BOT_NAME).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting user usage: {e}")
        return None


def increment_usage(user_id, platform, analysis_results=None):
    """زيادة عدد استخدامات المستخدم حسب المنصة"""
    try:
        user = get_user_info(user_id)
        if not user:
            return False
        
        username = user.get('username', '')
        first_name = user.get('first_name', '')
        usage = get_user_usage(user_id)
        today = date.today().isoformat()
        
        platform_column_map = {
            'youtube': 'youtube_uses',
            'instagram': 'instagram_uses',
            'tiktok': 'tiktok_uses',
            'facebook': 'facebook_uses'
        }
        platform_column = platform_column_map.get(platform, 'youtube_uses')
        
        if usage and usage.get('last_use_date') != today:
            if user['status'] == 'free':
                supabase.table('bot_usage').update({
                    'daily_uses': 0,
                    'last_use_date': today,
                    'username': username,
                    'first_name': first_name
                }).eq('user_id', user_id).eq('bot_name', BOT_NAME).execute()
                usage = get_user_usage(user_id)
        
        current_platform_uses = usage.get(platform_column, 0) if usage else 0
        current_daily_uses = usage.get('daily_uses', 0) if usage else 0
        current_total_uses = usage.get('total_uses', 0) if usage else 0
        
        new_platform_uses = current_platform_uses + 1
        new_daily_uses = current_daily_uses + 1 if user['status'] == 'free' else current_daily_uses
        new_total_uses = current_total_uses + 1
        
        update_data = {
            'total_uses': new_total_uses,
            'updated_at': datetime.now().isoformat(),
            'username': username,
            'first_name': first_name,
            platform_column: new_platform_uses
        }
        
        if user['status'] == 'free':
            update_data['daily_uses'] = new_daily_uses
            update_data['last_use_date'] = today
        
        supabase.table('bot_usage').upsert({
            'user_id': user_id,
            'bot_name': BOT_NAME,
            **update_data
        }, on_conflict='user_id,bot_name').execute()
        
        if analysis_results:
            supabase.table('analysis_history').insert({
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'platform': platform,
                'analysis_date': datetime.now().isoformat(),
                'account_name': analysis_results.get('account_name'),
                'subscribers': analysis_results.get('subscribers'),
                'total_posts': analysis_results.get('total_posts'),
                'top_posts': analysis_results.get('top_posts'),
                'top_comments': analysis_results.get('top_comments'),
                'ai_recommendations': analysis_results.get('ai_recommendations'),
                'is_premium': user['status'] == 'premium',
                'analysis_duration': analysis_results.get('duration')
            }).execute()
        
        logger.info(f"✅ Usage incremented for user {user_id} on platform {platform}")
        return True
        
    except Exception as e:
        logger.error(f"Error incrementing usage: {e}")
        return False


def can_analyze(user_id):
    """التحقق مما إذا كان المستخدم يمكنه التحليل"""
    user = get_user_info(user_id)
    if not user:
        return True, 0
    
    if user['status'] == 'premium' and user.get('premium_until'):
        if datetime.strptime(user['premium_until'], '%Y-%m-%d').date() < date.today():
            supabase.table('users').update({'status': 'free', 'premium_until': None}).eq('user_id', user_id).execute()
            user['status'] = 'free'
    
    if user['status'] == 'premium':
        return True, 0
    
    try:
        response = supabase.table('bot_usage').select('daily_uses').eq('user_id', user_id).eq('bot_name', BOT_NAME).execute()
        daily_uses = response.data[0]['daily_uses'] if response.data else 0
        
        if daily_uses >= FREE_LIMIT:
            return False, daily_uses
        return True, daily_uses
    except Exception as e:
        logger.error(f"Error in can_analyze: {e}")
        return True, 0


def get_remaining_analyses(user_id):
    """الحصول على عدد التحليلات المتبقية للمستخدم"""
    can_dl, current_uses = can_analyze(user_id)
    if not can_dl:
        return 0
    
    user = get_user_info(user_id)
    if user and user['status'] == 'premium':
        return -1
    
    return FREE_LIMIT - current_uses


def get_total_analyses(user_id):
    """الحصول على إجمالي تحليلات المستخدم"""
    usage = get_user_usage(user_id)
    return usage.get('total_uses', 0) if usage else 0


# ========== دوال حسابات المستخدمين (قراءة/كتابة - supabase) ==========

def get_user_social_accounts(user_id):
    """جلب جميع حسابات المستخدم"""
    try:
        response = supabase.table('user_social_accounts').select('*').eq('user_id', user_id).execute()
        return {acc['platform']: acc for acc in response.data} if response.data else {}
    except Exception as e:
        logger.error(f"Error getting user accounts: {e}")
        return {}


def get_user_account(user_id, platform):
    """جلب حساب مستخدم معين"""
    try:
        response = supabase.table('user_social_accounts').select('*').eq('user_id', user_id).eq('platform', platform).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting user account: {e}")
        return None


def save_user_account(user_id, platform, account_identifier, is_active=True):
    """حفظ أو تحديث حساب مستخدم"""
    try:
        supabase.table('user_social_accounts').upsert({
            'user_id': user_id,
            'platform': platform,
            'account_identifier': account_identifier,
            'is_active': is_active,
            'updated_at': datetime.now().isoformat()
        }).execute()
        
        logger.info(f"✅ تم حفظ حساب {platform} للمستخدم {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving user account: {e}")
        return False


def delete_user_account(user_id, platform):
    """حذف حساب مستخدم"""
    try:
        supabase.table('user_social_accounts').delete().eq('user_id', user_id).eq('platform', platform).execute()
        logger.info(f"✅ تم حذف حساب {platform} للمستخدم {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting user account: {e}")
        return False


# ========== دوال Gemini API (قراءة/كتابة - supabase) ==========

def get_gemini_usage(user_id):
    """الحصول على استخدامات Gemini للمستخدم"""
    try:
        response = supabase.table('gemini_usage').select('*').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting gemini usage: {e}")
        return None


def can_use_gemini(user_id):
    """التحقق مما إذا كان المستخدم يمكنه استخدام توصيات Gemini"""
    try:
        user = get_user_info(user_id)
        
        if user['status'] == 'free':
            return False, 0, "💎 هذه الميزة متاحة فقط للمستخدمين المميزين!"
        
        usage = get_gemini_usage(user_id)
        today = date.today().isoformat()
        
        if usage and usage.get('last_use_date') != today:
            supabase.table('gemini_usage').update({
                'daily_recommendations': 0,
                'last_use_date': today
            }).eq('user_id', user_id).execute()
            daily_uses = 0
        elif usage:
            daily_uses = usage.get('daily_recommendations', 0)
        else:
            supabase.table('gemini_usage').insert({
                'user_id': user_id,
                'daily_recommendations': 0,
                'total_recommendations': 0,
                'last_use_date': today
            }).execute()
            daily_uses = 0
        
        if daily_uses >= GEMINI_DAILY_LIMIT:
            return False, GEMINI_DAILY_LIMIT, f"⚠️ لقد وصلت للحد اليومي لاستخدام التوصيات!\n\n📊 الحد المسموح: {GEMINI_DAILY_LIMIT} توصية يومياً"
        
        remaining = GEMINI_DAILY_LIMIT - daily_uses
        return True, remaining, None
        
    except Exception as e:
        logger.error(f"Error in can_use_gemini: {e}")
        return False, 0, "❌ حدث خطأ، يرجى المحاولة لاحقاً"


def increment_gemini_usage(user_id):
    """زيادة عدد استخدامات Gemini للمستخدم"""
    try:
        usage = get_gemini_usage(user_id)
        today = date.today().isoformat()
        
        if usage:
            if usage.get('last_use_date') != today:
                supabase.table('gemini_usage').update({
                    'daily_recommendations': 1,
                    'total_recommendations': usage.get('total_recommendations', 0) + 1,
                    'last_use_date': today,
                    'updated_at': datetime.now().isoformat()
                }).eq('user_id', user_id).execute()
            else:
                supabase.table('gemini_usage').update({
                    'daily_recommendations': usage.get('daily_recommendations', 0) + 1,
                    'total_recommendations': usage.get('total_recommendations', 0) + 1,
                    'updated_at': datetime.now().isoformat()
                }).eq('user_id', user_id).execute()
        else:
            supabase.table('gemini_usage').insert({
                'user_id': user_id,
                'daily_recommendations': 1,
                'total_recommendations': 1,
                'last_use_date': today
            }).execute()
        
        return True
    except Exception as e:
        logger.error(f"Error incrementing gemini usage: {e}")
        return False


# ========== دوال صفحة البايو (كتابة - supabase_admin) ==========

def generate_bio_url(user_id):
    """إنشاء رابط فريد لصفحة البايو"""
    random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    time_part = datetime.now().timestamp()
    hash_input = f"{user_id}_{random_part}_{time_part}"
    url_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]
    return url_hash


def get_bio_page(user_id):
    """جلب صفحة البايو للمستخدم (قراءة فقط - supabase)"""
    try:
        response = supabase.table('bio_pages').select('*').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting bio page: {e}")
        return None


def get_bio_page_by_page_url(page_url):
    """جلب صفحة البايو بواسطة page_url (قراءة فقط - supabase)"""
    try:
        response = supabase.table('bio_pages').select('*').eq('page_url', page_url).eq('is_enabled', True).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting bio page by url: {e}")
        return None


def create_or_update_bio_page(user_id, display_name, accounts, custom_links=None, bio=None):
    """إنشاء أو تحديث صفحة البايو (كتابة - supabase_admin)"""
    try:
        existing = supabase_admin.table('bio_pages').select('page_url').eq('user_id', user_id).execute()
        
        if existing.data:
            page_url = existing.data[0]['page_url']
            supabase_admin.table('bio_pages').update({
                'display_name': display_name,
                'bio': bio or '',
                'accounts': accounts,
                'custom_links': custom_links or [],
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', user_id).execute()
            logger.info(f"✅ تم تحديث صفحة البايو للمستخدم {user_id}")
        else:
            page_url = generate_bio_url(user_id)
            supabase_admin.table('bio_pages').insert({
                'user_id': user_id,
                'display_name': display_name,
                'bio': bio or '',
                'accounts': accounts,
                'custom_links': custom_links or [],
                'page_url': page_url,
                'is_enabled': True,
                'views_count': 0,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }).execute()
            logger.info(f"✅ تم إنشاء صفحة بايو جديدة للمستخدم {user_id}")
        
        return page_url
    except Exception as e:
        logger.error(f"Error creating/updating bio page: {e}")
        return None


def increment_bio_views(page_url):
    """زيادة عدد مشاهدات صفحة البايو (تحديث - supabase)"""
    try:
        response = supabase.table('bio_pages').select('views_count').eq('page_url', page_url).execute()
        
        if response.data:
            current_views = response.data[0].get('views_count', 0)
            new_views = current_views + 1
            
            supabase.table('bio_pages').update({
                'views_count': new_views
            }).eq('page_url', page_url).execute()
            
        return True
    except Exception as e:
        logger.error(f"Error incrementing bio views: {e}")
        return False


def disable_bio_page(user_id):
    """تعطيل صفحة البايو (كتابة - supabase_admin)"""
    try:
        supabase_admin.table('bio_pages').update({
            'is_enabled': False,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error disabling bio page: {e}")
        return False


def update_bio_theme(user_id, theme_name):
    """تحديث ثيم صفحة البايو (كتابة - supabase_admin)"""
    try:
        supabase_admin.table('bio_pages').update({
            'theme_name': theme_name,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating theme: {e}")
        return False

def get_all_themes():
    """جلب جميع الثيمات المتاحة من قاعدة البيانات"""
    try:
        response = supabase.table('themes').select('*').order('sort_order').execute()
        if response.data:
            return response.data
        # fallback في حال عدم وجود جدول themes
        return [
            {'name': 'default', 'display_name': 'فاتح', 'sort_order': 1},
            {'name': 'dark', 'display_name': 'داكن', 'sort_order': 2},
        ]
    except Exception as e:
        logger.error(f"Error getting themes: {e}")
        return [
            {'name': 'default', 'display_name': 'فاتح', 'sort_order': 1},
            {'name': 'dark', 'display_name': 'داكن', 'sort_order': 2},
        ]

def update_bio_text(user_id, bio_text):
    """تحديث النبذة (كتابة - supabase_admin)"""
    try:
        result = supabase_admin.table('bio_pages').update({
            'bio': bio_text,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        
        if result.data:
            logger.info(f"✅ Bio updated for user {user_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error updating bio: {e}")
        return False


def update_bio_avatar(user_id, avatar_url):
    """تحديث الصورة الشخصية (كتابة - supabase_admin)"""
    try:
        result = supabase_admin.table('bio_pages').update({
            'avatar_url': avatar_url,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        
        if result.data:
            logger.info(f"✅ Avatar updated for user {user_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error updating avatar: {e}")
        return False


def add_custom_link(user_id, title, url):
    """إضافة رابط مخصص (كتابة - supabase_admin)"""
    try:
        bio = get_bio_page(user_id)
        custom_links = bio.get('custom_links', []) if bio else []
        custom_links.append({'title': title, 'url': url})
        
        supabase_admin.table('bio_pages').update({
            'custom_links': custom_links,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error adding custom link: {e}")
        return False


def remove_custom_link(user_id, link_index):
    """حذف رابط مخصص (كتابة - supabase_admin)"""
    try:
        bio = get_bio_page(user_id)
        if not bio:
            return False
        custom_links = bio.get('custom_links', [])
        if 0 <= link_index < len(custom_links):
            custom_links.pop(link_index)
            supabase_admin.table('bio_pages').update({
                'custom_links': custom_links,
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error removing custom link: {e}")
        return False


# ========== دوال لوحة تحكم المدير (قراءة - supabase) ==========

def get_all_users_with_stats(bot_name=None):
    """جلب جميع المستخدمين مع إحصائياتهم الكاملة"""
    try:
        if bot_name is None:
            bot_name = os.environ.get('BOT_NAME', 'social_analyzer')
        
        usage_response = supabase.table('bot_usage').select('user_id').eq('bot_name', bot_name).execute()
        user_ids = [u['user_id'] for u in usage_response.data] if usage_response.data else []
        
        if not user_ids:
            return []
        
        users_response = supabase.table('users').select('*').in_('user_id', user_ids).order('user_id', desc=False).execute()
        users = users_response.data if users_response.data else []
        
        all_usage = {}
        for user_id in user_ids:
            usage_resp = supabase.table('bot_usage').select('*').eq('user_id', user_id).eq('bot_name', bot_name).execute()
            if usage_resp.data:
                all_usage[user_id] = usage_resp.data[0]
        
        bio_response = supabase.table('bio_pages').select('user_id, page_url, views_count').in_('user_id', user_ids).execute()
        bio_pages = {b['user_id']: b for b in bio_response.data} if bio_response.data else {}
        
        result = []
        for user in users:
            usage = all_usage.get(user['user_id'], {})
            bio = bio_pages.get(user['user_id'], {})
            
            result.append({
                'user_id': user['user_id'],
                'first_name': user.get('first_name', ''),
                'username': user.get('username', ''),
                'status': user.get('status', 'free'),
                'premium_until': user.get('premium_until'),
                'created_at': user.get('created_at'),
                'total_uses': usage.get('total_uses', 0),
                'daily_uses': usage.get('daily_uses', 0),
                'bio_page_url': bio.get('page_url'),
                'bio_views': bio.get('views_count', 0),
                'platform_usage': {
                    'youtube': usage.get('youtube_uses', 0),
                    'instagram': usage.get('instagram_uses', 0),
                    'tiktok': usage.get('tiktok_uses', 0),
                    'facebook': usage.get('facebook_uses', 0)
                }
            })
        
        return result
    except Exception as e:
        logger.error(f"Error in get_all_users_with_stats: {e}")
        return []


def get_global_stats(bot_name=None):
    """جلب إحصائيات عامة للوحة التحكم"""
    try:
        if bot_name is None:
            bot_name = os.environ.get('BOT_NAME', 'social_analyzer')
        
        usage_response = supabase.table('bot_usage').select('*').eq('bot_name', bot_name).execute()
        user_ids = [u['user_id'] for u in usage_response.data] if usage_response.data else []
        
        if not user_ids:
            return {
                'total_users': 0,
                'premium_users': 0,
                'free_users': 0,
                'total_uses': 0,
                'total_daily_uses': 0,
                'total_bio_pages': 0,
                'total_bio_views': 0,
                'platform_stats': {'youtube': 0, 'instagram': 0, 'tiktok': 0, 'facebook': 0},
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        users_response = supabase.table('users').select('status').in_('user_id', user_ids).execute()
        users = users_response.data if users_response.data else []
        total_users = len(users)
        premium_users = len([u for u in users if u.get('status') == 'premium'])
        free_users = total_users - premium_users
        
        total_uses = sum([u.get('total_uses', 0) for u in usage_response.data]) if usage_response.data else 0
        total_daily = sum([u.get('daily_uses', 0) for u in usage_response.data]) if usage_response.data else 0
        
        bio_response = supabase.table('bio_pages').select('views_count').in_('user_id', user_ids).execute()
        total_bio_pages = len(bio_response.data) if bio_response.data else 0
        total_bio_views = sum([b.get('views_count', 0) for b in bio_response.data]) if bio_response.data else 0
        
        platform_stats = {'youtube': 0, 'instagram': 0, 'tiktok': 0, 'facebook': 0}
        for u in usage_response.data:
            platform_stats['youtube'] += u.get('youtube_uses', 0)
            platform_stats['instagram'] += u.get('instagram_uses', 0)
            platform_stats['tiktok'] += u.get('tiktok_uses', 0)
            platform_stats['facebook'] += u.get('facebook_uses', 0)
        
        return {
            'total_users': total_users,
            'premium_users': premium_users,
            'free_users': free_users,
            'total_uses': total_uses,
            'total_daily_uses': total_daily,
            'total_bio_pages': total_bio_pages,
            'total_bio_views': total_bio_views,
            'platform_stats': platform_stats,
            'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        logger.error(f"Error in get_global_stats: {e}")
        return {
            'total_users': 0,
            'premium_users': 0,
            'free_users': 0,
            'total_uses': 0,
            'total_daily_uses': 0,
            'total_bio_pages': 0,
            'total_bio_views': 0,
            'platform_stats': {'youtube': 0, 'instagram': 0, 'tiktok': 0, 'facebook': 0},
            'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }


def upgrade_user_to_premium(user_id, duration_days=365):
    """ترقية مستخدم إلى خطة مميزة"""
    try:
        premium_until = (datetime.now() + timedelta(days=duration_days)).strftime('%Y-%m-%d')
        result = supabase.table('users').update({
            'status': 'premium',
            'premium_until': premium_until,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        
        if result.data:
            logger.info(f"✅ User {user_id} upgraded to premium until {premium_until}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error upgrading user {user_id}: {e}")
        return False


def downgrade_user_to_free(user_id):
    """خفض مستخدم إلى خطة مجانية"""
    try:
        result = supabase.table('users').update({
            'status': 'free',
            'premium_until': None,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        
        if result.data:
            logger.info(f"✅ User {user_id} downgraded to free")
            return True
        return False
    except Exception as e:
        logger.error(f"Error downgrading user {user_id}: {e}")
        return False
