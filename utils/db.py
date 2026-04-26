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
    """الحصول على استخدامات المستخدم من جدول users"""
    try:
        response = supabase.table('users').select(
            'daily_uses, total_uses, youtube_uses, instagram_uses, tiktok_uses, facebook_uses, last_use_date'
        ).eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting user usage: {e}")
        return None


def increment_usage(user_id, platform, analysis_results=None):
    """زيادة عدد استخدامات المستخدم حسب المنصة (مع حفظ سجل التحليل)"""
    try:
        user = get_user_info(user_id)
        if not user:
            return False
        
        username = user.get('username', '')
        first_name = user.get('first_name', '')
        today = date.today().isoformat()
        
        # جلب الاستخدامات الحالية من جدول users
        usage_response = supabase.table('users').select(
            'daily_uses, total_uses, youtube_uses, instagram_uses, tiktok_uses, facebook_uses, last_use_date'
        ).eq('user_id', user_id).execute()
        usage = usage_response.data[0] if usage_response.data else None
        
        platform_column_map = {
            'youtube': 'youtube_uses',
            'instagram': 'instagram_uses',
            'tiktok': 'tiktok_uses',
            'facebook': 'facebook_uses'
        }
        platform_column = platform_column_map.get(platform, 'youtube_uses')
        
        # إعادة تعيين daily_uses إذا كان اليوم مختلفاً (للمجانيين فقط)
        if usage and usage.get('last_use_date') != today:
            if user['status'] == 'free':
                supabase.table('users').update({
                    'daily_uses': 0,
                    'last_use_date': today
                }).eq('user_id', user_id).execute()
                # إعادة جلب البيانات بعد التحديث
                usage_response = supabase.table('users').select(
                    'daily_uses, total_uses, youtube_uses, instagram_uses, tiktok_uses, facebook_uses, last_use_date'
                ).eq('user_id', user_id).execute()
                usage = usage_response.data[0] if usage_response.data else None
        
        # الحصول على القيم الحالية
        current_platform_uses = usage.get(platform_column, 0) if usage else 0
        current_daily_uses = usage.get('daily_uses', 0) if usage else 0
        current_total_uses = usage.get('total_uses', 0) if usage else 0
        
        # حساب القيم الجديدة (نزيد daily_uses للجميع)
        new_platform_uses = current_platform_uses + 1
        new_daily_uses = current_daily_uses + 1  # ✅ تغيير: نزيد للجميع
        new_total_uses = current_total_uses + 1
        
        # تحديث جدول users (نحدث daily_uses و last_use_date للجميع)
        update_data = {
            'total_uses': new_total_uses,
            'updated_at': datetime.now().isoformat(),
            platform_column: new_platform_uses,
            'daily_uses': new_daily_uses,
            'last_use_date': today
        }
        
        supabase.table('users').update(update_data).eq('user_id', user_id).execute()
        
        # ========== حفظ سجل التحليل مع تحويل الأرقام ==========
        if analysis_results:
            def parse_number(value):
                if value is None:
                    return None
                if isinstance(value, (int, float)):
                    return int(value)
                if not isinstance(value, str):
                    return None
                try:
                    value = value.upper().strip()
                    if 'M' in value:
                        return int(float(value.replace('M', '')) * 1_000_000)
                    elif 'K' in value:
                        return int(float(value.replace('K', '')) * 1_000)
                    else:
                        return int(float(value))
                except (ValueError, TypeError):
                    return None
            
            subscribers_raw = analysis_results.get('subscribers')
            subscribers_clean = parse_number(subscribers_raw)
            
            total_posts_raw = analysis_results.get('total_posts')
            total_posts_clean = parse_number(total_posts_raw)
            
            supabase.table('analysis_history').insert({
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'platform': platform,
                'analysis_date': datetime.now().isoformat(),
                'account_name': analysis_results.get('account_name'),
                'subscribers': subscribers_clean,
                'total_posts': total_posts_clean,
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
    
    # التحقق من انتهاء الاشتراك المميز
    if user['status'] == 'premium' and user.get('premium_until'):
        if datetime.strptime(user['premium_until'], '%Y-%m-%d').date() < date.today():
            supabase.table('users').update({'status': 'free', 'premium_until': None}).eq('user_id', user_id).execute()
            user['status'] = 'free'
    
    if user['status'] == 'premium':
        return True, 0
    
    # للمستخدمين المجانيين - جلب daily_uses من جدول users مباشرة
    try:
        response = supabase.table('users').select('daily_uses').eq('user_id', user_id).execute()
        daily_uses = response.data[0]['daily_uses'] if response.data else 0
        
        if daily_uses >= FREE_LIMIT:
            return False, daily_uses
        return True, daily_uses
    except Exception as e:
        logger.error(f"Error in can_analyze: {e}")
        return True, 0


def get_remaining_analyses(user_id):
    """الحصول على عدد التحليلات المتبقية للمستخدم"""
    user = get_user_info(user_id)
    if not user:
        return 0
    
    if user['status'] == 'premium':
        return -1
    
    try:
        response = supabase.table('users').select('daily_uses').eq('user_id', user_id).execute()
        current_uses = response.data[0]['daily_uses'] if response.data else 0
        remaining = FREE_LIMIT - current_uses
        return max(0, remaining)
    except Exception as e:
        logger.error(f"Error in get_remaining_analyses: {e}")
        return FREE_LIMIT


def get_total_analyses(user_id):
    """الحصول على إجمالي تحليلات المستخدم"""
    try:
        response = supabase.table('users').select('total_uses').eq('user_id', user_id).execute()
        return response.data[0]['total_uses'] if response.data else 0
    except Exception as e:
        logger.error(f"Error in get_total_analyses: {e}")
        return 0


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
    """التحقق مما إذا كان المستخدم يمكنه استخدام توصيات Gemini (شهرياً)"""
    try:
        user = get_user_info(user_id)
        
        # جلب الحد المسموح حسب نوع المستخدم
        if user['status'] == 'free':
            monthly_limit = int(get_bot_setting('gemini_free_limit', '0'))
            if monthly_limit == 0:
                return False, 0, "💎 هذه الميزة متاحة فقط للمستخدمين المميزين!"
        else:
            monthly_limit = get_user_gemini_limit(user_id)
        
        usage = get_gemini_usage(user_id)
        today = date.today()
        current_month = today.strftime('%Y-%m')
        
        if usage and usage.get('last_use_month') != current_month:
            supabase.table('gemini_usage').update({
                'monthly_recommendations': 0,
                'last_use_month': current_month
            }).eq('user_id', user_id).execute()
            monthly_uses = 0
        elif usage:
            monthly_uses = usage.get('monthly_recommendations', 0)
        else:
            supabase.table('gemini_usage').insert({
                'user_id': user_id,
                'monthly_recommendations': 0,
                'total_recommendations': 0,
                'last_use_month': current_month
            }).execute()
            monthly_uses = 0
        
        if monthly_uses >= monthly_limit:
            return False, monthly_limit, f"⚠️ لقد وصلت للحد الشهري لاستخدام التوصيات!\n\n📊 الحد المسموح: {monthly_limit} توصية شهرياً\n📅 سيتم تجديده في الشهر القادم"
        
        remaining = monthly_limit - monthly_uses
        return True, remaining, None
        
    except Exception as e:
        logger.error(f"Error in can_use_gemini: {e}")
        return False, 0, "❌ حدث خطأ، يرجى المحاولة لاحقاً"


def increment_gemini_usage(user_id):
    """زيادة عدد استخدامات Gemini للمستخدم (شهرياً)"""
    try:
        usage = get_gemini_usage(user_id)
        today = date.today()
        current_month = today.strftime('%Y-%m')
        
        if usage:
            if usage.get('last_use_month') != current_month:
                supabase.table('gemini_usage').update({
                    'monthly_recommendations': 1,
                    'total_recommendations': usage.get('total_recommendations', 0) + 1,
                    'last_use_month': current_month,
                    'updated_at': datetime.now().isoformat()
                }).eq('user_id', user_id).execute()
            else:
                supabase.table('gemini_usage').update({
                    'monthly_recommendations': usage.get('monthly_recommendations', 0) + 1,
                    'total_recommendations': usage.get('total_recommendations', 0) + 1,
                    'updated_at': datetime.now().isoformat()
                }).eq('user_id', user_id).execute()
        else:
            supabase.table('gemini_usage').insert({
                'user_id': user_id,
                'monthly_recommendations': 1,
                'total_recommendations': 1,
                'last_use_month': current_month
            }).execute()
        
        return True
    except Exception as e:
        logger.error(f"Error incrementing gemini usage: {e}")
        return False

# ========== دوال تحليلات الذكاء الاصطناعي (AI Analytics) ==========

def save_first_analysis(user_id, platform, account_identifier, account_name, analysis_data):
    """حفظ أول تحليل للحساب (يتم مرة واحدة فقط)"""
    try:
        # التحقق من وجود تحليل أول مسبقاً
        existing = supabase.table('analysis_history').select('id').eq('user_id', user_id)\
            .eq('analyzed_user_id', account_identifier).eq('platform', platform)\
            .eq('analysis_type', 'first').execute()
        
        if existing.data:
            logger.info(f"First analysis already exists for user {user_id}, account {account_identifier}")
            return False
        
        # حفظ التحليل الأول مع جميع الأعمدة
        data = {
            'user_id': user_id,
            'analyzed_user_id': account_identifier,
            'analyzed_username': account_identifier.replace('@', ''),
            'platform': platform,
            'analysis_type': 'first',
            'account_name': analysis_data.get('account_name', ''),
            # إحصائيات عامة
            'subscribers': analysis_data.get('subscribers', 0),
            'followers': analysis_data.get('followers', 0),
            'following': analysis_data.get('following', 0),
            'total_views': analysis_data.get('total_views', 0),
            'total_posts': analysis_data.get('total_posts', 0),
            'total_videos': analysis_data.get('total_videos', 0),
            'total_likes': analysis_data.get('total_likes', 0),
            'total_comments': analysis_data.get('total_comments', 0),
            'total_shares': analysis_data.get('total_shares', 0),
            # نسب ومتوسطات
            'avg_views_per_post': analysis_data.get('avg_views_per_post', 0),
            'avg_likes_per_post': analysis_data.get('avg_likes_per_post', 0),
            'avg_comments_per_post': analysis_data.get('avg_comments_per_post', 0),
            'engagement_rate': analysis_data.get('engagement_rate', 0),
            # تحليل الفيديوهات
            'avg_video_duration': analysis_data.get('avg_video_duration', 0),
            'best_video_length': analysis_data.get('best_video_length', 0),
            'best_video_category': analysis_data.get('best_video_category'),
            # تحليل التوقيت
            'best_posting_day': analysis_data.get('best_posting_day'),
            'best_posting_hour': analysis_data.get('best_posting_hour'),
            'avg_posts_per_week': analysis_data.get('avg_posts_per_week'),
            # تحليل الجمهور
            'audience_growth_rate': analysis_data.get('audience_growth_rate'),
            'retention_rate': analysis_data.get('retention_rate'),
            'peak_activity_hour': analysis_data.get('peak_activity_hour'),
            # بيانات JSON
            'top_posts': analysis_data.get('top_posts', []),
            'top_categories': analysis_data.get('top_categories'),
            'hashtags_used': analysis_data.get('hashtags_used'),
            'content_types': analysis_data.get('content_types'),
            'analysis_date': datetime.now().isoformat()
        }
        
        result = supabase.table('analysis_history').insert(data).execute()
        logger.info(f"✅ First analysis saved for user {user_id}, account {account_identifier}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving first analysis: {e}")
        return False


def update_latest_analysis(user_id, platform, account_identifier, account_name, analysis_data):
    """تحديث آخر تحليل للحساب (يتم تحديثه في كل مرة)"""
    try:
        # التحقق من وجود تحليل latest مسبقاً
        existing = supabase.table('analysis_history').select('id').eq('user_id', user_id)\
            .eq('analyzed_user_id', account_identifier).eq('platform', platform)\
            .eq('analysis_type', 'latest').execute()
        
        data = {
            'user_id': user_id,
            'analyzed_user_id': account_identifier,
            'analyzed_username': account_identifier.replace('@', ''),
            'platform': platform,
            'analysis_type': 'latest',
            'account_name': analysis_data.get('account_name', ''),
            # إحصائيات عامة
            'subscribers': analysis_data.get('subscribers', 0),
            'followers': analysis_data.get('followers', 0),
            'following': analysis_data.get('following', 0),
            'total_views': analysis_data.get('total_views', 0),
            'total_posts': analysis_data.get('total_posts', 0),
            'total_videos': analysis_data.get('total_videos', 0),
            'total_likes': analysis_data.get('total_likes', 0),
            'total_comments': analysis_data.get('total_comments', 0),
            'total_shares': analysis_data.get('total_shares', 0),
            # نسب ومتوسطات
            'avg_views_per_post': analysis_data.get('avg_views_per_post', 0),
            'avg_likes_per_post': analysis_data.get('avg_likes_per_post', 0),
            'avg_comments_per_post': analysis_data.get('avg_comments_per_post', 0),
            'engagement_rate': analysis_data.get('engagement_rate', 0),
            # تحليل الفيديوهات
            'avg_video_duration': analysis_data.get('avg_video_duration', 0),
            'best_video_length': analysis_data.get('best_video_length', 0),
            'best_video_category': analysis_data.get('best_video_category'),
            # تحليل التوقيت
            'best_posting_day': analysis_data.get('best_posting_day'),
            'best_posting_hour': analysis_data.get('best_posting_hour'),
            'avg_posts_per_week': analysis_data.get('avg_posts_per_week'),
            # تحليل الجمهور
            'audience_growth_rate': analysis_data.get('audience_growth_rate'),
            'retention_rate': analysis_data.get('retention_rate'),
            'peak_activity_hour': analysis_data.get('peak_activity_hour'),
            # بيانات JSON
            'top_posts': analysis_data.get('top_posts', []),
            'top_categories': analysis_data.get('top_categories'),
            'hashtags_used': analysis_data.get('hashtags_used'),
            'content_types': analysis_data.get('content_types'),
            'analysis_date': datetime.now().isoformat()
        }
        
        if existing.data:
            # تحديث التحليل الموجود
            result = supabase.table('analysis_history').update(data)\
                .eq('user_id', user_id).eq('analyzed_user_id', account_identifier)\
                .eq('platform', platform).eq('analysis_type', 'latest').execute()
            logger.info(f"✅ Latest analysis updated for user {user_id}, account {account_identifier}")
        else:
            # إنشاء تحليل جديد
            result = supabase.table('analysis_history').insert(data).execute()
            logger.info(f"✅ Latest analysis created for user {user_id}, account {account_identifier}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating latest analysis: {e}")
        return False


def get_analyses_for_ai(user_id, platform, account_identifier):
    """
    جلب التحليلات للذكاء الاصطناعي (الأول وآخر 3 تحليلات)
    
    المعاملات:
    - user_id: معرف المستخدم في البوت
    - platform: اسم المنصة
    - account_identifier: معرف الحساب على المنصة
    
    الإرجاع:
    - dict: يحتوي على 'first' (التحليل الأول) و 'latest_analyses' (آخر 3 تحليلات)
    """
    try:
        # جلب التحليل الأول
        first_response = supabase.table('analysis_history').select('*')\
            .eq('user_id', user_id).eq('analyzed_user_id', account_identifier)\
            .eq('platform', platform).eq('analysis_type', 'first').execute()
        
        # جلب آخر 3 تحليلات (بما فيها latest)
        latest_response = supabase.table('analysis_history').select('*')\
            .eq('user_id', user_id).eq('analyzed_user_id', account_identifier)\
            .eq('platform', platform).order('analysis_date', desc=True).limit(3).execute()
        
        return {
            'first': first_response.data[0] if first_response.data else None,
            'latest_analyses': latest_response.data if latest_response.data else []
        }
        
    except Exception as e:
        logger.error(f"Error getting analyses for AI: {e}")
        return {'first': None, 'latest_analyses': []}


def calculate_growth_metrics(first_analysis, latest_analysis):
    """
    حساب مقاييس النمو بين أول تحليل وآخر تحليل
    
    المعاملات:
    - first_analysis: قاموس التحليل الأول
    - latest_analysis: قاموس آخر تحليل
    
    الإرجاع:
    - dict: يحتوي على مقاييس النمو (subscribers_growth, views_growth, percentages, etc.)
    """
    if not first_analysis or not latest_analysis:
        return {}
    
    # استخراج القيم
    subscribers_first = first_analysis.get('subscribers', 0) or 0
    subscribers_latest = latest_analysis.get('subscribers', 0) or 0
    views_first = first_analysis.get('total_views', 0) or 0
    views_latest = latest_analysis.get('total_views', 0) or 0
    posts_first = first_analysis.get('total_posts', 0) or 0
    posts_latest = latest_analysis.get('total_posts', 0) or 0
    
    # حساب النمو
    growth = {
        'subscribers_growth': subscribers_latest - subscribers_first,
        'subscribers_percent': 0,
        'views_growth': views_latest - views_first,
        'views_percent': 0,
        'posts_growth': posts_latest - posts_first,
        'posts_percent': 0,
        'latest_engagement_rate': latest_analysis.get('engagement_rate', 0),
        'analysis_period_days': 0
    }
    
    # حساب النسب المئوية
    if subscribers_first > 0:
        growth['subscribers_percent'] = round((subscribers_latest - subscribers_first) / subscribers_first * 100, 2)
    
    if views_first > 0:
        growth['views_percent'] = round((views_latest - views_first) / views_first * 100, 2)
    
    if posts_first > 0:
        growth['posts_percent'] = round((posts_latest - posts_first) / posts_first * 100, 2)
    
    # حساب الفترة الزمنية بين التحليلات (بالأيام)
    try:
        date_first = datetime.fromisoformat(first_analysis.get('analysis_date', '').replace('Z', '+00:00'))
        date_latest = datetime.fromisoformat(latest_analysis.get('analysis_date', '').replace('Z', '+00:00'))
        growth['analysis_period_days'] = (date_latest - date_first).days
    except:
        pass
    
    return growth

# ========== دوال تحليلات الذكاء الاصطناعي (AI Analytics) ==========
# ... دوال save_first_analysis, update_latest_analysis, etc. ...


# ========== دوال حفظ التوصيات (Recommendations History) ==========
# 👇 أضف الكود هنا 👇

def save_recommendation(user_id, platform, account_identifier, recommendation_text, key_points=None):
    """حفظ توصية الذكاء الاصطناعي في قاعدة البيانات"""
    try:
        summary = recommendation_text[:500] if len(recommendation_text) > 500 else recommendation_text
        
        data = {
            'user_id': user_id,
            'platform': platform,
            'account_identifier': account_identifier,
            'recommendation_text': recommendation_text,
            'recommendation_summary': summary,
            'key_points': key_points or [],
            'created_at': datetime.now().isoformat()
        }
        
        result = supabase.table('recommendations_history').insert(data).execute()
        logger.info(f"✅ Recommendation saved for user {user_id}")
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error saving recommendation: {e}")
        return None


def get_previous_recommendations(user_id, platform, account_identifier, limit=3):
    """جلب التوصيات السابقة للمقارنة"""
    try:
        response = supabase.table('recommendations_history').select('*')\
            .eq('user_id', user_id).eq('platform', platform)\
            .eq('account_identifier', account_identifier)\
            .order('created_at', desc=True).limit(limit).execute()
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error getting previous recommendations: {e}")
        return []


def update_recommendation_feedback(user_id, recommendation_id, implemented, feedback, impact_score=None):
    """تحديث حالة التوصية (هل نفذها المستخدم؟)"""
    try:
        data = {
            'implemented': implemented,
            'feedback': feedback,
            'updated_at': datetime.now().isoformat()
        }
        if impact_score:
            data['impact_score'] = impact_score
        
        result = supabase.table('recommendations_history').update(data)\
            .eq('id', recommendation_id).eq('user_id', user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating recommendation feedback: {e}")
        return False

# =================================================================================
# القسم: دوال الأسعار المتغيرة والإعدادات (Dynamic Settings)
# =================================================================================

def get_bot_setting(setting_key, default_value=None):
    """الحصول على قيمة إعداد معين من جدول bot_settings_social"""
    try:
        response = supabase.table('bot_settings_social').select('setting_value').eq('setting_key', setting_key).execute()
        if response.data:
            return response.data[0]['setting_value']
        return default_value
    except Exception as e:
        logger.error(f"Error getting setting {setting_key}: {e}")
        return default_value


def update_bot_setting(setting_key, setting_value):
    """تحديث قيمة إعداد في جدول bot_settings_social"""
    try:
        supabase.table('bot_settings_social').upsert({
            'setting_key': setting_key,
            'setting_value': setting_value,
            'updated_at': datetime.now().isoformat()
        }, on_conflict='setting_key').execute()
        return True
    except Exception as e:
        logger.error(f"Error updating setting {setting_key}: {e}")
        return False

def get_all_prices():
    """جلب جميع الأسعار والإعدادات من جدول bot_settings_social"""
    try:
        response = supabase.table('bot_settings_social').select('setting_key, setting_value').execute()
        
        # تحويل النتيجة إلى قاموس
        settings = {row['setting_key']: row['setting_value'] for row in (response.data or [])}
        
        # القيم الافتراضية إذا لم تكن موجودة
        return {
            'price_monthly': int(settings.get('price_monthly', 10)),
            'price_half_yearly': int(settings.get('price_half_yearly', 30)),
            'price_yearly': int(settings.get('price_yearly', 48)),
            'price_lifetime': int(settings.get('price_lifetime', 100)),
            'duration_monthly': int(settings.get('duration_monthly', 30)),
            'duration_half_yearly': int(settings.get('duration_half_yearly', 180)),
            'duration_yearly': int(settings.get('duration_yearly', 365)),
            'duration_lifetime': int(settings.get('duration_lifetime', 36500)),
            'free_limit': int(settings.get('free_limit', 2)),
            'premium_limit': int(settings.get('premium_limit', -1)),
            'gemini_monthly_limit': int(settings.get('gemini_monthly_limit', 20)),
            'gemini_free_limit': int(settings.get('gemini_free_limit', 0)),
            'promo_active': settings.get('promo_active', 'false') == 'true',
            'promo_half_yearly': int(settings.get('promo_half_yearly', 25)),
            'promo_yearly': int(settings.get('promo_yearly', 40)),
            'promo_end_date': settings.get('promo_end_date', ''),
            'payment_number': settings.get('payment_number', '772130931'),
            'developer_link': settings.get('developer_link', 'https://t.me/E_Alshabany'),
            'bot_link': settings.get('bot_link', 'https://t.me/Social_Media_tools_bot')
        }
    except Exception as e:
        logger.error(f"Error getting all settings: {e}")
        return {}




# =================================================================================
# القسم: دوال الاشتراكات المتقدمة (Subscriptions)
# =================================================================================

def create_subscription(user_id, plan_id, duration_days, price, payment_method=None):
    """إنشاء اشتراك جديد للمستخدم"""
    try:
        start_date = date.today()
        end_date = start_date + timedelta(days=duration_days)
        
        # جلب اسم الخطة
        plan_response = supabase.table('subscription_plans_social').select('name').eq('id', plan_id).execute()
        plan_name = plan_response.data[0]['name'] if plan_response.data else 'unknown'
        
        # إنشاء الاشتراك
        subscription = {
            'user_id': user_id,
            'plan_id': plan_id,
            'status': 'active',
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'payment_amount': price,
            'payment_method': payment_method,
            'created_at': datetime.now().isoformat()
        }
        
        response = supabase.table('user_subscriptions_social').insert(subscription).execute()
        
        if response.data:
            subscription_id = response.data[0]['id']
            
            # تحديث حالة المستخدم
            supabase.table('users').update({
                'status': 'premium',
                'premium_until': end_date.isoformat(),
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', user_id).execute()
            
            logger.info(f"✅ Subscription created for user {user_id}: {plan_name} until {end_date}")
            return True, end_date, plan_name
        return False, None, None
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        return False, None, None


def get_user_active_subscription(user_id):
    """الحصول على الاشتراك النشط للمستخدم"""
    try:
        today = date.today().isoformat()
        response = supabase.table('user_subscriptions_social').select('*, subscription_plans_social(*)').eq('user_id', user_id).eq('status', 'active').gte('end_date', today).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error getting user subscription: {e}")
        return None


def get_subscription_stats():
    """إحصائيات خطط الاشتراك"""
    try:
        response = supabase.table('user_subscriptions_social').select('*, subscription_plans_social(name)').eq('status', 'active').execute()
        
        stats = {
            'half_yearly': 0,
            'yearly': 0,
            'lifetime': 0,
            'monthly': 0,
            'total': 0
        }
        
        for sub in (response.data or []):
            plan_name = sub.get('subscription_plans_social', {}).get('name', '')
            if plan_name == 'half_yearly':
                stats['half_yearly'] += 1
            elif plan_name == 'yearly':
                stats['yearly'] += 1
            elif plan_name == 'lifetime':
                stats['lifetime'] += 1
            elif plan_name == 'monthly':
                stats['monthly'] += 1
            stats['total'] += 1
        
        return stats
    except Exception as e:
        logger.error(f"Error getting subscription stats: {e}")
        return {'half_yearly': 0, 'yearly': 0, 'lifetime': 0, 'monthly': 0, 'total': 0}


# =================================================================================
# القسم: دوال الإشعارات (Notifications)
# =================================================================================

def log_notification(notification_type, target_audience, target_user_id, message):
    """تسجيل إشعار في جدول notification_log_social"""
    try:
        log_data = {
            'notification_type': notification_type,
            'target_audience': target_audience,
            'target_user_id': target_user_id,
            'message': message,
            'sent_at': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat()
        }
        response = supabase.table('notification_log_social').insert(log_data).execute()
        return response.data[0]['id'] if response.data else None
    except Exception as e:
        logger.error(f"Error logging notification: {e}")
        return None


def log_notification_delivery(notification_id, user_id, status='sent'):
    """تسجيل إرسال إشعار لكل مستخدم"""
    try:
        delivery_data = {
            'notification_id': notification_id,
            'user_id': user_id,
            'status': status,
            'delivered_at': datetime.now().isoformat()
        }
        supabase.table('notification_delivery_social').insert(delivery_data).execute()
        return True
    except Exception as e:
        logger.error(f"Error logging notification delivery: {e}")
        return False


def get_notifications_history(limit=100):
    """جلب سجل الإشعارات"""
    try:
        response = supabase.table('notification_log_social').select('*').order('sent_at', desc=True).limit(limit).execute()
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error getting notifications history: {e}")
        return []
# ========== دوال صفحة البايو (كتابة - supabase_admin) ==========
# دوال صفحة البايو تبدأ من هنا
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
    """جلب جميع المستخدمين مع إحصائياتهم الكاملة - مع إضافة gemini_limit"""
    try:
        if bot_name is None:
            bot_name = os.environ.get('BOT_NAME', 'social_analyzer')
        
        # جلب المستخدمين الذين لديهم استخدامات لهذا البوت
        usage_response = supabase.table('bot_usage').select('*').eq('bot_name', bot_name).execute()
        
        if not usage_response.data:
            return []
        
        user_ids = [u['user_id'] for u in usage_response.data]
        
        # جلب تفاصيل المستخدمين
        users_response = supabase.table('users').select('*').in_('user_id', user_ids).order('user_id', desc=False).execute()
        users = {u['user_id']: u for u in (users_response.data or [])}
        
        # جلب إحصائيات الاستخدام
        all_usage = {u['user_id']: u for u in usage_response.data}
        
        # جلب صفحات البايو
        bio_response = supabase.table('bio_pages').select('user_id, page_url, views_count').in_('user_id', user_ids).execute()
        bio_pages = {b['user_id']: b for b in (bio_response.data or [])}
        
        # 🆕 جلب حدود Gemini المخصصة
        gemini_response = supabase.table('user_gemini_limits').select('user_id, monthly_limit').in_('user_id', user_ids).execute()
        gemini_limits = {g['user_id']: g['monthly_limit'] for g in (gemini_response.data or [])}
        
        # الحصول على الحد الافتراضي من متغير البيئة
        default_gemini_limit = int(os.environ.get('GEMINI_MONTHLY_LIMIT', '20'))
        
        # جلب الاشتراكات النشطة
        subscriptions_response = supabase.table('user_subscriptions_social').select('user_id, plan_id, status, start_date, end_date').eq('status', 'active').execute()
        active_subs = {s['user_id']: s for s in (subscriptions_response.data or [])}
        
        # جلب أسماء الخطط
        plans_response = supabase.table('subscription_plans_social').select('id, name, name_ar').execute()
        plans = {p['id']: p for p in (plans_response.data or [])}
        
        result = []
        for user_id in user_ids:
            user = users.get(user_id, {})
            usage = all_usage.get(user_id, {})
            bio = bio_pages.get(user_id, {})
            sub = active_subs.get(user_id, {})
            plan = plans.get(sub.get('plan_id'), {}) if sub else {}
            
            # الحصول على gemini_limit (مخصص أو افتراضي)
            gemini_limit = gemini_limits.get(user_id, default_gemini_limit)
            
            # جلب عدد التوصيات المستخدمة هذا الشهر
            current_month = date.today().strftime('%Y-%m')
            gemini_usage_response = supabase.table('gemini_usage').select('monthly_recommendations').eq('user_id', user_id).execute()
            gemini_used = gemini_usage_response.data[0]['monthly_recommendations'] if gemini_usage_response.data else 0
            
            result.append({
                'user_id': user_id,
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
                },
                'subscription_plan': plan.get('name_ar') or plan.get('name', '-'),
                'subscription_start_date': sub.get('start_date', '-'),
                'subscription_end_date': sub.get('end_date', '-'),
                'gemini_limit': gemini_limit,      # 🆕 الحد الشهري للتوصيات
                'gemini_used': gemini_used         # 🆕 عدد التوصيات المستخدمة هذا الشهر
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
# =================================================================================
# القسم: دوال الحدود الشهرية للتوصيات (Gemini Monthly Limits)
# =================================================================================

def get_user_gemini_limit(user_id):
    """الحصول على الحد الشهري للتوصيات لمستخدم معين"""
    try:
        # جلب الحد المخصص للمستخدم (إذا وجد)
        response = supabase.table('user_gemini_limits').select('monthly_limit').eq('user_id', user_id).execute()
        
        if response.data:
            return response.data[0]['monthly_limit']
        
        # إذا لم يوجد حد مخصص، استخدم الحد العام من الإعدادات
        default_limit = int(get_bot_setting('gemini_monthly_limit', '20'))
        return default_limit
        
    except Exception as e:
        logger.error(f"Error getting user gemini limit: {e}")
        return int(get_bot_setting('gemini_monthly_limit', '20'))


def set_user_gemini_limit(user_id, monthly_limit):
    """تعيين حد شهري مخصص للتوصيات لمستخدم معين"""
    try:
        result = supabase.table('user_gemini_limits').upsert({
            'user_id': user_id,
            'monthly_limit': monthly_limit,
            'updated_at': datetime.now().isoformat()
        }, on_conflict='user_id').execute()
        
        logger.info(f"✅ User {user_id} gemini limit set to {monthly_limit}")
        return True
    except Exception as e:
        logger.error(f"Error setting user gemini limit: {e}")
        return False


def get_all_gemini_limits():
    """جلب جميع الحدود المخصصة للمستخدمين (للوحة التحكم)"""
    try:
        response = supabase.table('user_gemini_limits').select('*').order('user_id').execute()
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error getting all gemini limits: {e}")
        return []

# ========== دوال الدفع عبر نجوم Telegram ==========

def get_star_price(plan_type):
    """جلب سعر الخطة بالنجوم من bot_settings_social"""
    price_key = f'stars_{plan_type}'
    value = get_bot_setting(price_key, '0')
    return int(value)


def get_star_prices_all():
    """جلب جميع أسعار الخطط بالنجوم"""
    return {
        'monthly': get_star_price('monthly'),
        'half_yearly': get_star_price('half_yearly'),
        'yearly': get_star_price('yearly'),
        'lifetime': get_star_price('lifetime'),
        'extra_recs_small': int(get_bot_setting('stars_extra_recs_small', '50')),
        'extra_recs_medium': int(get_bot_setting('stars_extra_recs_medium', '100')),
        'extra_recs_large': int(get_bot_setting('stars_extra_recs_large', '200')),
        'extra_recs_premium': int(get_bot_setting('stars_extra_recs_premium', '500')),
    }


def is_stars_enabled():
    """التحقق من تفعيل الدفع بالنجوم"""
    return get_bot_setting('stars_enabled', 'true') == 'true'


def get_stars_local_rate():
    """سعر النجم بالريال اليمني"""
    stars_usd_rate = float(get_bot_setting('stars_usd_rate', '0.025'))
    usd_to_rial = 530
    return stars_usd_rate * usd_to_rial


def create_star_invoice_data(user_id, plan_type, extra_recs=0):
    """إنشاء بيانات فاتورة النجوم"""
    import time
    import json
    
    if extra_recs > 0:
        price = get_extra_recs_star_price(extra_recs)
        payload = json.dumps({
            'type': 'extra_recs',
            'user_id': user_id,
            'extra_recs': extra_recs,
            'price': price,
            'timestamp': int(time.time())
        })
        title = f"⭐ {extra_recs} توصية إضافية"
        description = f"زيادة حصة التوصيات الشهرية بمقدار {extra_recs} توصية"
    else:
        price = get_star_price(plan_type)
        payload = json.dumps({
            'type': 'subscription',
            'user_id': user_id,
            'plan_type': plan_type,
            'price': price,
            'timestamp': int(time.time())
        })
        plan_names = {
            'monthly': 'شهري',
            'half_yearly': 'نصف سنوي',
            'yearly': 'سنوي',
            'lifetime': 'مدى الحياة'
        }
        title = f"⭐ اشتراك {plan_names.get(plan_type, plan_type)}"
        description = f"الخطة {plan_names.get(plan_type, plan_type)} من بوت تحليل الحسابات"
    
    return {
        'title': title,
        'description': description,
        'payload': payload,
        'currency': 'XTR',
        'prices': [{'label': f'⭐ {price} نجم', 'amount': price}]
    }


def get_extra_recs_star_price(recs_count):
    """جلب سعر عدد التوصيات الإضافية"""
    if recs_count <= 10:
        return int(get_bot_setting('stars_extra_recs_small', '50'))
    elif recs_count <= 25:
        return int(get_bot_setting('stars_extra_recs_medium', '100'))
    elif recs_count <= 50:
        return int(get_bot_setting('stars_extra_recs_large', '200'))
    else:
        return int(get_bot_setting('stars_extra_recs_premium', '500'))


def activate_extra_recs(user_id, extra_recs):
    """تفعيل التوصيات الإضافية للمستخدم"""
    try:
        # جلب الحد الحالي للمستخدم
        current_limit = get_user_gemini_limit(user_id)
        new_limit = current_limit + extra_recs
        
        # تحديث الحد
        result = set_user_gemini_limit(user_id, new_limit)
        
        if result:
            logger.info(f"✅ User {user_id} got {extra_recs} extra recommendations. New limit: {new_limit}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error activating extra recs: {e}")
        return False
