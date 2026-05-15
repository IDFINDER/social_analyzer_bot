# -*- coding: utf-8 -*-
"""
================================================================================
                       Social Media Analyzer Bot - Flask Server
                                   الإصدار 4.0
================================================================================
اسم الملف: app.py
الوصف: خادم Flask الرئيسي - يدير صفحات البايو، لوحات التحكم، API، المصادقات، والمزيد
المشروع: Social Media Analyzer Bot
المطور: @Alshabany_Ai
التاريخ: 2026
================================================================================
"""

import os
import sys
import logging
import secrets
import requests
import aiohttp
import asyncio
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for, render_template_string
from flask_cors import CORS  # ✅ تفعيل CORS للسماح بطلبات AJAX

# استيراد دوال قاعدة البيانات وأدوات المساعدة
# استيراد دوال قاعدة البيانات
from utils.db import (
    get_bio_page_by_page_url, get_user_info, increment_bio_views, supabase,
    get_bio_page, get_user_social_accounts, save_user_account, delete_user_account,
    create_or_update_bio_page, update_bio_text, update_bio_theme, update_bio_avatar,
    supabase_admin, get_all_prices, get_bot_setting, update_bot_setting,
    get_global_stats, get_all_users_with_stats, upgrade_user_to_premium,
    downgrade_user_to_free, get_subscription_stats, get_notifications_history,
    log_notification, log_notification_delivery, get_user_active_subscription,
    get_user_usage, can_analyze, increment_usage, get_remaining_analyses
)
from utils.helpers import escape_html, verify_token, create_secure_token
from utils.snapchat_auth import save_token
from datetime import datetime, timezone, timedelta
# إعدادات التسجيل (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =================================================================================
# القسم 1: تهيئة التطبيق والمتغيرات الأساسية (SECTION 1: INIT & CONFIG)
# =================================================================================

app = Flask(__name__)
CORS(app)  # ✅ السماح بطلبات AJAX من أي مصدر (حل لمشكلة CORS)

PORT = int(os.environ.get('PORT', 10000))
FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '5'))
RENDER_URL = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
TIKTOK_REDIRECT_URI = "https://social-analyzer-flask.onrender.com/callback/tiktok"
BOT_NAME = os.environ.get('BOT_NAME', 'social_analyzer')

# إعدادات المصادقة للوحة التحكم
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin@123#Secure!')
SECRET_KEY = os.environ.get('SECRET_KEY', 'dGhpcyBpcyBhIHZlcnkgc2VjcmV0IGtleQ==')
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(hours=24)

ADMIN_USER_IDS = os.environ.get('ADMIN_USER_IDS', '7850462368').split(',')
ADMIN_USER_IDS = [int(x.strip()) for x in ADMIN_USER_IDS if x.strip().isdigit()]
BASIC_AUTH_PASSWORD = os.environ.get('BASIC_AUTH_PASSWORD', 'Admin@123#Secure!')

# =================================================================================
# القسم 2: ديكوراتور التحقق من التوكن (SECTION 2: TOKEN DECORATOR)
# =================================================================================

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # 🟢 طباعة جميع الهيدرات للتحقق
        print("=" * 50)
        print("HEADERS:", dict(request.headers))
        print("AUTH HEADER:", request.headers.get('Authorization'))
        print("ARGS:", request.args)
        print("=" * 50)
        
        token = None
        
        # 1. جلب التوكن من Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header:
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
            else:
                token = auth_header
        
        # 2. إذا لم يجد، جرب من query parameters
        if not token:
            token = request.args.get('token')
        
        # 3. ✅ إذا لم يجد، جرب من JSON body (جديد!)
        if not token and request.is_json:
            try:
                data = request.get_json(silent=True)
                if data:
                    token = data.get('token')
                    print(f"🔍 Token from JSON body: {token[:30] if token else 'None'}...")
            except:
                pass
        
        if not token:
            print("❌ No token found!")
            return jsonify({'success': False, 'error': 'Token missing'}), 401
        
        # التحقق من التوكن
        user_id = verify_token(token)
        print(f"🔍 Token: {token[:30]}...")
        print(f"👤 Verified user_id: {user_id}")
        
        if not user_id:
            return jsonify({'success': False, 'error': 'Invalid token'}), 401
        
        return f(user_id, *args, **kwargs)
    return decorated
# =================================================================================
# القسم 3: رؤوس الأمان (Security Headers)
# =================================================================================

@app.after_request
def set_security_headers(resp):
    """إضافة رؤوس أمان لمنع تحذيرات المتصفح"""
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
    resp.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://telegram.org https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://use.fontawesome.com; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com https://use.fontawesome.com; "
        "img-src 'self' data: https:;"
    )
    return resp

# =================================================================================
# القسم 4: دوال المصادقة المساعدة (Admin Auth)
# =================================================================================

def login_required(f):
    """طبقة أمان: التحقق من جلسة المدير"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# =================================================================================
# القسم 5: صفحات عامة (سياسة الخصوصية، robots.txt، شروط الخدمة)
# =================================================================================

@app.route('/privacy')
def privacy_policy():
    try:
        return render_template('privacy.html')
    except Exception as e:
        logger.error(f"Error in privacy page: {e}")
        return "Privacy policy page", 200

@app.route('/robots.txt')
def robots_txt():
    try:
        return send_from_directory('static', 'robots.txt')
    except Exception as e:
        return "User-agent: *\nAllow: /", 200

@app.route('/sitemap.xml')
def sitemap():
    try:
        return send_from_directory('static', 'sitemap.xml')
    except Exception as e:
        return "Sitemap not available", 404

@app.route('/terms')
def terms_of_service():
    try:
        return render_template('terms.html')
    except Exception as e:
        return "Terms of Service page", 200
# =================================================================================
@app.route('/tiktokw9Ukfj91mI3iM5jQUAxlKiItQbyu9i8j.txt')
def serve_tiktok_verification():
    return send_from_directory('static/tiktok', 'tiktokw9Ukfj91mI3iM5jQUAxlKiItQbyu9i8j.txt')
# =================================================================================
# TikTok domain verification for the new app
@app.route('/tiktokwlX4EbdbLSiAmI4QADbFjxTG1za9a4ZA.txt')
def serve_tiktok_verification_new():
    return send_from_directory('static/tiktok', 'tiktokwlX4EbdbLSiAmI4QADbFjxTG1za9a4ZA.txt')
# =================================================================================
# TikTok Domain Verification (Static Route)
@app.route('/.well-known/tiktok-display-url-verification')
def tiktok_domain_verification():
    # يجب أن يكون المحتوى مطابقاً تماماً لما هو مطلوب من TikTok
    return "tiktok-developers-site-verification=wlX4EbdbLSiAmI4QADbFjxTG1za9a4ZA", 200, {'Content-Type': 'text/plain'}    
# =================================================================================
# القسم 6: نقاط نهاية فحص الصحة (Health Checks)
# =================================================================================

@app.route('/')
def home():
    """الصفحة الرئيسية (صفحة هبوط للزوار ولتكامل تيك توك وسناب شات)"""
    return render_template('landing.html')

@app.route('/health')
@app.route('/healthcheck')
def health():
    return jsonify({"status": "ok", "service": "flask"}), 200

# =================================================================================
# القسم 7: صفحات WebApp الرئيسية والتبويبات
# =================================================================================

@app.route('/dashboard')
def dashboard():
    """صفحة WebApp الرئيسية (لوحة التحكم)"""
    token = request.args.get('token')
    if not token:
        return "Missing token", 401
    
    # التحقق من صحة التوكن
    user_id = verify_token(token)
    if not user_id:
        return "Invalid token", 401
    
    # جلب معلومات المستخدم
    from utils.db import get_user_info, get_user_social_accounts, get_bot_setting, get_user_gemini_limit, get_gemini_usage, get_remaining_analyses, supabase
    from utils.texts import WebAppTexts
    
    user_info = get_user_info(user_id)
    if not user_info:
        return "User not found", 404
    
    is_premium = user_info.get('status') == 'premium'
    
    # جلب الإعدادات من قاعدة البيانات
    free_limit = int(get_bot_setting('free_limit', '2'))
    gemini_default_limit = int(get_bot_setting('gemini_monthly_limit', '20'))
    
    # حساب التحليلات المتبقية للمستخدم المجاني
    daily_remaining = None
    if not is_premium:
        daily_remaining = get_remaining_analyses(user_id)
    
    # حساب التوصيات المتبقية للمستخدم
    gemini_remaining = None
    gemini_limit = None
    gemini_used = 0
    
    if is_premium:
        gemini_limit = get_user_gemini_limit(user_id)
        try:
            usage = get_gemini_usage(user_id)
            if usage:
                gemini_used = usage.get('monthly_recommendations', 0)
                gemini_remaining = max(0, gemini_limit - gemini_used)
            else:
                gemini_remaining = gemini_limit
        except:
            gemini_remaining = gemini_limit
    else:
        gemini_limit = int(get_bot_setting('gemini_free_limit', '0'))
        gemini_remaining = 0
    
    # التحقق من وجود حساب يوتيوب مسجل
    has_youtube_account = False
    try:
        accounts_response = supabase.table('user_social_accounts').select('id').eq('user_id', user_id).eq('platform', 'youtube').eq('is_active', True).execute()
        has_youtube_account = len(accounts_response.data) > 0
    except:
        pass
    
    # نصوص الواجهة
    webapp_texts = {
        'profile': WebAppTexts.PROFILE_TAB,
        'subscription': WebAppTexts.SUBSCRIPTION_TAB,
        'stats': WebAppTexts.STATS_TAB,
        'recommendations': WebAppTexts.RECOMMENDATIONS_TAB,
        'info': WebAppTexts.INFO_TAB,
        'toast': WebAppTexts.TOAST_MESSAGES
    }
    
    return render_template('dashboard/base.html',
                          token=token,
                          webapp_texts=webapp_texts,
                          user_is_premium=is_premium,
                          user_daily_remaining=daily_remaining,
                          user_gemini_remaining=gemini_remaining,
                          user_gemini_limit=gemini_limit,
                          user_gemini_used=gemini_used,
                          user_free_limit=free_limit,
                          has_youtube_account=has_youtube_account,
                          user_info=user_info)


@app.route('/api/tab/<tab_name>')
def get_tab(tab_name):
    """API لجلب محتوى تبويب معين مع تمرير متغيرات الصلاحيات"""
    token = request.args.get('token')
    if not token:
        return "Missing token", 401
    
    # التحقق من صحة التوكن
    user_id = verify_token(token)
    if not user_id:
        return "Invalid token", 401
    
    # جلب معلومات المستخدم الأساسية للتبويبات
    from utils.db import get_user_info, get_bot_setting, get_user_gemini_limit, get_remaining_analyses, get_gemini_usage
    from utils.texts import WebAppTexts
    
    user_info = get_user_info(user_id)
    if not user_info:
        return "User not found", 404
    
    is_premium = user_info.get('status') == 'premium'
    
    # جلب الإعدادات للتبويبات التي تحتاجها
    free_limit = int(get_bot_setting('free_limit', '2'))
    
    daily_remaining = None
    if not is_premium:
        daily_remaining = get_remaining_analyses(user_id)
    
    gemini_remaining = None
    gemini_limit = None
    if is_premium:
        gemini_limit = get_user_gemini_limit(user_id)
        try:
            usage = get_gemini_usage(user_id)
            gemini_used = usage.get('monthly_recommendations', 0) if usage else 0
            gemini_remaining = max(0, gemini_limit - gemini_used)
        except:
            gemini_remaining = gemini_limit
    else:
        gemini_limit = int(get_bot_setting('gemini_free_limit', '0'))
        gemini_remaining = 0
    
    # خريطة التبويبات (الاسم في الرابط ← اسم الملف)
    tabs_map = {
        'profile': 'dashboard/profile_tab_new.html',
        'subscription': 'dashboard/subscription_tab.html',
        'stats': 'dashboard/stats_tab.html',
        'recommendations': 'dashboard/recommendations_tab.html',
        'info': 'dashboard/info_tab.html'
    }
    
    if tab_name not in tabs_map:
        return "Tab not found", 404
    
    # تمرير المتغيرات إلى التبويب
    return render_template(tabs_map[tab_name],
                          user_is_premium=is_premium,
                          user_daily_remaining=daily_remaining,
                          user_gemini_remaining=gemini_remaining,
                          user_gemini_limit=gemini_limit,
                          user_free_limit=free_limit,
                          webapp_texts=webapp_texts)

# =================================================================================
# القسم 8: صفحة الدفع (Payment Page)
# =================================================================================

@app.route('/payment')
def payment_page():
    try:
        prices = get_all_prices()
        plan = request.args.get('plan', 'half_yearly')
        amount = request.args.get('amount', prices.get('price_half_yearly', 30))
        plan_details = {
            'monthly': {'name': 'شهري', 'price': prices.get('price_monthly', 10)},
            'half_yearly': {'name': 'نصف سنوي', 'price': prices.get('price_half_yearly', 30)},
            'yearly': {'name': 'سنوي', 'price': prices.get('price_yearly', 48)},
            'lifetime': {'name': 'مدى الحياة', 'price': prices.get('price_lifetime', 100)}
        }
        current_plan = plan_details.get(plan, plan_details['half_yearly'])
        return render_template('payment.html', free_limit=FREE_LIMIT, prices=prices, plan=current_plan, selected_plan=plan, amount=amount)
    except Exception as e:
        logger.error(f"Payment page error: {e}")
        return f"Error loading payment page: {e}", 500

# =================================================================================
# القسم 9: صفحات البايو الشخصية (Bio Pages)
# =================================================================================

@app.route('/bio/<page_url>')
def bio_page(page_url):
    try:
        logger.info(f"🔍 Bio page requested: {page_url}")
        bio = get_bio_page_by_page_url(page_url)
        if not bio:
            return "Page not found", 404
        user_info = get_user_info(bio['user_id'])
        if not user_info:
            return "User not found", 404
        increment_bio_views(page_url)
        accounts = bio.get('accounts', {})
        custom_links = bio.get('custom_links', [])
        platform_icons = {
            'youtube': 'https://upload.wikimedia.org/wikipedia/commons/b/b8/YouTube_Logo_2017.svg',
            'instagram': 'https://upload.wikimedia.org/wikipedia/commons/a/a5/Instagram_icon.png',
            'tiktok': 'https://upload.wikimedia.org/wikipedia/commons/0/0a/TikTok_logo.svg',
            'facebook': 'https://upload.wikimedia.org/wikipedia/commons/5/51/Facebook_f_logo_%282019%29.svg'
        }
        platform_names = {'youtube': 'YouTube', 'instagram': 'Instagram', 'tiktok': 'TikTok', 'facebook': 'Facebook'}
        accounts_list = []
        for platform, acc in accounts.items():
            identifier = acc.get('account_identifier', '')
            if identifier:
                if identifier.startswith('@'):
                    identifier = identifier[1:]
                url = f"https://{platform}.com/{identifier}"
                accounts_list.append({'platform': platform, 'name': platform_names.get(platform, platform.capitalize()), 'url': url, 'icon': platform_icons.get(platform, '')})
        custom_links_list = [{'title': link.get('title', 'رابط مخصص'), 'url': link.get('url', '#')} for link in custom_links]
        theme_name = bio.get('theme_name', 'default')
        return render_template('bio_page.html', display_name=bio['display_name'], username=user_info.get('username', ''), bio=bio.get('bio', ''), accounts=accounts_list, custom_links=custom_links_list, avatar_url=bio.get('avatar_url', None), views_count=bio.get('views_count', 0), theme_name=theme_name, user_id=bio['user_id'], is_premium=(user_info.get('status') == 'premium'), RENDER_URL=RENDER_URL)
    except Exception as e:
        logger.error(f"Error in bio_page: {e}")
        return f"Internal error: {e}", 500

# =================================================================================
# القسم 10: API المصادقة مع Snapchat OAuth (نسخة محسنة)
# =================================================================================

@app.route('/snapchat/callback')
def snapchat_callback():
    code = request.args.get('code')
    user_id = request.args.get('state')
    
    # تحسين: التحقق من وجود المتغيرات
    if not code or not user_id:
        logger.error(f"Missing code or user_id: code={code}, user_id={user_id}")
        return "Missing code or user_id", 400
    
    try:
        user_id = int(user_id)
    except ValueError:
        logger.error(f"Invalid user_id: {user_id}")
        return "Invalid user_id", 400
    
    # الحصول على رابط إعادة التوجيه من متغير البيئة أو استخدام الافتراضي
    redirect_uri = os.environ.get('SNAPCHAT_REDIRECT_URI', 'https://social-analyzer-flask.onrender.com/snapchat/callback')
    
    async def exchange_code():
        try:
            async with aiohttp.ClientSession() as session:
                # تحسين: إضافة timeout
                async with session.post(
                    'https://accounts.snapchat.com/login/oauth2/access_token',
                    data={
                        'grant_type': 'authorization_code',
                        'code': code,
                        'redirect_uri': redirect_uri,
                        'client_id': os.environ.get('SNAPCHAT_CLIENT_ID'),
                        'client_secret': os.environ.get('SNAPCHAT_CLIENT_SECRET')
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Token exchange failed with status {response.status}: {error_text}")
                        return None
        except asyncio.TimeoutError:
            logger.error("Token exchange timeout")
            return None
        except Exception as e:
            logger.error(f"Token exchange exception: {e}")
            return None
    
    channel_details, error = asyncio.run(get_channel_details(channel_clean))
    if not token_data:
        return "Failed to exchange code", 500
    
    # حفظ التوكن
    if not save_token(user_id, token_data):
        logger.error(f"Failed to save token for user {user_id}")
        return "Failed to save token", 500
    
    # إرسال إشعار للمستخدم
    TOKEN = os.environ.get('TELEGRAM_TOKEN')
    if TOKEN:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={
                    'chat_id': user_id,
                    'text': "✅ تم تفعيل تحليل Snapchat بنجاح!\n\n📸 يمكنك الآن استخدام زر 'تحليل سناب شات' لتحليل حسابك.",
                    'parse_mode': 'HTML'
                },
                timeout=5
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")
    
    # صفحة النجاح
    return """
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>تم التفعيل بنجاح - Social Analyzer Bot</title>
        <style>
            *{margin:0;padding:0;box-sizing:border-box;}
            body{
                font-family:'Segoe UI',sans-serif;
                background:linear-gradient(135deg,#667eea,#764ba2);
                min-height:100vh;
                display:flex;
                justify-content:center;
                align-items:center;
                padding:20px;
            }
            .card{
                background:white;
                border-radius:24px;
                padding:40px;
                text-align:center;
                max-width:400px;
                box-shadow:0 20px 40px rgba(0,0,0,0.2);
                animation:fadeInUp 0.5s ease;
            }
            .icon{font-size:64px;margin-bottom:20px;}
            h1{color:#2c3e50;margin-bottom:10px;}
            p{color:#666;line-height:1.6;}
            .btn{
                display:inline-block;
                background:#667eea;
                color:white;
                padding:12px 24px;
                border-radius:30px;
                text-decoration:none;
                margin-top:20px;
                transition:0.3s;
            }
            .btn:hover{
                transform:translateY(-2px);
                background:#5a67d8;
            }
            @keyframes fadeInUp{
                from{opacity:0;transform:translateY(30px);}
                to{opacity:1;transform:translateY(0);}
            }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">✅</div>
            <h1>تم التفعيل بنجاح!</h1>
            <p>يمكنك الآن العودة إلى البوت واستخدام ميزة تحليل Snapchat.</p>
            <a href="https://t.me/Social_Media_tools_bot" class="btn">🚀 العودة إلى البوت</a>
        </div>
        <script>
            setTimeout(function(){
                window.location.href = 'https://t.me/Social_Media_tools_bot';
            }, 5000);
        </script>
    </body>
    </html>
    """

# =================================================================================
# القسم 11: واجهات برمجة التطبيقات العامة (Public APIs)
# =================================================================================

@app.route('/api/save_theme', methods=['POST'])
def save_theme():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        theme_name = data.get('theme_name')
        if not user_id or not theme_name:
            return jsonify({'status': 'error', 'message': 'بيانات ناقصة'}), 400
        valid_themes = ['default', 'dark']
        if theme_name not in valid_themes:
            return jsonify({'status': 'error', 'message': 'قالب غير صالح'}), 400
        result = supabase.table('bio_pages').update({'theme_name': theme_name, 'updated_at': datetime.now().isoformat()}).eq('user_id', user_id).execute()
        if result.data:
            return jsonify({'status': 'ok', 'message': 'تم حفظ الثيم بنجاح'})
        return jsonify({'status': 'error', 'message': 'لم يتم العثور على صفحة البايو'}), 404
    except Exception as e:
        logger.error(f"Error in save_theme: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    from datetime import datetime, date
    from utils.db import get_user_info, get_user_social_accounts, get_user_active_subscription, get_user_usage, get_all_prices
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'Missing token'}), 401
    try:
        user_id = int(token.split(':')[0])
    except:
        return jsonify({'error': 'Invalid token'}), 401
    user_info = get_user_info(user_id)
    if not user_info:
        return jsonify({'error': 'User not found'}), 404
    accounts = get_user_social_accounts(user_id)
    is_premium = user_info.get('status') == 'premium'
    usage = get_user_usage(user_id)
    days_left = 0
    subscription_start_date = None
    subscription_plan_name = None
    subscription_end_date = None
    try:
        from utils.db import supabase
        sub_response = supabase.table('user_subscriptions_social').select('*, subscription_plans_social(name_ar, name)').eq('user_id', user_id).eq('status', 'active').order('created_at', desc=True).limit(1).execute()
        if sub_response.data:
            sub = sub_response.data[0]
            subscription_start_date = sub.get('start_date')
            subscription_end_date = sub.get('end_date')
            if sub.get('subscription_plans_social'):
                subscription_plan_name = sub['subscription_plans_social'].get('name_ar', 'مميز')
            if subscription_end_date:
                try:
                    end_date = datetime.strptime(subscription_end_date, '%Y-%m-%d').date()
                    days_left = max(0, (end_date - date.today()).days)
                except:
                    days_left = 0
    except Exception as e:
        logger.error(f"Error fetching subscription: {e}")
    prices = get_all_prices()
    gemini_uses = 0
    gemini_limit = prices.get('gemini_monthly_limit', 20) if is_premium else prices.get('gemini_free_limit', 0)
    try:
        from utils.db import supabase
        current_month = datetime.now().strftime('%Y-%m')
        gemini_response = supabase.table('gemini_usage').select('monthly_recommendations, total_recommendations, last_use_month').eq('user_id', user_id).execute()
        if gemini_response.data:
            last_use_month = gemini_response.data[0].get('last_use_month', '')
            if last_use_month == current_month:
                gemini_uses = gemini_response.data[0].get('monthly_recommendations', 0)
            else:
                gemini_uses = 0
        else:
            gemini_uses = 0
        logger.info(f"Gemini uses for user {user_id}: {gemini_uses}/{gemini_limit}")
    except Exception as e:
        logger.error(f"Error fetching gemini uses: {e}")
        gemini_uses = 0
    try:
        from utils.db import supabase
        limit_response = supabase.table('user_gemini_limits').select('monthly_limit').eq('user_id', user_id).execute()
        if limit_response.data:
            gemini_limit = limit_response.data[0].get('monthly_limit', gemini_limit)
        logger.info(f"Gemini limit for user {user_id}: {gemini_limit}")
    except Exception as e:
        logger.error(f"Error fetching gemini limit: {e}")
    recommendations = []
    try:
        from utils.db import supabase
        recs_response = supabase.table('recommendations_history').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(20).execute()
        for rec in (recs_response.data or []):
            recommendations.append({
                'id': rec.get('id'), 'platform': rec.get('platform'), 'account_identifier': rec.get('account_identifier'),
                'recommendation_summary': rec.get('recommendation_summary', '')[:300] if rec.get('recommendation_summary') else '',
                'recommendation_text': rec.get('recommendation_text', ''), 'key_points': rec.get('key_points'),
                'implemented': rec.get('implemented', False), 'created_at': rec.get('created_at')
            })
        logger.info(f"Found {len(recommendations)} recommendations for user {user_id}")
    except Exception as e:
        logger.error(f"Error fetching recommendations: {e}")
        recommendations = []
    bio_page = None
    try:
        from utils.db import supabase
        bio_response = supabase.table('bio_pages').select('page_url, views_count, is_enabled').eq('user_id', user_id).eq('is_enabled', True).execute()
        if bio_response.data:
            bio_page = bio_response.data[0]
        logger.info(f"Bio page for user {user_id}: {bio_page}")
    except Exception as e:
        logger.error(f"Error fetching bio page: {e}")
        bio_page = None
    response_data = {
        'is_premium': is_premium,
        'user': {'first_name': user_info.get('first_name'), 'username': user_info.get('username'), 'user_id': user_id,
                 'created_at': user_info.get('created_at'), 'language_code': user_info.get('language_code'),
                 'last_activity': user_info.get('updated_at'), 'photo_url': None},
        'accounts': accounts,
        'stats': {'total_uses': usage.get('total_uses', 0) if usage else 0,
                  'youtube_uses': usage.get('youtube_uses', 0) if usage else 0,
                  'instagram_uses': usage.get('instagram_uses', 0) if usage else 0,
                  'tiktok_uses': usage.get('tiktok_uses', 0) if usage else 0,
                  'facebook_uses': usage.get('facebook_uses', 0) if usage else 0},
        'free_limit': prices.get('free_limit', 2), 'gemini_limit': gemini_limit, 'gemini_uses': gemini_uses,
        'recommendations': recommendations,
        'bio_page': {'page_url': bio_page.get('page_url'), 'views_count': bio_page.get('views_count', 0), 'is_enabled': bio_page.get('is_enabled', False)} if bio_page else None
    }
    if is_premium and subscription_start_date:
        response_data['subscription'] = {'plan': subscription_plan_name or 'مميز', 'start_date': subscription_start_date, 'end_date': subscription_end_date, 'days_left': days_left}
    elif is_premium:
        response_data['subscription'] = {'plan': 'مميز', 'start_date': user_info.get('premium_until'), 'end_date': user_info.get('premium_until'), 'days_left': days_left}
    else:
        response_data['subscription'] = {'plan': 'مجاني', 'start_date': None, 'end_date': None, 'days_left': 0}
    return jsonify(response_data)

@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'status': 'ok', 'message': 'API is working'})

# =================================================================================
# القسم 12: API محمية (Protected APIs) – تتطلب التوكن
# =================================================================================

@app.route('/webapp/api/action', methods=['POST'])
@token_required
def webapp_action(user_id):
    """API لتنفيذ إجراءات المستخدم (تعديل الاسم، إدارة الحسابات، البايو)"""
    data = request.get_json()
    action = data.get('action')
    
    if action == 'update_name':
        new_name = data.get('name')
        if new_name:
            supabase.table('users').update({'first_name': new_name, 'updated_at': datetime.now().isoformat()}).eq('user_id', user_id).execute()
            accounts = get_user_social_accounts(user_id)
            formatted = {p: {'account_identifier': a['account_identifier']} for p, a in accounts.items()}
            create_or_update_bio_page(user_id, new_name, formatted)
            return jsonify({'success': True})
    
    elif action == 'update_bio':
        new_bio = data.get('bio')
        if new_bio is not None:
            update_bio_text(user_id, new_bio)
            return jsonify({'success': True})
    
    elif action == 'update_theme':
        theme = data.get('theme')
        if theme:
            update_bio_theme(user_id, theme)
            return jsonify({'success': True})
    
    elif action == 'add_account' or action == 'save_account':
        platform = data.get('platform')
        identifier = data.get('identifier')
        if platform and identifier:
            save_user_account(user_id, platform, identifier)
            # تحديث صفحة البايو للمستخدمين المميزين
            user_info = get_user_info(user_id)
            if user_info and user_info.get('status') == 'premium':
                accounts = get_user_social_accounts(user_id)
                formatted = {p: {'account_identifier': a['account_identifier']} for p, a in accounts.items()}
                create_or_update_bio_page(user_id, user_info.get('first_name', 'مستخدم'), formatted)
            return jsonify({'success': True})
    
    # 🆕 إضافة هذا القسم الجديد لتعديل الحساب
    elif action == 'update_account':
        platform = data.get('platform')
        identifier = data.get('identifier')
        if platform and identifier:
            # إزالة @ إذا وجدت
            if identifier.startswith('@'):
                identifier = identifier[1:]
            # حذف الحساب القديم وإضافة الجديد
            delete_user_account(user_id, platform)
            save_user_account(user_id, platform, identifier)
            # تحديث صفحة البايو للمستخدمين المميزين
            user_info = get_user_info(user_id)
            if user_info and user_info.get('status') == 'premium':
                accounts = get_user_social_accounts(user_id)
                formatted = {p: {'account_identifier': a['account_identifier']} for p, a in accounts.items()}
                create_or_update_bio_page(user_id, user_info.get('first_name', 'مستخدم'), formatted)
            return jsonify({'success': True})
    
    elif action == 'delete_account':
        platform = data.get('platform')
        if platform:
            delete_user_account(user_id, platform)
            user_info = get_user_info(user_id)
            if user_info and user_info.get('status') == 'premium':
                accounts = get_user_social_accounts(user_id)
                formatted = {p: {'account_identifier': a['account_identifier']} for p, a in accounts.items()}
                create_or_update_bio_page(user_id, user_info.get('first_name', 'مستخدم'), formatted)
            return jsonify({'success': True})
    
    elif action == 'reset_page':
        update_bio_text(user_id, '')
        update_bio_avatar(user_id, None)
        return jsonify({'success': True})
    
    elif action == 'reset_url':
        accounts = get_user_social_accounts(user_id)
        user_info = get_user_info(user_id)
        formatted = {p: {'account_identifier': a['account_identifier']} for p, a in accounts.items()}
        supabase_admin.table('bio_pages').delete().eq('user_id', user_id).execute()
        new_url = create_or_update_bio_page(user_id, user_info.get('first_name', 'مستخدم'), formatted)
        flask_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
        return jsonify({'success': True, 'new_url': f"https://{flask_url}/bio/{new_url}"})
    
    elif action == 'delete_page':
        supabase_admin.table('bio_pages').delete().eq('user_id', user_id).execute()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Unknown action'})

# =================================================================================
# القسم 13: خدمة الملفات الثابتة (Static Files)
# =================================================================================

@app.route('/static/themes/<path:filename>')
def serve_theme(filename):
    return send_from_directory('static/themes', filename)

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

# =================================================================================
# القسم 14: معالجة الأخطاء العامة (Error Handlers)
# =================================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Page not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# =================================================================================
# القسم 15: لوحة تحكم المدير (Admin Dashboard)
# =================================================================================

@app.route('/secure/x7K9mP2/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            session.permanent = True
            return redirect(url_for('admin_dashboard'))
        return render_template_string('''
            <!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="UTF-8"><title>دخول المدير</title><style>
            *{margin:0;padding:0;box-sizing:border-box;}body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;justify-content:center;align-items:center;}
            .login-card{background:white;border-radius:20px;padding:40px;width:100%;max-width:400px;text-align:center;}h1{color:#2c3e50;margin-bottom:10px;}
            .error{color:#e74c3c;margin-bottom:20px;padding:10px;background:#fdecea;border-radius:10px;}input{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:10px;}
            button{width:100%;padding:12px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:10px;cursor:pointer;}</style></head>
            <body><div class="login-card"><h1>🔐 دخول المدير</h1><div class="error">❌ اسم المستخدم أو كلمة المرور غير صحيحة</div>
            <form method="POST"><input type="text" name="username" placeholder="اسم المستخدم" required><input type="password" name="password" placeholder="كلمة المرور" required><button type="submit">دخول</button></form></div></body></html>
        ''', 401)
    return render_template_string('''
        <!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="UTF-8"><title>دخول المدير</title><style>
        *{margin:0;padding:0;box-sizing:border-box;}body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;justify-content:center;align-items:center;}
        .login-card{background:white;border-radius:20px;padding:40px;width:100%;max-width:400px;text-align:center;}h1{color:#2c3e50;}.subtitle{color:#7f8c8d;margin-bottom:30px;}
        input{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:10px;}button{width:100%;padding:12px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:10px;cursor:pointer;}
        .footer{margin-top:30px;font-size:12px;color:#95a5a6;}</style></head>
        <body><div class="login-card"><h1>🔐 لوحة التحكم</h1><div class="subtitle">بوتات الأدوات الاجتماعية</div>
        <form method="POST"><input type="text" name="username" placeholder="اسم المستخدم" required><input type="password" name="password" placeholder="كلمة المرور" required><button type="submit">دخول</button></form><div class="footer">🔒 صفحة مخصصة للمدير فقط</div></div></body></html>
    ''')

@app.route('/secure/x7K9mP2/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    try:
        default_gemini_limit = int(os.environ.get('GEMINI_MONTHLY_LIMIT', '20'))
        users_response = supabase.table('users').select('*').order('user_id', desc=False).execute()
        users_list = []
        for user in (users_response.data or []):
            user_id = user['user_id']
            bio_response = supabase.table('bio_pages').select('page_url, views_count').eq('user_id', user_id).execute()
            bio = bio_response.data[0] if bio_response.data else {}
            subscription = None
            if user.get('status') == 'premium':
                try:
                    sub_response = supabase.table('user_subscriptions_social').select('*, subscription_plans_social(name, name_ar)').eq('user_id', user_id).eq('status', 'active').execute()
                    if sub_response.data:
                        subscription = sub_response.data[0]
                except Exception as e:
                    logger.warning(f"Could not fetch subscription: {e}")
            gemini_limit_response = supabase.table('user_gemini_limits').select('monthly_limit').eq('user_id', user_id).execute()
            gemini_limit = gemini_limit_response.data[0]['monthly_limit'] if gemini_limit_response.data else default_gemini_limit
            current_month = datetime.now().strftime('%Y-%m')
            gemini_used_response = supabase.table('gemini_usage').select('monthly_recommendations').eq('user_id', user_id).eq('last_use_month', current_month).execute()
            gemini_used = gemini_used_response.data[0]['monthly_recommendations'] if gemini_used_response.data else 0
            users_list.append({
                'user_id': user_id, 'first_name': user.get('first_name', ''), 'username': user.get('username', ''),
                'status': user.get('status', 'free'), 'created_at': user.get('created_at', ''),
                'bio_page_url': bio.get('page_url'), 'bio_views': bio.get('views_count', 0),
                'total_usage': {'youtube': user.get('youtube_uses', 0), 'instagram': user.get('instagram_uses', 0), 'tiktok': user.get('tiktok_uses', 0), 'facebook': user.get('facebook_uses', 0)},
                'daily_uses': user.get('daily_uses', 0), 'subscription_plan': subscription.get('subscription_plans_social', {}).get('name_ar', '-') if subscription else '-',
                'subscription_end_date': subscription.get('end_date', '-') if subscription else '-', 'subscription_start_date': subscription.get('start_date', '-') if subscription else '-',
                'gemini_limit': gemini_limit, 'gemini_used': gemini_used
            })
        total_users = len(users_list)
        premium_users = len([u for u in users_list if u['status'] == 'premium'])
        free_users = total_users - premium_users
        total_uses = sum([u.get('total_uses', 0) for u in users_list])
        platform_stats = {
            'youtube': sum([u['total_usage']['youtube'] for u in users_list]),
            'instagram': sum([u['total_usage']['instagram'] for u in users_list]),
            'tiktok': sum([u['total_usage']['tiktok'] for u in users_list]),
            'facebook': sum([u['total_usage']['facebook'] for u in users_list])
        }
        subscription_stats = {'monthly': 0, 'half_yearly': 0, 'yearly': 0, 'lifetime': 0}
        try:
            subs_response = supabase.table('user_subscriptions_social').select('plan_id').eq('status', 'active').execute()
            if subs_response.data:
                for sub in subs_response.data:
                    plan_response = supabase.table('subscription_plans_social').select('name').eq('id', sub['plan_id']).execute()
                    if plan_response.data:
                        plan_name = plan_response.data[0]['name']
                        if plan_name == 'monthly': subscription_stats['monthly'] += 1
                        elif plan_name == 'half_yearly': subscription_stats['half_yearly'] += 1
                        elif plan_name == 'yearly': subscription_stats['yearly'] += 1
                        elif plan_name == 'lifetime': subscription_stats['lifetime'] += 1
        except Exception as e:
            logger.warning(f"Could not fetch subscription stats: {e}")
        stats = {
            'total_users': total_users, 'premium_users': premium_users, 'free_users': free_users, 'total_uses': total_uses,
            'total_bio_pages': len([u for u in users_list if u.get('bio_page_url')]), 'total_bio_views': sum([u.get('bio_views', 0) for u in users_list]),
            'platform_stats': platform_stats, 'subscription_stats': subscription_stats, 'total_gemini_uses': sum([u.get('gemini_used', 0) for u in users_list]),
            'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        return render_template('admin_dashboard.html', users=users_list, stats=stats, free_limit=FREE_LIMIT, RENDER_URL=RENDER_URL)
    except Exception as e:
        logger.error(f"Error in admin_dashboard: {e}")
        return f"حدث خطأ: {e}", 500

# =================================================================================
# القسم 16: إدارة المستخدمين (ترقية / خفض) من لوحة التحكم
# =================================================================================

@app.route('/upgrade-user', methods=['POST'])
@login_required
def upgrade_user():
    user_id = request.form.get('user_id')
    plan_type = request.form.get('plan_type')
    if not user_id or not plan_type:
        return redirect(url_for('admin_dashboard'))
    plan_details = {
        'monthly': {'name': 'شهري', 'name_en': 'monthly', 'days': 30, 'price_key': 'price_monthly'},
        'half_yearly': {'name': 'نصف سنوي', 'name_en': 'half_yearly', 'days': 180, 'price_key': 'price_half_yearly'},
        'yearly': {'name': 'سنوي', 'name_en': 'yearly', 'days': 365, 'price_key': 'price_yearly'},
        'lifetime': {'name': 'مدى الحياة', 'name_en': 'lifetime', 'days': 36500, 'price_key': 'price_lifetime'}
    }
    plan = plan_details.get(plan_type, plan_details['half_yearly'])
    price = int(get_bot_setting(plan['price_key'], '30'))
    start_date = datetime.now().date()
    end_date = start_date + timedelta(days=plan['days'])
    end_date_str = end_date.strftime('%Y-%m-%d')
    try:
        result = supabase.table('users').update({'status': 'premium', 'premium_until': end_date_str, 'updated_at': datetime.now().isoformat()}).eq('user_id', int(user_id)).execute()
        if not result.data:
            return redirect(url_for('admin_dashboard'))
        try:
            plan_response = supabase.table('subscription_plans_social').select('id').eq('name', plan['name_en']).execute()
            plan_id = plan_response.data[0]['id'] if plan_response.data else None
            if plan_id:
                supabase.table('user_subscriptions_social').insert({'user_id': int(user_id), 'plan_id': plan_id, 'status': 'active', 'start_date': start_date.isoformat(), 'end_date': end_date.isoformat(), 'payment_amount': price, 'created_at': datetime.now().isoformat()}).execute()
        except Exception as e:
            logger.error(f"Error creating subscription record: {e}")
        TOKEN = os.environ.get('TELEGRAM_TOKEN')
        message = f"🎉 <b>تم ترقية حسابك بنجاح!</b>\n\n📅 <b>خطتك:</b> {plan['name']}\n💰 <b>المبلغ:</b> {price}$\n⏰ <b>تنتهي في:</b> {end_date_str}\n\n✅ يمكنك الآن الاستمتاع بالمميزات:\n• تحليل غير محدود\n• توصيات الذكاء الاصطناعي\n• صفحة بايو شخصية\n\nشكراً لثقتك! 🙏"
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={'chat_id': user_id, 'text': message, 'parse_mode': 'HTML'}, timeout=5)
        except Exception as e:
            logger.error(f"Error sending upgrade message: {e}")
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        logger.error(f"Error upgrading user: {e}")
        return f"حدث خطأ: {e}", 500

@app.route('/downgrade-user', methods=['POST'])
@login_required
def downgrade_user():
    user_id = request.form.get('user_id')
    if not user_id:
        return redirect(url_for('admin_dashboard'))
    try:
        result = supabase.table('users').update({'status': 'free', 'premium_until': None, 'updated_at': datetime.now().isoformat()}).eq('user_id', int(user_id)).execute()
        if not result.data:
            return redirect(url_for('admin_dashboard'))
        try:
            supabase.table('user_subscriptions_social').update({'status': 'cancelled', 'updated_at': datetime.now().isoformat()}).eq('user_id', int(user_id)).eq('status', 'active').execute()
        except Exception as e:
            logger.error(f"Error updating subscription status: {e}")
        FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '2'))
        TOKEN = os.environ.get('TELEGRAM_TOKEN')
        message = f"📉 <b>تم خفض اشتراكك إلى الخطة المجانية</b>\n\n✅ لا يزال بإمكانك استخدام:\n• {FREE_LIMIT} تحليل يومياً\n\n💎 للعودة إلى الخطة المميزة، استخدم الأمر /premium"
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={'chat_id': user_id, 'text': message, 'parse_mode': 'HTML'}, timeout=5)
        except Exception as e:
            logger.error(f"Error sending downgrade message: {e}")
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        logger.error(f"Error downgrading user: {e}")
        return f"حدث خطأ: {e}", 500

# =================================================================================
# القسم 17: واجهات إدارة إضافية (Admin APIs & Stats)
# =================================================================================

@app.route('/admin/api/stats')
@login_required
def admin_api_stats():
    try:
        stats = get_global_stats(BOT_NAME)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/users')
@login_required
def admin_api_users():
    try:
        users = get_all_users_with_stats(BOT_NAME)
        return jsonify(users)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/security-info')
def security_info():
    return jsonify({
        'message': 'نظام حماية لوحة التحكم',
        'security_layers': [
            {'layer': 1, 'name': 'Session Authentication', 'description': 'التحقق من جلسة المستخدم عبر اسم المستخدم وكلمة المرور'},
            {'layer': 2, 'name': 'Security Headers', 'description': 'رؤوس أمان تمنع هجمات XSS و MIME sniffing'},
            {'layer': 3, 'name': 'HTTPS', 'description': 'تشفير البيانات أثناء الإرسال عبر Render'},
        ],
        'admin_url': '/secure/x7K9mP2/login',
        'dashboard_url': '/admin/dashboard',
        'protection_level': 'عالية'
    })

# =================================================================================
# القسم 18: تعديل الأسعار والإعدادات (Settings)
# =================================================================================

@app.route('/admin-prices', methods=['GET', 'POST'])
@login_required
def admin_prices():
    message = None
    message_type = None
    if request.method == 'POST':
        try:
            settings_to_save = {
                'price_monthly': request.form.get('price_monthly', '10'), 'price_half_yearly': request.form.get('price_half_yearly', '30'),
                'price_yearly': request.form.get('price_yearly', '48'), 'price_lifetime': request.form.get('price_lifetime', '100'),
                'duration_monthly': request.form.get('duration_monthly', '30'), 'duration_half_yearly': request.form.get('duration_half_yearly', '180'),
                'duration_yearly': request.form.get('duration_yearly', '365'), 'duration_lifetime': request.form.get('duration_lifetime', '36500'),
                'free_limit': request.form.get('free_limit', '2'), 'gemini_monthly_limit': request.form.get('gemini_monthly_limit', '20'),
                'gemini_free_limit': request.form.get('gemini_free_limit', '0'), 'stars_monthly': request.form.get('stars_monthly', '200'),
                'stars_half_yearly': request.form.get('stars_half_yearly', '500'), 'stars_yearly': request.form.get('stars_yearly', '800'),
                'stars_lifetime': request.form.get('stars_lifetime', '2000'), 'stars_usd_rate': request.form.get('stars_usd_rate', '0.025'),
                'stars_enabled': request.form.get('stars_enabled', 'true'), 'stars_extra_recs_small': request.form.get('stars_extra_recs_small', '50'),
                'stars_extra_recs_medium': request.form.get('stars_extra_recs_medium', '100'), 'stars_extra_recs_large': request.form.get('stars_extra_recs_large', '200'),
                'stars_extra_recs_premium': request.form.get('stars_extra_recs_premium', '500'), 'promo_active': request.form.get('promo_active', 'false'),
                'promo_half_yearly': request.form.get('promo_half_yearly', '25'), 'promo_yearly': request.form.get('promo_yearly', '40'),
                'promo_end_date': request.form.get('promo_end_date', ''), 'payment_number': request.form.get('payment_number', '772130931'),
                'developer_link': request.form.get('developer_link', 'https://t.me/E_Alshabany'), 'bot_link': request.form.get('bot_link', 'https://t.me/Social_Media_tools_bot')
            }
            saved_count = 0
            for key, value in settings_to_save.items():
                try:
                    result = supabase.table('bot_settings_social').upsert({'setting_key': key, 'setting_value': str(value), 'updated_at': datetime.now().isoformat()}, on_conflict='setting_key').execute()
                    if result.data:
                        saved_count += 1
                except Exception as e:
                    logger.error(f"Error saving {key}: {e}")
            if saved_count == len(settings_to_save):
                message = f"✅ تم حفظ {saved_count} إعداد بنجاح!"
                message_type = 'success'
            else:
                message = f"⚠️ تم حفظ {saved_count} من {len(settings_to_save)} إعداد فقط"
                message_type = 'warning'
            return redirect(url_for('admin_prices', msg=message, msg_type=message_type))
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return redirect(url_for('admin_prices', msg=f"❌ حدث خطأ: {e}", msg_type='error'))
    prices = get_all_prices()
    msg = request.args.get('msg')
    msg_type = request.args.get('msg_type', 'info')
    return render_template('admin_prices.html', prices=prices, msg=msg, msg_type=msg_type)

# =================================================================================
# القسم 19: سجل الإشعارات وإرسال الإشعارات (Notifications)
# =================================================================================

@app.route('/notifications-history')
@login_required
def notifications_history():
    notifications = get_notifications_history(100)
    return render_template('notifications_history.html', notifications=notifications)

@app.route('/send-notification', methods=['POST'])
@login_required
def send_notification():
    data = request.get_json()
    target = data.get('target')
    user_id = data.get('user_id')
    message = data.get('message')
    if not message:
        return jsonify({'success': False, 'message': 'الرسالة مطلوبة'})
    TOKEN = os.environ.get('TELEGRAM_TOKEN')
    users_to_notify = []
    if target == 'user' and user_id:
        users_to_notify = [int(user_id)]
        notification_type = 'individual'
        target_audience = f'user_{user_id}'
    elif target == 'all_premium':
        response = supabase.table('users').select('user_id').eq('status', 'premium').execute()
        users_to_notify = [u['user_id'] for u in (response.data or [])]
        notification_type = 'broadcast'
        target_audience = 'all_premium'
    elif target == 'free_users':
        response = supabase.table('users').select('user_id').eq('status', 'free').execute()
        users_to_notify = [u['user_id'] for u in (response.data or [])]
        notification_type = 'broadcast'
        target_audience = 'free_users'
    elif target in ['half_yearly', 'yearly', 'lifetime', 'monthly']:
        response = supabase.table('user_subscriptions_social').select('user_id, plan_id').eq('status', 'active').execute()
        plan_names = {'half_yearly': 'half_yearly', 'yearly': 'yearly', 'lifetime': 'lifetime', 'monthly': 'monthly'}
        for sub in (response.data or []):
            plan_response = supabase.table('subscription_plans_social').select('name').eq('id', sub['plan_id']).execute()
            if plan_response.data and plan_response.data[0]['name'] == plan_names.get(target):
                users_to_notify.append(sub['user_id'])
        notification_type = 'broadcast'
        target_audience = target
    else:
        return jsonify({'success': False, 'message': 'هدف غير صحيح'}), 400
    if not users_to_notify:
        return jsonify({'success': False, 'message': 'لا يوجد مستخدمين مستهدفين'}), 404
    notification_id = log_notification(notification_type, target_audience, int(user_id) if user_id and target == 'user' else None, message)
    sent_count = 0
    for uid in users_to_notify:
        try:
            response = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={'chat_id': uid, 'text': message, 'parse_mode': 'HTML'}, timeout=5)
            if response.status_code == 200:
                sent_count += 1
                if notification_id:
                    log_notification_delivery(notification_id, uid, 'sent')
            else:
                if notification_id:
                    log_notification_delivery(notification_id, uid, 'failed')
        except Exception as e:
            logger.error(f"Error sending to {uid}: {e}")
            if notification_id:
                log_notification_delivery(notification_id, uid, 'failed')
    if notification_id:
        supabase.table('notification_log_social').update({'sent_count': sent_count}).eq('id', notification_id).execute()
    return jsonify({'success': True, 'message': f'تم إرسال الإشعار إلى {sent_count} من {len(users_to_notify)} مستخدم'})

# =================================================================================
# القسم 20: صفحات التحقق من Google و TikTok
# =================================================================================

@app.route('/google4324552e195bad11.html')
def google_verification_file():
    try:
        with open('static/google4324552e195bad11.html', 'r', encoding='utf-8') as f:
            content = f.read()
        return content, 200, {'Content-Type': 'text/html'}
    except Exception as e:
        return f"File not found: {e}", 404

@app.route('/tiktokqpTHen1C0AsF1UmIXCVMMc6qc8EgpOAO.txt')
def tiktok_verification():
    try:
        with open('static/tiktokqpTHen1C0AsF1UmIXCVMMc6qc8EgpOAO.txt', 'r', encoding='utf-8') as f:
            content = f.read()
        return content, 200, {'Content-Type': 'text/plain'}
    except Exception as e:
        return f"File not found: {e}", 404

# =================================================================================
# القسم 21: تكامل TikTok OAuth
# =================================================================================

TIKTOK_CLIENT_KEY = os.environ.get('TIKTOK_CLIENT_KEY', '')
TIKTOK_CLIENT_SECRET = os.environ.get('TIKTOK_CLIENT_SECRET', '')
TIKTOK_REDIRECT_URI = os.environ.get('TIKTOK_REDIRECT_URI', f"https://{RENDER_URL}/callback/tiktok")

@app.route('/login/tiktok')
def tiktok_login():
    if not TIKTOK_CLIENT_KEY:
        return "TikTok API not configured", 500
    state = secrets.token_urlsafe(32)
    session['tiktok_state'] = state
    params = {'client_key': TIKTOK_CLIENT_KEY, 'scope': 'user.info.basic,user.info.profile,user.info.stats,video.list', 'response_type': 'code', 'redirect_uri': TIKTOK_REDIRECT_URI, 'state': state}
    auth_url = f"https://www.tiktok.com/v2/auth/authorize/?{urlencode(params)}"
    return redirect(auth_url)


import os
import requests
import logging
from flask import request, render_template_string, session, url_for, redirect, jsonify

# إعداد الـ Logger لمراقبة العمليات
logger = logging.getLogger(__name__)

@app.route('/callback/tiktok')
def tiktok_callback():
    # 1. التحقق من وجود أخطاء قادمة من تيك توك في الرابط
    error = request.args.get('error')
    if error:
        logger.error(f"❌ TikTok Redirect Error: {error}")
        return f"خطأ من تيك توك: {error}", 400
    
    code = request.args.get('code')
    state = request.args.get('state')
    
    # طباعة تشخيصية للـ Code المستلم
    logger.info(f"📡 Callback Received - Code: {code[:10]}... | State: {state}")
    
    if not code:
        logger.error("❌ No authorization code found in request")
        return "لم يتم استلام كود التفويض", 400
    
    # 2. استخراج user_id من الـ state
    user_id = None
    if state and '_' in state:
        try:
            user_id = int(state.split('_')[0])
            logger.info(f"👤 Extracted user_id: {user_id}")
        except Exception as e:
            logger.error(f"❌ Failed to parse user_id from state: {e}")
    
    if not user_id:
        logger.error("❌ Invalid or missing user_id in state")
        return "معرف المستخدم غير صالحة", 400

    # 3. جلب الإعدادات من رندر (Render Environment Variables)
    TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
    TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
    TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI") # تأكد من إضافته في رندر

    # الرابط الجديد للإصدار الثاني V2
    TOKEN_URL = 'https://open.tiktokapis.com/v2/oauth/token/'
    
    # تجهيز البيانات (Data Payload)
    data = {
        'client_key': TIKTOK_CLIENT_KEY,
        'client_secret': TIKTOK_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': TIKTOK_REDIRECT_URI, # 👈 السر في حل خطأ 10014
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cache-Control': 'no-cache'
    }

    logger.info(f"🔄 Attempting Token Exchange for user {user_id}...")
    logger.info(f"🔗 Using Redirect URI: {TIKTOK_REDIRECT_URI}")

    try:
        # إرسال الطلب لتيك توك
        response = requests.post(TOKEN_URL, data=data, headers=headers, timeout=30)
        
        # طباعة تفصيلية للرد لمعرفة الخلل
        logger.info(f"📊 TikTok Response Status: {response.status_code}")
        
        token_data = response.json()
        
        # التحقق من نجاح الحصول على التوكن
        if 'access_token' in token_data:
            access_token = token_data['access_token']
            refresh_token = token_data.get('refresh_token')
            open_id = token_data.get('open_id')
            expires_in = token_data.get('expires_in', 86400)

            logger.info(f"✅ SUCCESS: Access token obtained for user {user_id}")
            
            # حفظ التوكن في قاعدة البيانات باستخدام دالتك الأصلية
            from utils.tiktok_analyzer import save_tiktok_token
            save_tiktok_token(user_id, {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'open_id': open_id,
                'expires_in': expires_in
            })
            
            return render_template_string('''
                <!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="UTF-8"><title>تم الاتصال بنجاح</title>
                <style>
                    *{margin:0;padding:0;box-sizing:border-box;}
                    body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#fe2c55,#25f4ee);min-height:100vh;display:flex;justify-content:center;align-items:center;}
                    .card{background:white;border-radius:20px;padding:40px;text-align:center;max-width:400px;box-shadow:0 20px 40px rgba(0,0,0,0.2);}
                    h1{color:#121212;margin-bottom:10px;}
                    .success{color:#fe2c55;font-size:64px;margin-bottom:10px;}
                    .btn{display:inline-block;background:#121212;color:white;padding:12px 24px;border-radius:30px;text-decoration:none;margin-top:20px;transition:0.3s;font-weight:bold;}
                    .btn:hover{transform:scale(1.05);background:#000;}
                </style>
                </head>
                <body>
                    <div class="card">
                        <div class="success">🎵</div>
                        <h1>تم ربط تيك توك بنجاح!</h1>
                        <p>عظيم! حسابك متصل الآن بـ Social Analyzer AI. يمكنك العودة للبوت والبدء بالتحليل.</p>
                        <a href="https://t.me/Social_Media_tools_bot" class="btn">🚀 اذهب للبوت الآن</a>
                    </div>
                </body>
                </html>
            ''')
        else:
            # هنا يطبع الخلل الحقيقي إذا لم ينجح الطلب
            logger.error(f"❌ Token Exchange Failed! Response: {token_data}")
            return f"فشل تبادل التوكن: {token_data}", 400
            
    except Exception as e:
        logger.error(f"🔥 Critical Exception in TikTok Callback: {str(e)}")
        return f"حدث خطأ داخلي: {str(e)}", 500


@app.route('/tiktok/profile')
def tiktok_profile():
    """جلب بيانات الملف الشخصي باستخدام الإصدار V2"""
    # يفضل جلب التوكن من قاعدة البيانات باستخدام user_id، ولكن هنا سنتبع نهجك الحالي
    access_token = session.get('tiktok_access_token')
    if not access_token:
        return "يجب تسجيل الدخول أولاً", 401

    # رابط المعلومات الشخصية الجديد V2
    USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
    
    # في V2 التوكن يرسل في الـ Header وليس الـ Params
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    # تحديد الحقول المطلوبة (Scopes)
    params = {
        'fields': 'open_id,union_id,avatar_url,display_name,bio_description,is_verified'
    }
    
    try:
        response = requests.get(USER_INFO_URL, headers=headers, params=params)
        logger.info(f"Profile Request Status: {response.status_code}")
        return jsonify(response.json())
    except Exception as e:
        logger.error(f"❌ Error fetching TikTok profile: {e}")
        return jsonify({'error': str(e)}), 500






@app.route('/debug/tiktok-flow')
def tiktok_flow_debug():
    return '''
    <!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="UTF-8"><title>تدفق TikTok - شرح</title>
    <style>body{font-family:'Segoe UI',sans-serif;background:#f5f7fa;padding:20px;}.container{max-width:800px;margin:0 auto;background:white;border-radius:20px;padding:30px;}h1{color:#2c3e50;}
    .step{background:#f8f9fa;padding:15px;margin:15px 0;border-radius:10px;border-right:4px solid #667eea;}.code{background:#2d2d2d;color:#f8f8f2;padding:10px;border-radius:8px;font-family:monospace;font-size:12px;}
    .success{color:#48bb78;}</style></head><body><div class="container"><h1>🔄 تدفق تكامل TikTok</h1><div class="step"><strong>📌 الخطوة 1:</strong> <code>/login/tiktok</code></div>
    <div class="step"><strong>📌 الخطوة 2:</strong> إعادة التوجيه إلى <code>https://www.tiktok.com/v2/auth/authorize/...</code></div><div class="step"><strong>📌 الخطوة 3:</strong> تسجيل الدخول والموافقة على الصلاحيات</div>
    <div class="step"><strong>📌 الخطوة 4:</strong> إعادة التوجيه إلى <code class="success">✅ /callback/tiktok?code=xxxx&state=yyyy</code></div>
    <div class="step"><strong>📌 الخطوة 5:</strong> تبادل الرمز للحصول على Access Token</div><div class="step"><strong>📌 الخطوة 6:</strong> عرض صفحة النجاح</div>
    <hr><p><strong>🔗 روابط الاختبار:</strong></p><ul><li><a href="/login/tiktok" target="_blank">بدء تسجيل الدخول بتيك توك</a></li><li><a href="/tiktok/profile" target="_blank">عرض معلومات الملف الشخصي (بعد المصادقة)</a></li></ul></div></body></html>
    '''

# =================================================================================
# القسم 22: إدارة حدود توصيات Gemini (من لوحة التحكم)
# =================================================================================

@app.route('/admin/set-gemini-limit', methods=['POST'])
@login_required
def set_gemini_limit():
    try:
        user_id = int(request.form.get('user_id'))
        gemini_limit = int(request.form.get('gemini_limit'))
        result = supabase_admin.table('user_gemini_limits').upsert({'user_id': user_id, 'monthly_limit': gemini_limit, 'updated_at': datetime.now().isoformat()}, on_conflict='user_id').execute()
        if result.data:
            logger.info(f"✅ Gemini limit updated for user {user_id} to {gemini_limit}")
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        logger.error(f"Error setting gemini limit: {e}")
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/gemini-limits')
@login_required
def gemini_limits_page():
    try:
        default_limit = int(os.environ.get('GEMINI_MONTHLY_LIMIT', '20'))
        users_response = supabase.table('users').select('user_id, first_name, username, status').eq('status', 'premium').execute()
        limits_response = supabase.table('user_gemini_limits').select('user_id, monthly_limit').execute()
        user_limits = {l['user_id']: l['monthly_limit'] for l in (limits_response.data or [])}
        user_list = []
        for user in (users_response.data or []):
            user_list.append({'user_id': user['user_id'], 'first_name': user.get('first_name', ''), 'username': user.get('username', ''), 'status': user.get('status', 'free'), 'current_limit': user_limits.get(user['user_id'], default_limit)})
        return render_template('gemini_limits.html', users=user_list, default_limit=default_limit)
    except Exception as e:
        logger.error(f"Error in gemini_limits_page: {e}")
        return f"حدث خطأ: {e}", 500

# =================================================================================
# القسم 23: إيرادات النجوم (Stars Earnings)
# =================================================================================

@app.route('/admin/stars-earnings')
@login_required
def stars_earnings():
    try:
        from utils.db import supabase
        from datetime import datetime, timedelta
        total_response = supabase.table('stars_earnings').select('amount', count='exact').execute()
        total_earnings = sum([r['amount'] for r in (total_response.data or [])])
        total_transactions = total_response.count if hasattr(total_response, 'count') else len(total_response.data or [])
        today = datetime.now().date().isoformat()
        today_response = supabase.table('stars_earnings').select('amount').gte('payment_date', today).execute()
        today_earnings = sum([r['amount'] for r in (today_response.data or [])])
        today_transactions = len(today_response.data or [])
        first_day_of_month = datetime.now().date().replace(day=1).isoformat()
        month_response = supabase.table('stars_earnings').select('amount').gte('payment_date', first_day_of_month).execute()
        month_earnings = sum([r['amount'] for r in (month_response.data or [])])
        month_transactions = len(month_response.data or [])
        transactions_response = supabase.table('stars_earnings').select('*').order('payment_date', desc=True).limit(50).execute()
        transactions = transactions_response.data or []
        dollar_rate = 0.02
        total_dollars = total_earnings * dollar_rate
        today_dollars = today_earnings * dollar_rate
        month_dollars = month_earnings * dollar_rate
        stats = {
            'total_earnings': total_earnings, 'total_transactions': total_transactions, 'total_dollars': round(total_dollars, 2),
            'today_earnings': today_earnings, 'today_transactions': today_transactions, 'today_dollars': round(today_dollars, 2),
            'month_earnings': month_earnings, 'month_transactions': month_transactions, 'month_dollars': round(month_dollars, 2),
        }
        return render_template('stars_earnings.html', stats=stats, transactions=transactions)
    except Exception as e:
        logger.error(f"Error in stars_earnings: {e}")
        return f"حدث خطأ: {e}", 500

# =================================================================================


# =================================================================================
# القسم 25: API إنشاء توكن تجريبي (للتطوير فقط)
# =================================================================================

@app.route('/api/create_test_token', methods=['GET'])
def create_test_token():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'Missing user_id'}), 400
    try:
        user_id = int(user_id)
        token = create_secure_token(user_id)
        return jsonify({'token': token, 'url': f"https://{RENDER_URL}/app?token={token}"})
    except:
        return jsonify({'error': 'Invalid user_id'}), 400

# =================================================================================
# القسم 26: API تحليل الحسابات (لـ WebApp)
# =================================================================================

@app.route('/api/analyze', methods=['GET', 'POST'])
def api_analyze():
    """API لتحليل الحسابات من WebApp (يدعم يوتيوب حالياً)"""
    from utils.youtube_analyzer import get_channel_details, format_channel_report
    from utils.helpers import verify_token
    import asyncio
    import json
    
    # استخراج التوكن (من Header أو Parameter)
    token = None
    
    # 1. محاولة من Authorization header
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header[7:]
    
    # 2. محاولة من query parameters
    if not token:
        token = request.args.get('token')
    
    # 3. محاولة من body (لطلبات POST)
    if not token and request.is_json:
        data = request.get_json(silent=True)
        if data:
            token = data.get('token')
    
    if not token:
        return jsonify({'success': False, 'error': 'Token missing'}), 401
    
    # التحقق من صحة التوكن
    user_id = verify_token(token)
    if not user_id:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    # استخراج معلمات الطلب
    platform = None
    identifier = None
    
    if request.method == 'GET':
        platform = request.args.get('platform')
        identifier = request.args.get('identifier')
    else:
        data = request.get_json()
        if data:
            platform = data.get('platform')
            identifier = data.get('identifier')
    
    if not platform or not identifier:
        return jsonify({'success': False, 'error': 'Missing platform or identifier'}), 400
    
        # التحقق من صلاحية المستخدم (حصص التحليل)
    user_info = get_user_info(user_id)
    is_premium = user_info.get('status') == 'premium' if user_info else False
    
    if not is_premium:
        can_analyze_bool, current_uses = can_analyze(user_id)
        if not can_analyze_bool:
            prices = get_all_prices()
            free_limit = prices.get('free_limit', 2)
            remaining = free_limit - current_uses
            return jsonify({
                'success': False, 
                'error': f'⚠️ لقد وصلت للحد اليومي المجاني!\n\n📊 الحد المسموح: {free_limit} تحليل يومياً\n✅ التحليلات اليوم: {current_uses}\n🎯 المتبقي اليوم: {remaining}\n\n💎 للتحليل غير المحدود، اشترك في الخطة المميزة'
            }), 403
    
            # ========== تحليل YouTube ==========
    if platform == 'youtube':
        try:
            # تنظيف المعرف (إزالة @ والرابط)
            channel_clean = identifier
            channel_clean = channel_clean.replace('https://youtube.com/@', '')
            channel_clean = channel_clean.replace('https://www.youtube.com/@', '')
            if channel_clean.startswith('@'):
                channel_clean = channel_clean[1:]
            
            # استخدام دالة get_channel_details الموجودة
            channel_details, error = asyncio.run(get_channel_details(channel_clean))
            
        except Exception as e:
            logger.error(f"YouTube analysis error: {e}")
            return jsonify({'success': False, 'error': f'تحليل يوتيوب فشل: {str(e)}'}), 500
        
        if error or not channel_details:
            return jsonify({'success': False, 'error': error or 'لم يتم العثور على القناة'}), 404
        
        # حساب عدد التحليلات المتبقية للمستخدم المجاني
        remaining_analyses = None
        if not is_premium:
            remaining = get_remaining_analyses(user_id)
            remaining_analyses = remaining if remaining > 0 else 0
        else:
            remaining_analyses = "غير محدود"
        
        # استخدام دالة format_channel_report الموجودة
        report_message, file_data = format_channel_report(
            channel_details, 
            user_id, 
            is_premium, 
            remaining_analyses
        )
        
        # ========== تخزين البيانات في analysis_history (نسخة محسنة) ==========
        try:
            # تحويل قائمة الفيديوهات إلى JSON
            latest_videos = channel_details.get('latest_videos', [])
            top_posts_json = latest_videos if latest_videos else None
            
            # حساب engagement_rate
            subscribers_raw = channel_details.get('subscribers_raw', 0)
            avg_views_raw = channel_details.get('avg_views_raw', 0)
            engagement_rate = None
            if subscribers_raw > 0 and avg_views_raw > 0:
                engagement_rate = round((avg_views_raw / subscribers_raw) * 100, 2)
            
            # حساب best_posting_hour
            best_posting_hour = None
            hour_counts = {}
            for video in latest_videos:
                published_at = video.get('published_at', '')
                if published_at and 'T' in published_at:
                    try:
                        hour = int(published_at.split('T')[1].split(':')[0])
                        hour_counts[hour] = hour_counts.get(hour, 0) + 1
                    except:
                        pass
            if hour_counts:
                best_posting_hour = max(hour_counts, key=hour_counts.get)
            
            # حساب best_posting_day
            best_posting_day = None
            day_counts = {}
            days_map = {
                'Monday': 'الإثنين', 'Tuesday': 'الثلاثاء', 'Wednesday': 'الأربعاء',
                'Thursday': 'الخميس', 'Friday': 'الجمعة', 'Saturday': 'السبت', 'Sunday': 'الأحد'
            }
            for video in latest_videos:
                published_at = video.get('published_at', '')
                if published_at:
                    try:
                        from datetime import datetime
                        dt = datetime.strptime(published_at[:10], '%Y-%m-%d')
                        day_name = dt.strftime('%A')
                        day_counts[day_name] = day_counts.get(day_name, 0) + 1
                    except:
                        pass
            if day_counts:
                best_day_en = max(day_counts, key=day_counts.get)
                best_posting_day = days_map.get(best_day_en, best_day_en)
            
            # حساب avg_posts_per_week
            avg_posts_per_week = None
            if latest_videos:
                dates = []
                for video in latest_videos:
                    pub_date = video.get('published_at', '')[:10]
                    if pub_date and len(pub_date) >= 10:
                        dates.append(pub_date)
                if len(dates) >= 2:
                    try:
                        from datetime import datetime
                        d1 = datetime.strptime(min(dates), '%Y-%m-%d')
                        d2 = datetime.strptime(max(dates), '%Y-%m-%d')
                        weeks = max(1, (d2 - d1).days / 7)
                        avg_posts_per_week = round(len(latest_videos) / weeks, 1)
                    except:
                        pass
            
            # حساب إجمالي الإعجابات والتعليقات
            total_likes = sum(v.get('likes', 0) for v in latest_videos)
            total_comments = sum(v.get('comments', 0) for v in latest_videos)
            avg_likes_per_post = round(total_likes / len(latest_videos), 2) if latest_videos else 0
            avg_comments_per_post = round(total_comments / len(latest_videos), 2) if latest_videos else 0
            
            # حساب analysis_number (الرقم التسلسلي)
            max_number_result = supabase.table('analysis_history')\
                .select('analysis_number')\
                .eq('user_id', user_id)\
                .order('analysis_number', desc=True)\
                .limit(1)\
                .execute()
            
            next_number = 1
            if max_number_result.data and max_number_result.data[0].get('analysis_number'):
                next_number = max_number_result.data[0]['analysis_number'] + 1
            
            # التحقق مما إذا كان هذا هو أول تحليل لهذه القناة
            first_check = supabase.table('analysis_history')\
                .select('id')\
                .eq('user_id', user_id)\
                .eq('account_name', channel_details.get('title'))\
                .execute()
            is_first_analysis = (first_check.count == 0)
            
            # بناء سجل التحليل (صف واحد كامل مع جميع الحقول)
            from datetime import timezone, timedelta
            local_tz = timezone(timedelta(hours=3))
            local_now = datetime.now(local_tz)
            
            analysis_record = {
                # الحقول الأساسية
                'user_id': user_id,
                'username': user_info.get('username') if user_info else None,
                'first_name': user_info.get('first_name') if user_info else None,
                'platform': 'youtube',
                'analyzed_user_id': channel_details.get('channel_id'),
                'analyzed_username': channel_clean,
                'account_name': channel_details.get('title'),
                'analysis_type': 'first' if is_first_analysis else 'latest',
                'analysis_date': local_now.isoformat(),
                
                # الإحصائيات الأساسية
                'subscribers': subscribers_raw,
                'total_views': channel_details.get('total_views_raw', 0),
                'total_posts': channel_details.get('total_videos_raw', 0),
                'avg_views_per_post': avg_views_raw,
                'top_posts': top_posts_json,
                
                # المقاييس المتقدمة
                'engagement_rate': engagement_rate,
                'best_posting_hour': best_posting_hour,
                'best_posting_day': best_posting_day,
                'avg_posts_per_week': avg_posts_per_week,
                
                # حقول إضافية
                'total_videos': channel_details.get('total_videos_raw', 0),
                'total_likes': total_likes,
                'total_comments': total_comments,
                'followers': subscribers_raw,
                'following': 0,
                'avg_likes_per_post': avg_likes_per_post,
                'avg_comments_per_post': avg_comments_per_post,
                'avg_video_duration': 600,
                'best_video_length': 0,
                'best_video_category': None,
                'analysis_duration': 0,
                
                # معلومات القناة
                'country': channel_details.get('country'),
                'published_at': channel_details.get('published_at'),
                
                # علامات
                'is_premium': is_premium,
                'analysis_number': next_number,
                'is_first_analysis': is_first_analysis,
                'updated_at': local_now.isoformat(),
            }
            
            # إدراج في قاعدة البيانات
            supabase.table('analysis_history').insert(analysis_record).execute()
            logger.info(f"Saved analysis for user {user_id}: {channel_details.get('title')}")
            
        except Exception as e:
            logger.error(f"Error saving analysis to history: {e}")
            # لا نريد إفشال الطلب بسبب خطأ في الحفظ
            pass
        
        # تحديث إحصائيات المستخدم (للحد اليومي)
        try:
            increment_usage(user_id, 'youtube', {
                'account_name': channel_details.get('title', identifier),
                'subscribers': channel_details.get('subscribers_raw', 0),
                'total_posts': channel_details.get('total_videos_raw', 0)
            })
        except Exception as e:
            logger.error(f"Error incrementing usage: {e}")
        
        # ========== إرسال التقرير إلى البوت تلقائياً (باستخدام القالب) ==========
        try:
            from utils.texts import ReportTemplates
            from datetime import datetime
            
            # تنسيق قائمة الفيديوهات
            videos_list = ""
            for i, video in enumerate(latest_videos[:5], 1):
                title = video.get('title', 'بدون عنوان')[:60]
                video_id = video.get('video_id', '')
                if video_id:
                    videos_list += f"{i}. <a href='https://youtu.be/{video_id}'>{title}</a>\n"
                else:
                    videos_list += f"{i}. {title}\n"
            
            # بناء التقرير باستخدام القالب
            report_text = ReportTemplates.ANALYSIS_REPORT.format(
                analysis_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                platform='يوتيوب',
                account_name=channel_details.get('title'),
                subscribers=format_number(subscribers_raw),
                total_views=format_number(total_views_raw),
                total_posts=total_videos_raw,
                avg_views=format_number(avg_views_raw)
            )
            
            # إضافة الفيديوهات إلى التقرير
            if latest_videos:
                report_text += f"\n\n🎬 أحدث الفيديوهات:\n{videos_list}"
            
            # إرسال التقرير إلى البوت
            BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
            if BOT_TOKEN:
                filename = f"تحليل_{channel_details.get('title')[:30]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                files = {'document': (filename, report_text.encode('utf-8'), 'text/plain')}
                data = {'chat_id': user_id, 'caption': f"📊 تقرير تحليل قناة {channel_details.get('title')}"}
                
                requests.post(
                    f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument',
                    data=data,
                    files=files,
                    timeout=60
                )
                logger.info(f"✅ Report sent to user {user_id} automatically")
                
        except Exception as e:
            logger.error(f"Error sending auto report: {e}")
        
        # استخراج نص التقرير من الملف (للتنزيل في الواجهة)
        file_content = file_data[0] if file_data else report_message
        
        return jsonify({
            'success': True, 
            'platform': 'youtube',
            'identifier': identifier,
            'report': report_message,
            'file_content': file_content,
            'channel_name': channel_details.get('title'),
            'subscribers': channel_details.get('subscribers'),
            'subscribers_raw': channel_details.get('subscribers_raw', 0),
            'total_views': channel_details.get('total_views'),
            'total_views_raw': channel_details.get('total_views_raw', 0),
            'total_videos': channel_details.get('total_videos'),
            'total_videos_raw': channel_details.get('total_videos_raw', 0),
            'avg_views': channel_details.get('avg_views'),
            'avg_views_raw': channel_details.get('avg_views_raw', 0)
        })

    # ========== منصات أخرى (قيد التطوير) ==========
    elif platform in ['instagram', 'facebook', 'snapchat']:
        platform_names = {
            'instagram': 'انستقرام',
            'facebook': 'فيسبوك',
            'snapchat': 'سناب شات'
        }
        return jsonify({
            'success': False, 
            'error': f'📢 ميزة تحليل {platform_names.get(platform, platform)} قيد التطوير حالياً، ستكون متاحة قريباً!'
        }), 501
    
    elif platform == 'tiktok':
        from utils.tiktok_analyzer import get_tiktok_token, format_tiktok_report
        from utils.db import get_user_info, increment_usage, get_remaining_analyses
        from datetime import datetime
        import asyncio
        
        # تنظيف اسم المستخدم (إزالة @ والرابط)
        username_clean = identifier
        username_clean = username_clean.replace('https://tiktok.com/@', '')
        username_clean = username_clean.replace('https://www.tiktok.com/@', '')
        if username_clean.startswith('@'):
            username_clean = username_clean[1:]
        
        # التحقق من وجود توكن TikTok للمستخدم
        tiktok_token_data = get_tiktok_token(user_id)
        
        if not tiktok_token_data:
            # لا يوجد توكن → عرض رابط التفعيل
            from utils.tiktok_analyzer import get_tiktok_auth_url
            auth_url = get_tiktok_auth_url(user_id)
            return jsonify({
                'success': False,
                'need_auth': True,
                'auth_url': auth_url,
                'error': '🔐 تحتاج إلى تفعيل حساب TikTok أولاً'
            }), 401
        
        # يوجد توكن → تنفيذ التحليل
        try:
            # استدعاء دالة التقرير الموجودة
            report_text = await format_tiktok_report(user_id, username_clean)
            
            if not report_text or "❌" in report_text:
                return jsonify({
                    'success': False,
                    'error': report_text or 'فشل في تحليل حساب TikTok'
                }), 500
            
            # تحديث عداد الاستخدام
            increment_usage(user_id, 'tiktok', {
                'account_name': username_clean,
                'platform': 'tiktok'
            })
            
            # حساب عدد التحليلات المتبقية
            remaining_analyses = None
            if not is_premium:
                remaining = get_remaining_analyses(user_id)
                remaining_analyses = remaining if remaining > 0 else 0
            else:
                remaining_analyses = "غير محدود"
            
            # إرسال التقرير إلى البوت تلقائياً
            try:
                BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
                if BOT_TOKEN:
                    filename = f"تحليل_TikTok_{username_clean}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    files = {'document': (filename, report_text.encode('utf-8'), 'text/plain')}
                    data = {'chat_id': user_id, 'caption': f"📊 تقرير تحليل حساب TikTok @{username_clean}"}
                    
                    requests.post(
                        f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument',
                        data=data,
                        files=files,
                        timeout=60
                    )
                    logger.info(f"✅ TikTok report sent to user {user_id} automatically")
            except Exception as e:
                logger.error(f"Error sending auto TikTok report: {e}")
            
            return jsonify({
                'success': True,
                'platform': 'tiktok',
                'identifier': username_clean,
                'report': report_text,
                'file_content': report_text,
                'account_name': username_clean,
                'remaining_analyses': remaining_analyses
            })
            
        except Exception as e:
            logger.error(f"TikTok analysis error: {e}")
            return jsonify({
                'success': False,
                'error': f'فشل تحليل TikTok: {str(e)}'
            }), 500
        pass
    
    else:
        return jsonify({'success': False, 'error': f'منصة {platform} غير مدعومة'}), 400


# =================================================================================
# API لجلب تاريخ التحليلات (لـ WebApp)
# =================================================================================

@app.route('/api/analysis/history')
def get_analysis_history():
    """جلب آخر التحليلات للمستخدم"""
    token = request.args.get('token')
    if not token:
        return jsonify({'success': False, 'error': 'Missing token'}), 401
    
    try:
        user_id = int(token.split(':')[0])
    except:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    limit = int(request.args.get('limit', 10))
    
    try:
        # جلب آخر التحليلات من جدول analysis_history
        response = supabase.table('analysis_history')\
            .select('*')\
            .eq('user_id', user_id)\
            .order('analysis_date', desc=True)\
            .limit(limit)\
            .execute()
        
        # تحويل البيانات إلى صيغة مناسبة
        analyses = []
        for item in (response.data or []):
            analyses.append({
                'id': item.get('id'),
                'platform': item.get('platform'),
                'account_identifier': item.get('analyzed_username'),
                'account_name': item.get('account_name'),
                'analysis_date': item.get('analysis_date'),
                'subscribers': item.get('subscribers', 0),
                'total_views': item.get('total_views', 0),
                'total_posts': item.get('total_posts', 0),
                'avg_views_per_post': item.get('avg_views_per_post', 0),
                'top_posts': item.get('top_posts'),
                'country': item.get('country'),
                'published_at': item.get('published_at')
            })
        
        return jsonify({'success': True, 'data': analyses})
    except Exception as e:
        logger.error(f"Error fetching analysis history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analysis/details')
def get_analysis_details():
    """جلب تفاصيل تحليل معين"""
    analysis_id = request.args.get('id')
    token = request.args.get('token')
    
    if not analysis_id or not token:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400
    
    try:
        user_id = int(token.split(':')[0])
    except:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    try:
        response = supabase.table('analysis_history')\
            .select('*')\
            .eq('id', analysis_id)\
            .eq('user_id', user_id)\
            .execute()
        
        if response.data:
            item = response.data[0]
            details = {
                'id': item.get('id'),
                'platform': item.get('platform'),
                'account_identifier': item.get('analyzed_username'),
                'account_name': item.get('account_name'),
                'analysis_date': item.get('analysis_date'),
                'subscribers': item.get('subscribers', 0),
                'total_views': item.get('total_views', 0),
                'total_posts': item.get('total_posts', 0),
                'avg_views_per_post': item.get('avg_views_per_post', 0),
                'top_posts': item.get('top_posts'),
                'country': item.get('country'),
                'published_at': item.get('published_at')
            }
            return jsonify({'success': True, 'data': details})
        else:
            return jsonify({'success': False, 'error': 'Analysis not found'}), 404
    except Exception as e:
        logger.error(f"Error fetching analysis details: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =================================================================================
# API جديد: جلب أول تحليل (نقطة البداية المرجعية)
# =================================================================================

@app.route('/api/analysis/first-analysis')
def get_first_analysis():
    """جلب أول تحليل للمستخدم (نقطة البداية المرجعية)"""
    token = request.args.get('token')
    if not token:
        return jsonify({'success': False, 'error': 'Missing token'}), 401
    
    try:
        user_id = int(token.split(':')[0])
    except:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    try:
        # جلب التحليل الذي تم وضع علامة is_first_analysis = True
        # ✅ إزالة asc=True
        response = supabase.table('analysis_history')\
            .select('*')\
            .eq('user_id', user_id)\
            .eq('is_first_analysis', True)\
            .order('analysis_date')\
            .limit(1)\
            .execute()
        
        if response.data:
            item = response.data[0]
            return jsonify({
                'success': True,
                'data': {
                    'id': item.get('id'),
                    'platform': item.get('platform'),
                    'account_name': item.get('account_name'),
                    'account_identifier': item.get('analyzed_username'),
                    'analysis_date': item.get('analysis_date'),
                    'subscribers': item.get('subscribers', 0),
                    'total_views': item.get('total_views', 0),
                    'total_posts': item.get('total_posts', 0),
                    'avg_views_per_post': item.get('avg_views_per_post', 0),
                    'analysis_number': item.get('analysis_number')  # ✅ جديد
                }
            })
        else:
            # إذا لم يوجد تحليل مميز بـ is_first_analysis
            # نحاول جلب أقدم تحليل للمستخدم
            # ✅ إزالة asc=True
            fallback_response = supabase.table('analysis_history')\
                .select('*')\
                .eq('user_id', user_id)\
                .not_.is_('top_posts', 'null')\
                .order('analysis_date')\
                .limit(1)\
                .execute()
            
            if fallback_response.data:
                item = fallback_response.data[0]
                return jsonify({
                    'success': True,
                    'data': {
                        'id': item.get('id'),
                        'platform': item.get('platform'),
                        'account_name': item.get('account_name'),
                        'account_identifier': item.get('analyzed_username'),
                        'analysis_date': item.get('analysis_date'),
                        'subscribers': item.get('subscribers', 0),
                        'total_views': item.get('total_views', 0),
                        'total_posts': item.get('total_posts', 0),
                        'avg_views_per_post': item.get('avg_views_per_post', 0)
                    }
                })
            else:
                return jsonify({'success': True, 'data': None})
        
    except Exception as e:
        logger.error(f"Error fetching first analysis: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
# =================================================================================
# القسم 27: واجهات API الخاصة بالتبويبات (للإصدارات الجديدة)
# =================================================================================

@app.route('/api/profile_data')
def get_profile_data():
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'Missing token'}), 401
    try:
        user_id = int(token.split(':')[0])
    except:
        return jsonify({'error': 'Invalid token'}), 401
    user_info = get_user_info(user_id)
    accounts = get_user_social_accounts(user_id)
    return jsonify({
        'success': True,
        'user': {'first_name': user_info.get('first_name'), 'username': user_info.get('username'), 'created_at': user_info.get('created_at')},
        'is_premium': user_info.get('status') == 'premium',
        'accounts': accounts
    })

@app.route('/api/home_data')
def get_home_data():
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'Missing token'}), 401
    try:
        user_id = int(token.split(':')[0])
    except:
        return jsonify({'error': 'Invalid token'}), 401
    from datetime import date
    user_info = get_user_info(user_id)
    usage = get_user_usage(user_id)
    is_premium = user_info.get('status') == 'premium'
    prices = get_all_prices()
    gemini_uses = 0
    gemini_limit = prices.get('gemini_monthly_limit', 20) if is_premium else prices.get('gemini_free_limit', 0)
    try:
        from utils.db import supabase
        current_month = datetime.now().strftime('%Y-%m')
        gemini_response = supabase.table('gemini_usage').select('monthly_recommendations').eq('user_id', user_id).eq('last_use_month', current_month).execute()
        if gemini_response.data:
            gemini_uses = gemini_response.data[0].get('monthly_recommendations', 0)
    except:
        pass
    subscription_info = {}
    if is_premium:
        try:
            sub_response = supabase.table('user_subscriptions_social').select('*, subscription_plans_social(name_ar)').eq('user_id', user_id).eq('status', 'active').execute()
            if sub_response.data:
                sub = sub_response.data[0]
                end_date = datetime.strptime(sub['end_date'], '%Y-%m-%d').date()
                days_left = max(0, (end_date - date.today()).days)
                subscription_info = {'plan': sub.get('subscription_plans_social', {}).get('name_ar', 'مميز'), 'start_date': sub.get('start_date'), 'end_date': sub.get('end_date'), 'days_left': days_left}
        except:
            pass
    return jsonify({
        'success': True,
        'stats': {'total_uses': usage.get('total_uses', 0)},
        'is_premium': is_premium,
        'gemini_uses': gemini_uses,
        'gemini_limit': gemini_limit,
        'free_limit': prices.get('free_limit', 2),
        'subscription': subscription_info if subscription_info else None
    })
# =================================================================================
# API للتحقق من صلاحيات المستخدم (لـ WebApp)القسم 28
# =================================================================================

@app.route('/api/user_permissions')
def get_user_permissions():
    """API لجلب صلاحيات المستخدم والحدود (لـ WebApp)"""
    from utils.db import get_user_info, get_bot_setting, get_user_gemini_limit, get_gemini_remaining, supabase
    from utils.helpers import verify_token
    from datetime import date
    
    token = request.args.get('token')
    if not token:
        return jsonify({'success': False, 'error': 'Missing token'}), 401
    
    user_id = verify_token(token)
    if not user_id:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    # جلب معلومات المستخدم
    user_info = get_user_info(user_id)
    if not user_info:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    is_premium = user_info.get('status') == 'premium'
    
    # جلب الإعدادات من قاعدة البيانات
    free_limit = int(get_bot_setting('free_limit', '2'))
    gemini_default_limit = int(get_bot_setting('gemini_monthly_limit', '20'))
    
    # حساب التحليلات المتبقية للمستخدم المجاني
    daily_uses = 0
    daily_remaining = None
    if not is_premium:
        try:
            response = supabase.table('users').select('daily_uses, last_use_date').eq('user_id', user_id).execute()
            if response.data:
                daily_uses = response.data[0].get('daily_uses', 0)
                last_use_date = response.data[0].get('last_use_date')
                
                # إعادة تعيين العداد إذا كان اليوم مختلفاً
                today_str = date.today().isoformat()
                if last_use_date != today_str:
                    daily_uses = 0
            daily_remaining = max(0, free_limit - daily_uses)
        except Exception as e:
            logger.error(f"Error getting daily uses: {e}")
            daily_remaining = free_limit
    
    # حساب التوصيات المتبقية للمستخدم
    gemini_remaining = None
    gemini_limit = None
    gemini_used = 0
    
    if is_premium:
        gemini_limit = get_user_gemini_limit(user_id)
        # حساب عدد التوصيات المستخدمة هذا الشهر
        try:
            from utils.db import get_gemini_usage
            usage = get_gemini_usage(user_id)
            if usage:
                gemini_used = usage.get('monthly_recommendations', 0)
                gemini_remaining = max(0, gemini_limit - gemini_used)
            else:
                gemini_remaining = gemini_limit
        except:
            gemini_remaining = gemini_limit
    else:
        gemini_limit = int(get_bot_setting('gemini_free_limit', '0'))
        gemini_remaining = 0
    
    # التحقق من وجود حساب يوتيوب مسجل
    has_youtube_account = False
    try:
        accounts_response = supabase.table('user_social_accounts').select('id').eq('user_id', user_id).eq('platform', 'youtube').eq('is_active', True).execute()
        has_youtube_account = len(accounts_response.data) > 0
    except:
        pass
    
    return jsonify({
        'success': True,
        'is_premium': is_premium,
        'free_limit': free_limit,
        'daily_uses': daily_uses,
        'daily_remaining': daily_remaining,
        'gemini_limit': gemini_limit,
        'gemini_used': gemini_used,
        'gemini_remaining': gemini_remaining,
        'has_youtube_account': has_youtube_account,
        'premium_until': user_info.get('premium_until') if is_premium else None,
        'username': user_info.get('username'),
        'first_name': user_info.get('first_name')
    })

# =================================================================================
# API لتوليد التقارير (باستخدام القوالب من texts.py)
# =================================================================================

@app.route('/api/generate-report', methods=['POST'])
def generate_report():
    """توليد تقرير نصي باستخدام القوالب من texts.py"""
    from utils.texts import ReportTemplates
    
    data = request.get_json()
    report_type = data.get('type')
    report_data = data.get('data', {})
    
    if report_type == 'analysis':
        report = ReportTemplates.ANALYSIS_REPORT.format(**report_data)
    elif report_type == 'recommendations':
        report = ReportTemplates.RECOMMENDATIONS_REPORT.format(**report_data)
    else:
        return jsonify({'error': 'Invalid report type'}), 400
    
    return jsonify({'report': report})

# =================================================================================
# API لإرسال التقرير إلى البوت (Telegram Document)
# =================================================================================

@app.route('/api/send-report-to-bot', methods=['POST'])
def send_report_to_bot():
    """إرسال تقرير التحليل كملف Document باستخدام دوال البوت الموجودة"""
    from utils.helpers import verify_token
    from utils.db import supabase, get_user_info, get_user_social_accounts
    from utils.youtube_analyzer import get_channel_details, format_channel_report
    import requests
    import asyncio
    from datetime import datetime
    
    data = request.get_json()
    token = data.get('token')
    analysis_id = data.get('analysis_id')
    return_only = data.get('return_report', False)  # ✅ فقط هذا السطر مضاف
    
    if not token or not analysis_id:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400
    
    user_id = verify_token(token)
    if not user_id:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    try:
        # جلب تفاصيل التحليل من قاعدة البيانات
        response = supabase.table('analysis_history').select('*').eq('id', analysis_id).eq('user_id', user_id).execute()
        if not response.data:
            return jsonify({'success': False, 'error': 'Analysis not found'}), 404
        
        analysis = response.data[0]
        
        # جلب اسم القناة من التحليل
        channel_username = analysis.get('analyzed_username', '')
        if not channel_username:
            channel_username = analysis.get('account_name', '')
        
        # تنظيف المعرف (إزالة @)
        channel_username = channel_username.replace('@', '')
        
        if not channel_username:
            return jsonify({'success': False, 'error': 'Channel username not found'}), 404
        
        # جلب معلومات المستخدم للتحقق من حالة الاشتراك
        user_info = get_user_info(user_id)
        is_premium = user_info.get('status') == 'premium' if user_info else False
        remaining_analyses = None
        
        # استخدام دالة البوت الأصلية للحصول على التقرير المفصل
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        channel_details, error = loop.run_until_complete(get_channel_details(channel_username))
        loop.close()
        
        if error or not channel_details:
            return jsonify({'success': False, 'error': error or 'لم يتم العثور على القناة'}), 404
        
        # استخدام دالة تنسيق التقرير من البوت (نفس التي يستخدمها البوت)
        report_message, file_data = format_channel_report(
            channel_details, 
            user_id, 
            is_premium, 
            remaining_analyses
        )
        
        # الحصول على محتوى الملف النصي
        file_content = file_data[0] if file_data else report_message
        
        # ✅ إذا كان الطلب فقط لإرجاع التقرير (للعرض في النافذة المنبثقة)
        if return_only:
            return jsonify({'success': True, 'report_text': file_content})
        
        # ========== باقي الكود كما هو (لإرسال الملف إلى البوت) ==========
        
        # إرسال الملف عبر البوت
        BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
        if not BOT_TOKEN:
            return jsonify({'success': False, 'error': 'Bot token not configured'}), 500
        
        chat_id = user_id
        now = datetime.now()
        filename = f"تحليل_قناة_{channel_username}_{now.strftime('%Y%m%d_%H%M%S')}.txt"
        
        # إرسال الرسالة النصية أولاً (نفس ما يفعله البوت)
        try:
            requests.post(
                f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                json={'chat_id': chat_id, 'text': report_message, 'parse_mode': 'HTML'},
                timeout=30
            )
        except Exception as e:
            logger.error(f"Error sending text message: {e}")
        
        # إرسال الملف
        files = {'document': (filename, file_content.encode('utf-8'), 'text/plain')}
        data = {'chat_id': chat_id, 'caption': f"📊 ملف التحليل الكامل لقناة {channel_details.get('title')}"}
        
        bot_response = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument',
            data=data,
            files=files,
            timeout=60
        )
        
        if bot_response.status_code == 200:
            logger.info(f"Report sent to user {user_id} via bot")
            return jsonify({'success': True, 'message': 'تم إرسال التقرير إلى البوت'})
        else:
            logger.error(f"Failed to send document: {bot_response.text}")
            return jsonify({'success': False, 'error': 'Failed to send via bot'}), 500
            
    except Exception as e:
        logger.error(f"Error sending report to bot: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# =================================================================================
# API لتوصيات الذكاء الاصطناعي (يستخدم دوال البوت الحالية)
# =================================================================================

@app.route('/api/recommendations', methods=['POST'])
def api_recommendations():
    """API لتوليد توصيات الذكاء الاصطناعي (يستخدم دوال البوت الموجودة)"""
    from utils.helpers import verify_token
    from utils.db import get_user_info, get_user_social_accounts, can_use_gemini, increment_gemini_usage, save_recommendation
    from utils.youtube_analyzer import get_channel_details
    from utils.gemini_ai import get_advanced_recommendations
    import requests
    import asyncio
    from datetime import datetime
    
    data = request.get_json()
    token = data.get('token')
    
    if not token:
        return jsonify({'success': False, 'error': 'Missing token'}), 401
    
    user_id = verify_token(token)
    if not user_id:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    # التحقق من صلاحية المستخدم
    user_info = get_user_info(user_id)
    is_premium = user_info.get('status') == 'premium' if user_info else False
    
    if not is_premium:
        return jsonify({'success': False, 'error': '💎 هذه الميزة متاحة فقط للمستخدمين المميزين!'}), 403
    
    # التحقق من حصة التوصيات الشهرية
    can_use, remaining, error_msg = can_use_gemini(user_id)
    if not can_use:
        return jsonify({'success': False, 'error': error_msg}), 403
    
    # جلب حساب اليوتيوب المسجل
    accounts = get_user_social_accounts(user_id)
    youtube_account = accounts.get('youtube')
    if not youtube_account:
        return jsonify({'success': False, 'error': 'لم تقم بتسجيل حساب يوتيوب بعد!'}), 404
    
    account_identifier = youtube_account['account_identifier'].replace('@', '')
    
    # ✅ استخدام asyncio.run() لتشغيل الدوال غير المتزامنة
    async def fetch_data():
        channel_details, error = await get_channel_details(account_identifier)
        return channel_details, error
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        channel_details, error = loop.run_until_complete(fetch_data())
        loop.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
    if error or not channel_details:
        return jsonify({'success': False, 'error': error or 'لم يتم العثور على القناة'}), 404
    
    # ✅ تشغيل دالة التوصيات غير المتزامنة
    async def fetch_recommendations():
        return await get_advanced_recommendations(channel_details)
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        recommendations = loop.run_until_complete(fetch_recommendations())
        loop.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
    if not recommendations or len(recommendations) < 50:
        return jsonify({'success': False, 'error': '⚠️ عذراً، لم يتمكن الذكاء الاصطناعي من توليد توصيات في هذا الوقت. يرجى المحاولة مرة أخرى لاحقاً.'}), 500
    
    # حفظ التوصية في قاعدة البيانات
    key_points = []
    for line in recommendations.split('\n'):
        line_stripped = line.strip()
        if line_stripped.startswith(('📊', '🎬', '💡', '📜', '🚀', '•', '-', '✅')):
            key_points.append(line_stripped[:200])
    
    save_recommendation(user_id, 'youtube', account_identifier, recommendations, key_points[:5])
    
    # زيادة عدد استخدامات Gemini
    increment_gemini_usage(user_id)
    
    # إرسال التوصية إلى البوت
    BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    if BOT_TOKEN:
        now = datetime.now()
        filename = f"توصيات_{channel_details.get('title', 'قناة')}_{now.strftime('%Y%m%d_%H%M%S')}.txt"
        
        # إرسال الملف
        files = {'document': (filename, recommendations.encode('utf-8'), 'text/plain')}
        data = {'chat_id': user_id, 'caption': f"🤖 توصيات قناة {channel_details.get('title')}"}
        
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument',
            data=data,
            files=files,
            timeout=60
        )
    
    return jsonify({
        'success': True,
        'message': 'تم توليد التوصيات وإرسالها إلى البوت',
        'remaining': remaining - 1
    })
# ========== API المساعد الذكي المتطور V2 ==========
@app.route('/api/ai-chat', methods=['POST'])
@token_required
def ai_chat(user_id):  # ✅ أضف user_id كمعامل
    """API للمساعد الذكي - مع تعلم ذاتي وتخزين في Supabase"""
    try:
        data = request.get_json()
        question = data.get('question', '')
        context = data.get('context', {})
        
        if not question:
            return jsonify({'success': False, 'error': 'السؤال مطلوب'}), 400
        
        # ✅ user_id تأتي من الـ decorator مباشرة
        user_id_str = str(user_id)  # تحويل إلى string
        
        is_premium = context.get('user_permissions', {}).get('is_premium', False)
        
        # بناء سياق المستخدم
        user_permissions = context.get('user_permissions', {})
        user_context = f"""
        - نوع الخطة: {'⭐ مميز' if is_premium else '🎁 مجاني'}
        - تحليلات يومية متبقية: {user_permissions.get('daily_remaining', 0)}
        - توصيات AI متبقية: {user_permissions.get('gemini_remaining', 0)}/{user_permissions.get('gemini_limit', 0)}
        - لديه حساب يوتيوب: {'✅ نعم' if context.get('has_youtube') else '❌ لا'}
        """
        
        # استدعاء المساعد الذكي المتطور
        from utils.chat_ai_v2 import get_chat_response
        
        result = get_chat_response(
            question=question,
            user_id=user_id_str,
            user_context=user_context,
            is_premium=is_premium
        )
        
        return jsonify(result)
        
    except ImportError as e:
        print(f"Chat AI V2 import error: {e}")
        return jsonify({
            'success': False,
            'answer': "❌ وحدة المساعد الذكي غير متاحة حالياً.\n\n📢 يرجى إبلاغ المطور @Alshabany_Ai."
        }), 500
        
    except Exception as e:
        print(f"AI Chat error: {e}")
        return jsonify({
            'success': False,
            'answer': "🤖 عذراً، حدث خطأ في المساعد الذكي.\n\n💡 يمكنك المحاولة لاحقاً."
        }), 500


# ========== API لتقييم الإجابة (تعلم ذاتي) ==========
@app.route('/api/rate-answer', methods=['POST'])
@token_required
def rate_answer(user_id):  # ✅ أضف user_id
    """تقييم إجابة المساعد الذكي لتحسين التعلم"""
    try:
        data = request.get_json()
        conversation_id = data.get('conversation_id')
        was_helpful = data.get('was_helpful')
        
        if not conversation_id:
            return jsonify({'success': False, 'error': 'معرف المحادثة مطلوب'}), 400
        
        from utils.chat_ai_v2 import rate_chat_answer
        result = rate_chat_answer(conversation_id, was_helpful)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Rate answer error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ========== API إحصائيات المساعد الذكي ==========
@app.route('/api/chat-stats', methods=['GET'])
@token_required
def chat_stats(user_id):  # ✅ أضف user_id
    """إحصائيات استخدام المساعد الذكي للمستخدم"""
    try:
        user_id_str = str(user_id)
        
        from utils.chat_ai_v2 import get_user_chat_stats
        
        stats = get_user_chat_stats(user_id_str) if 'get_user_chat_stats' in dir() else {}
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        print(f"Chat stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ========== API فحص توافر اليوزرنيم على يوتيوب ==========
@app.route('/api/check-username', methods=['POST'])
@token_required
def check_username_api(user_id):
    """
    API لفحص توافر اسم مستخدم على يوتيوب
    متاح فقط للمستخدمين المميزين
    """
    from utils.username_checker import check_single_platform
    from utils.db import get_user_info
    import asyncio
    
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        
        if not username:
            return jsonify({'success': False, 'error': 'اسم المستخدم مطلوب'}), 400
        
        # تنظيف الاسم من @ والمسافات
        username = username.replace('@', '').replace(' ', '').replace('/', '')
        
        if len(username) < 3:
            return jsonify({'success': False, 'error': 'اسم المستخدم يجب أن يكون 3 أحرف على الأقل'}), 400
        
        if len(username) > 30:
            return jsonify({'success': False, 'error': 'اسم المستخدم طويل جداً (الحد الأقصى 30 حرف)'}), 400
        
        # التحقق من أن المستخدم مميز
        user_info = get_user_info(user_id)
        if not user_info or user_info.get('status') != 'premium':
            return jsonify({
                'success': False, 
                'error': '💎 هذه الميزة متاحة فقط للمستخدمين المميزين!\n\nللاشتراك، تواصل مع المطور @Alshabany_Ai'
            }), 403
        
                # استدعاء دالة فحص اليوزرنيم (متوافقة مع async)
        result = asyncio.run(check_single_platform(username, platform='youtube'))
        
        # معالجة النتيجة حسب الهيكل الموجود في username_checker.py
        if result.get('status') == 'available':
            return jsonify({
                'success': True,
                'available': True,
                'username': username,
                'message': f'✅ اسم المستخدم @{username} متاح! يمكنك استخدام هذا الاسم.',
                'detail': result.get('detail', '')
            })
        elif result.get('status') == 'taken':
            return jsonify({
                'success': True,
                'available': False,
                'username': username,
                'message': f'❌ اسم المستخدم @{username} غير متاح. يرجى اختيار اسم آخر.',
                'detail': result.get('detail', '')
            })
        elif result.get('status') == 'error':
            return jsonify({
                'success': False,
                'error': result.get('detail', 'حدث خطأ أثناء الفحص')
            }), 500
        else:
            return jsonify({
                'success': False,
                'error': result.get('detail', 'لم نتمكن من التحقق من الاسم')
            }), 500
            
    except ImportError as e:
        print(f"❌ Username checker import error: {e}")
        return jsonify({
            'success': False,
            'error': '⚠️ وحدة فحص اليوزرنيم غير متاحة حالياً. يرجى إبلاغ المطور.'
        }), 500
    except Exception as e:
        print(f"❌ Username check error: {e}")
        return jsonify({
            'success': False,
            'error': f'حدث خطأ: {str(e)}'
        }), 500
# ================================================================================
@app.route('/api/send-recommendation-to-bot', methods=['POST'])
def send_recommendation_to_bot():
    """إرسال توصية كملف نصي إلى البوت"""
    from utils.helpers import verify_token
    import io
    from telegram import InputFile
    
    data = request.get_json()
    token = data.get('token')
    recommendation_id = data.get('recommendation_id')
    
    if not token or not recommendation_id:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400
    
    user_id = verify_token(token)
    if not user_id:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    # جلب التوصية من قاعدة البيانات
    response = supabase.table('recommendations_history')\
        .select('recommendation_text, account_identifier')\
        .eq('id', recommendation_id)\
        .eq('user_id', user_id)\
        .execute()
    
    if not response.data:
        return jsonify({'success': False, 'error': 'Recommendation not found'}), 404
    
    rec = response.data[0]
    recommendation_text = rec.get('recommendation_text', '')
    account_name = rec.get('account_identifier', 'توصية')
    
    BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    if not BOT_TOKEN:
        return jsonify({'success': False, 'error': 'Bot token not configured'}), 500
    
    now = datetime.now()
    filename = f"توصية_{account_name}_{now.strftime('%Y%m%d_%H%M%S')}.txt"
    
    # إرسال الملف
    files = {'document': (filename, recommendation_text.encode('utf-8'), 'text/plain')}
    data = {'chat_id': user_id, 'caption': f"🤖 توصية ذكاء اصطناعي لـ {account_name}"}
    
    response = requests.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument',
        data=data,
        files=files,
        timeout=60
    )
    
    if response.status_code == 200:
        return jsonify({'success': True, 'message': 'تم إرسال التوصية إلى البوت'})
    else:
        return jsonify({'success': False, 'error': 'Failed to send'}), 500
# =================================================================================
@app.route('/api/prices')
def get_prices():
    """جلب جميع الأسعار والإعدادات للدفع"""
    try:
        prices = get_all_prices()  # من utils.db
        return jsonify({'success': True, **prices})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
# =================================================================================
# القسم 29: تشغيل التطبيق (Main)
# =================================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Flask Server for Social Media Analyzer Bot")
    print(f"📁 Static files served from: /static/")
    print(f"🎨 Themes served from: /static/themes/")
    print(f"📄 Bio page available at: /bio/<page_url>")
    print(f"💳 Payment page available at: /payment")
    print(f"🔐 Admin login: /secure/x7K9mP2/login")
    print(f"🛡️ Admin dashboard: /admin/dashboard")
    print(f"🌐 Running on port: {PORT}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=PORT, debug=False)
