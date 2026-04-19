# -*- coding: utf-8 -*-
"""
================================================================================
اسم البوت: Social Media Analyzer Bot
الوصف: بوت تحليل حسابات السوشيال ميديا (يوتيوب، انستقرام، تيك توك، فيسبوك)
المطور: @E_Alshabany
التاريخ: 2026
================================================================================
"""

import os
import sys
import logging
import threading
import asyncio
from datetime import datetime, date, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
from flask import Flask, request, render_template, jsonify

# إضافة مجلد utils إلى المسار
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.db import (
    get_or_create_user, get_user_info, get_user_usage,
    increment_usage, can_analyze, get_remaining_analyses, get_total_analyses,
    get_user_social_accounts, get_user_account, save_user_account, delete_user_account,
    can_use_gemini, increment_gemini_usage,
    get_bio_page, create_or_update_bio_page, disable_bio_page, get_bio_page_by_page_url, increment_bio_views,
    update_bio_theme, update_bio_text, update_bio_avatar, add_custom_link, remove_custom_link
)
from utils.youtube_analyzer import get_channel_details, format_channel_report
from utils.gemini_ai import get_channel_recommendations, get_username_recommendations
from utils.helpers import escape_html

# =================================================================================
# القسم 1: خادم HTTP (لإبقاء السيرفر نشطاً على Render)
# =================================================================================

flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
@flask_app.route('/healthcheck')
def health_check():
    """نقطة نهاية للتحقق من صحة الخدمة"""
    return jsonify({"status": "ok", "bot": "running"}), 200

@flask_app.route('/bot_status')
def bot_status():
    """نقطة نهاية لعرض حالة البوت"""
    return jsonify({
        "status": "running",
        "bot_name": os.environ.get('BOT_NAME', 'social_analyzer'),
        "free_limit": int(os.environ.get('FREE_LIMIT', '2')),
        "uptime": datetime.now().isoformat()
    }), 200

def run_flask():
    """تشغيل خادم Flask في منفذ منفصل"""
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# تشغيل Flask في thread منفصل (قبل بدء البوت)
threading.Thread(target=run_flask, daemon=True).start()

# =================================================================================
# القسم 2: متغيرات البيئة والإعدادات الأساسية
# =================================================================================

TOKEN = os.environ.get('TELEGRAM_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
BOT_NAME = os.environ.get('BOT_NAME', 'social_analyzer')
FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '2'))
HUB_BOT_URL = os.environ.get('HUB_BOT_URL', 'https://t.me/SocMed_tools_bot')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', '7850462368')
RENDER_URL = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')

if not TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ: تأكد من تعيين المتغيرات المطلوبة")
    exit(1)

# إعدادات logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =================================================================================
# القسم 3: ثوابت المحادثة (ConversationHandler)
# =================================================================================

(ASK_NAME, ASK_YOUTUBE, ASK_INSTAGRAM, ASK_TIKTOK, ASK_FACEBOOK) = range(5)

# تخزين مؤقت لبيانات المستخدم أثناء التسجيل
user_registration_data = {}

# =================================================================================
# القسم 4: دوال المساعدة (Helper Functions)
# =================================================================================

def get_platform_icon(platform):
    """الحصول على أيقونة المنصة"""
    icons = {
        'youtube': '🎬',
        'instagram': '📸',
        'tiktok': '🎵',
        'facebook': '📘'
    }
    return icons.get(platform, '🔗')

# =================================================================================
# القسم 5: لوحات المفاتيح (Keyboards)
# =================================================================================

def get_main_keyboard(is_premium=False):
    """لوحة المفاتيح الرئيسية"""
    keyboard = [
        [KeyboardButton("🎯 تحليل حساباتي"), KeyboardButton("📊 إحصائياتي")],
        [KeyboardButton("📝 بياناتي"), KeyboardButton("✏️ تعديل بياناتي")],
        [KeyboardButton("💎 اشتراك مميز"), KeyboardButton("ℹ️ المساعدة")]
    ]
    if is_premium:
        keyboard.insert(2, [KeyboardButton("📄 صفحة البايو"), KeyboardButton("🔍 فحص يوزرنيم")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_analysis_keyboard():
    """لوحة اختيار منصة التحليل"""
    keyboard = [
        [InlineKeyboardButton("🎬 يوتيوب", callback_data="analyze_youtube")],
        [InlineKeyboardButton("📸 انستقرام (قريباً)", callback_data="analyze_instagram")],
        [InlineKeyboardButton("🎵 تيك توك (قريباً)", callback_data="analyze_tiktok")],
        [InlineKeyboardButton("📘 فيسبوك (قريباً)", callback_data="analyze_facebook")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_premium_keyboard():
    """لوحة الاشتراك المميز"""
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💎 اشتراك مميز - 10$ مدى الحياة", web_app=WebAppInfo(url=f"https://{RENDER_URL}/payment"))
    ]])
    return keyboard

# =================================================================================
# القسم 6: أوامر البوت - التسجيل (Registration Commands)
# =================================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء البوت وتسجيل المستخدم"""
    user = update.effective_user
    
    user_data = get_or_create_user(
        user.id,
        user.first_name,
        user.username or "",
        user.language_code or ""
    )
    
    if not user_data:
        await update.message.reply_text("❌ حدث خطأ، يرجى المحاولة لاحقاً")
        return ConversationHandler.END
    
    accounts = get_user_social_accounts(user.id)
    
    if accounts:
        is_premium = user_data['status'] == 'premium'
        remaining = get_remaining_analyses(user.id)
        total = get_total_analyses(user.id)
        
        if is_premium:
            status_text = "👑 مميز"
            limit_text = "غير محدود"
        else:
            status_text = "🎁 مجاني"
            limit_text = f"{remaining}/{FREE_LIMIT}"
        
        welcome_text = f"""
🌐 <b>مرحباً بعودتك {user.first_name}!</b>

💎 <b>حالتك:</b> {status_text}
📊 <b>التحليلات المتبقية اليوم:</b> {limit_text}
📈 <b>إجمالي التحليلات:</b> {total}

📱 <b>حساباتك المسجلة:</b>
"""
        for platform, acc in accounts.items():
            welcome_text += f"• {get_platform_icon(platform)} {platform.capitalize()}: @{acc['account_identifier']}\n"
        
        welcome_text += """
🎯 <b>ماذا تريد أن تفعل؟</b>
• اضغط على 🎯 تحليل حساباتي
• أو استخدم الأزرار أدناه
"""
        await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=get_main_keyboard(is_premium))
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            f"🌐 <b>مرحباً بك {user.first_name} في بوت تحليل الحسابات الاجتماعية!</b>\n\n"
            f"📊 <b>ماذا يمكنني أن أفعل؟</b>\n"
            f"• تحليل قنوات يوتيوب\n"
            f"• تحليل حسابات انستقرام (قريباً)\n"
            f"• تحليل حسابات تيك توك (قريباً)\n"
            f"• تحليل حسابات فيسبوك (قريباً)\n\n"
            f"💰 <b>الخطة المجانية:</b> {FREE_LIMIT} تحليل يومياً\n"
            f"👑 <b>الخطة المميزة:</b> 10$ مدى الحياة (غير محدود)\n\n"
            f"📝 <b>لنبدأ بتسجيل بياناتك...</b>\n\n"
            f"ما هو الاسم الذي تريد أن أناديك به؟",
            parse_mode='HTML'
        )
        return ASK_NAME

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء التسجيل"""
    user_id = update.effective_user.id
    if user_id in user_registration_data:
        del user_registration_data[user_id]
    await update.message.reply_text(
        "❌ تم إلغاء التسجيل.\n\n"
        "يمكنك البدء من جديد بإرسال /start",
        reply_markup=get_main_keyboard(False)
    )
    return ConversationHandler.END

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال الاسم"""
    user_id = update.effective_user.id
    name = update.message.text.strip()
    user_registration_data[user_id] = {'display_name': name}
    await update.message.reply_text(
        f"✅ تم حفظ اسمك: {escape_html(name)}\n\n"
        f"📺 الآن أدخل معرف قناتك على يوتيوب أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany أو https://youtube.com/@E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة",
        parse_mode='HTML'
    )
    return ASK_YOUTUBE

async def skip_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تجاوز إدخال يوتيوب"""
    user_id = update.effective_user.id
    if user_id in user_registration_data:
        user_registration_data[user_id]['youtube'] = None
    await update.message.reply_text("⏭️ تم تجاوز إضافة حساب يوتيوب\n\n📸 الآن أدخل معرف حسابك على انستقرام...")
    return ASK_INSTAGRAM

async def ask_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب يوتيوب"""
    user_id = update.effective_user.id
    youtube_input = update.message.text.strip()
    if user_id in user_registration_data:
        user_registration_data[user_id]['youtube'] = youtube_input
    await update.message.reply_text(
        f"✅ تم إضافة حساب يوتيوب: {escape_html(youtube_input)}\n\n📸 الآن أدخل معرف حسابك على انستقرام...",
        parse_mode='HTML'
    )
    return ASK_INSTAGRAM

async def skip_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تجاوز إدخال انستقرام"""
    user_id = update.effective_user.id
    if user_id in user_registration_data:
        user_registration_data[user_id]['instagram'] = None
    await update.message.reply_text("⏭️ تم تجاوز إضافة حساب انستقرام\n\n🎵 الآن أدخل معرف حسابك على تيك توك...")
    return ASK_TIKTOK

async def ask_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب انستقرام"""
    user_id = update.effective_user.id
    instagram_input = update.message.text.strip()
    if user_id in user_registration_data:
        user_registration_data[user_id]['instagram'] = instagram_input
    await update.message.reply_text(
        f"✅ تم إضافة حساب انستقرام: {escape_html(instagram_input)}\n\n🎵 الآن أدخل معرف حسابك على تيك توك...",
        parse_mode='HTML'
    )
    return ASK_TIKTOK

async def skip_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تجاوز إدخال تيك توك"""
    user_id = update.effective_user.id
    if user_id in user_registration_data:
        user_registration_data[user_id]['tiktok'] = None
    await update.message.reply_text("⏭️ تم تجاوز إضافة حساب تيك توك\n\n📘 الآن أدخل معرف حسابك على فيسبوك...")
    return ASK_FACEBOOK

async def ask_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب تيك توك"""
    user_id = update.effective_user.id
    tiktok_input = update.message.text.strip()
    if user_id in user_registration_data:
        user_registration_data[user_id]['tiktok'] = tiktok_input
    await update.message.reply_text(
        f"✅ تم إضافة حساب تيك توك: {escape_html(tiktok_input)}\n\n📘 الآن أدخل معرف حسابك على فيسبوك...",
        parse_mode='HTML'
    )
    return ASK_FACEBOOK

async def skip_facebook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تجاوز إدخال فيسبوك وإنهاء التسجيل"""
    user_id = update.effective_user.id
    data = user_registration_data.get(user_id, {})
    user = update.effective_user
    
    accounts_to_save = [
        ('youtube', data.get('youtube')),
        ('instagram', data.get('instagram')),
        ('tiktok', data.get('tiktok')),
        ('facebook', data.get('facebook'))
    ]
    for platform, identifier in accounts_to_save:
        if identifier:
            save_user_account(user.id, platform, identifier)
    
    if user_id in user_registration_data:
        del user_registration_data[user_id]
    
    accounts = get_user_social_accounts(user.id)
    summary = f"✅ <b>تم تسجيل بياناتك بنجاح!</b>\n\n📊 <b>ملخص حساباتك:</b>\n"
    for platform, acc in accounts.items():
        summary += f"• {get_platform_icon(platform)} {platform.capitalize()}: @{acc['account_identifier']}\n"
    summary += f"\n💰 <b>خطتك الحالية:</b> مجانية ({FREE_LIMIT} تحليل يومياً)\n"
    summary += f"💎 <b>للبحث غير المحدود:</b> /premium\n\n🎯 <b>للبدء، اضغط على 🎯 تحليل حساباتي</b>"
    await update.message.reply_text(summary, parse_mode='HTML', reply_markup=get_main_keyboard(False))
    return ConversationHandler.END

async def ask_facebook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب فيسبوك وإنهاء التسجيل"""
    user_id = update.effective_user.id
    facebook_input = update.message.text.strip()
    data = user_registration_data.get(user_id, {})
    data['facebook'] = facebook_input
    user = update.effective_user
    
    accounts_to_save = [
        ('youtube', data.get('youtube')),
        ('instagram', data.get('instagram')),
        ('tiktok', data.get('tiktok')),
        ('facebook', facebook_input)
    ]
    for platform, identifier in accounts_to_save:
        if identifier:
            save_user_account(user.id, platform, identifier)
    
    if user_id in user_registration_data:
        del user_registration_data[user_id]
    
    accounts = get_user_social_accounts(user.id)
    summary = f"✅ <b>تم تسجيل بياناتك بنجاح!</b>\n\n📊 <b>ملخص حساباتك:</b>\n"
    for platform, acc in accounts.items():
        summary += f"• {get_platform_icon(platform)} {platform.capitalize()}: @{acc['account_identifier']}\n"
    summary += f"\n💰 <b>خطتك الحالية:</b> مجانية ({FREE_LIMIT} تحليل يومياً)\n"
    summary += f"💎 <b>للبحث غير المحدود:</b> /premium\n\n🎯 <b>للبدء، اضغط على 🎯 تحليل حساباتي</b>"
    await update.message.reply_text(summary, parse_mode='HTML', reply_markup=get_main_keyboard(False))
    return ConversationHandler.END

# =================================================================================
# القسم 7: أوامر البوت - عرض البيانات والإحصائيات
# =================================================================================

async def my_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض بيانات المستخدم"""
    user_id = update.effective_user.id
    accounts = get_user_social_accounts(user_id)
    
    if not accounts:
        await update.message.reply_text("❌ لم تقم بتسجيل أي حسابات بعد.\n\nللتسجيل، أرسل /start", reply_markup=get_main_keyboard(False))
        return
    
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    text = f"📝 <b>بياناتي الشخصية</b>\n\n"
    text += f"👤 <b>الاسم:</b> {user_info['first_name'] if user_info else '-'}\n"
    text += f"🆔 <b>المعرف:</b> @{user_info['username'] if user_info else '-'}\n"
    text += f"💎 <b>الخطة:</b> {'👑 مميز' if is_premium else '🎁 مجاني'}\n\n"
    text += f"📱 <b>حساباتي المسجلة:</b>\n"
    
    for platform, acc in accounts.items():
        text += f"• {get_platform_icon(platform)} {platform.capitalize()}: @{acc['account_identifier']}\n"
    
    if is_premium:
        bio_page = get_bio_page(user_id)
        if bio_page and bio_page.get('is_enabled'):
            text += f"\n📄 <b>صفحة البايو:</b>\n🔗 https://{RENDER_URL}/bio/{bio_page['page_url']}"
    
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=get_main_keyboard(is_premium))

async def my_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات المستخدم"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    remaining = get_remaining_analyses(user_id)
    total = get_total_analyses(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if is_premium:
        gemini_usage = can_use_gemini(user_id)
        gemini_remaining = gemini_usage[1] if isinstance(gemini_usage, tuple) and len(gemini_usage) > 1 else 0
        text = f"""
📊 <b>إحصائياتي الشخصية</b>

👤 <b>المستخدم:</b> {user_info['first_name'] if user_info else '-'}
💎 <b>نوع الخطة:</b> 👑 مميز
📈 <b>إجمالي التحليلات:</b> {total}
🤖 <b>توصيات AI المتبقية اليوم:</b> {gemini_remaining}/5
📄 <b>صفحة البايو:</b> ✅ مفعلة
🔍 <b>فحص اليوزرنيم:</b> ✅ متاح
"""
    else:
        text = f"""
📊 <b>إحصائياتي الشخصية</b>

👤 <b>المستخدم:</b> {user_info['first_name'] if user_info else '-'}
💎 <b>نوع الخطة:</b> 🎁 مجاني
📊 <b>التحليلات المتبقية اليوم:</b> {remaining}/{FREE_LIMIT}
📈 <b>إجمالي التحليلات:</b> {total}
💎 <b>للترقية إلى خطة مميزة:</b> /premium
"""
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=get_main_keyboard(is_premium))

# =================================================================================
# القسم 8: أوامر البوت - الاشتراك المميز والمساعدة
# =================================================================================

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معلومات الاشتراك المميز - خطط متعددة"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    # جلب الأسعار من قاعدة البيانات
    from utils.db import get_all_prices
    prices = get_all_prices()
    print(f"DEBUG: الأسعار المقروءة = {prices}")
    # التحقق من وجود عروض ترويجية
    promo_text = ""
    if prices.get('promo_active', False):
        promo_text = f"\n🎉 <b>عرض خاص!</b>\n• نصف سنوي: {prices['promo_half_yearly']}$ فقط\n• سنوي: {prices['promo_yearly']}$ فقط\n"
    
    if is_premium:
        # جلب الاشتراك النشط
        from utils.db import get_user_active_subscription
        subscription = get_user_active_subscription(user_id)
        
        sub_text = ""
        if subscription:
            plan_name = subscription.get('subscription_plans_social', {}).get('name_ar', 'مميز')
            end_date = subscription.get('end_date', '')
            sub_text = f"\n📅 <b>خطتك:</b> {plan_name}\n⏰ <b>تنتهي في:</b> {end_date}\n"
        
        text = f"""
👑 <b>أنت مشترك في الخطة المميزة!</b>
{sub_text}
✅ <b>مميزات الاشتراك المميز:</b>
• تحليل غير محدود لجميع الحسابات
• توصيات الذكاء الاصطناعي (5 يومياً)
• صفحة بايو شخصية
• فحص توافر اليوزرنيم
• دعم أولوية في المعالجة

📅 <b>الاشتراك نشط حالياً</b>

شكراً لدعمك! 🙏
"""
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=get_main_keyboard(True))
    else:
        remaining = get_remaining_analyses(user_id)
        
        text = f"""
💎 <b>الاشتراك المميز</b>

🎁 <b>مميزات الخطة المميزة:</b>
• ✅ تحليل غير محدود
• ✅ توصيات الذكاء الاصطناعي (5 يومياً)
• ✅ صفحة بايو شخصية
• ✅ فحص توافر اليوزرنيم
• ✅ دعم أولوية في المعالجة

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>خطط الاشتراك:</b>

🌙 <b>شهري:</b> {prices.get('price_monthly', 10)}$ / شهر
📅 <b>نصف سنوي:</b> {prices.get('price_half_yearly', 30)}$ (5$ شهرياً)
🎉 <b>سنوي:</b> {prices.get('price_yearly', 48)}$ (4$ شهرياً)
💎 <b>مدى الحياة:</b> {prices.get('price_lifetime', 100)}$ (مرة واحدة)
{promo_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>حالتك الحالية:</b>
• نوع الخطة: مجانية
• التحليلات المتبقية اليوم: {remaining}/{prices.get('free_limit', FREE_LIMIT)}

🔽 <b>للاشتراك، اختر خطتك المفضلة:</b>
"""
        
        # إنشاء أزرار الخطط (ديناميكية من قاعدة البيانات)
        keyboard = [
            [InlineKeyboardButton(f"🌙 شهري - {prices.get('price_monthly', 10)}$", callback_data="subscribe_monthly")],
            [InlineKeyboardButton(f"📅 نصف سنوي - {prices.get('price_half_yearly', 30)}$", callback_data="subscribe_half_yearly")],
            [InlineKeyboardButton(f"🎉 سنوي - {prices.get('price_yearly', 48)}$", callback_data="subscribe_yearly")],
            [InlineKeyboardButton(f"💎 مدى الحياة - {prices.get('price_lifetime', 100)}$", callback_data="subscribe_lifetime")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
        ]
        
        # إضافة زر العرض إذا كان مفعلاً
        if prices.get('promo_active', False):
            keyboard.insert(0, [InlineKeyboardButton(f"🎁 عرض نصف سنوي - {prices.get('promo_half_yearly', 25)}$", callback_data="subscribe_promo")])
        
        await update.message.reply_text(
            text, 
            parse_mode='HTML', 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
async def subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_type):
    """معالجة اختيار خطة الاشتراك"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_info = get_user_info(user_id)
    
    # التحقق من أن المستخدم ليس مشتركاً بالفعل
    if user_info.get('status') == 'premium':
        await query.edit_message_text(
            "✅ أنت مشترك بالفعل في الخطة المميزة!\n\n"
            "لمعرفة تفاصيل اشتراكك، استخدم الأمر /mystats",
            parse_mode='HTML'
        )
        return
    
    # جلب الأسعار
    from utils.db import get_all_prices, get_bot_setting
    prices = get_all_prices()
    print(f"DEBUG: prices from DB = {prices}")
    # تحديد الخطة
    plan_details = {
        'monthly': {'name': 'شهري', 'name_en': 'monthly', 'days': 30, 'price': prices.get('price_monthly', 10)},
        'half_yearly': {'name': 'نصف سنوي', 'name_en': 'half_yearly', 'days': 180, 'price': prices.get('price_half_yearly', 30)},
        'yearly': {'name': 'سنوي', 'name_en': 'yearly', 'days': 365, 'price': prices.get('price_yearly', 48)},
        'lifetime': {'name': 'مدى الحياة', 'name_en': 'lifetime', 'days': 36500, 'price': prices.get('price_lifetime', 100)},
        'promo': {'name': 'نصف سنوي (عرض)', 'name_en': 'half_yearly', 'days': 180, 'price': prices.get('promo_half_yearly', 25)}
    }
    
    plan = plan_details.get(plan_type, plan_details['half_yearly'])
    
    # رابط الدفع
    payment_url = f"https://{RENDER_URL}/payment?plan={plan_type}&amount={plan['price']}"
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💳 إتمام الدفع", web_app=WebAppInfo(url=payment_url))
    ]])
    
    await query.edit_message_text(
        f"💎 <b>تفاصيل اشتراكك</b>\n\n"
        f"📅 <b>الخطة:</b> {plan['name']}\n"
        f"💰 <b>السعر:</b> {plan['price']}$\n"
        f"⏰ <b>المدة:</b> {plan['days']} يوماً\n\n"
        f"✅ <b>مميزات الخطة:</b>\n"
        f"• تحليل غير محدود لجميع المنصات\n"
        f"• توصيات الذكاء الاصطناعي\n"
        f"• صفحة بايو شخصية\n\n"
        f"🔽 <b>لإتمام الاشتراك، اضغط على زر الدفع أدناه:</b>\n\n"
        f"⚠️ بعد الدفع، تواصل مع المطور @E_Alshabany لإرسال إيصال الدفع وتفعيل اشتراكك.",
        parse_mode='HTML',
        reply_markup=keyboard
    )
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعليمات المساعدة"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    help_text = f"""
🆘 <b>مساعدة بوت تحليل الحسابات الاجتماعية</b>

🔹 <b>لتحليل حساب:</b> اضغط على زر 🎯 تحليل حساباتي
🔹 <b>للتسجيل أو تعديل البيانات:</b> اضغط على 📝 بياناتي أو ✏️ تعديل بياناتي

💰 <b>نظام الاستخدام:</b>
• الخطة المجانية: {FREE_LIMIT} تحليل يومياً
• الخطة المميزة: غير محدود

📋 <b>الأوامر:</b>
/start - بدء الاستخدام
/help - هذه المساعدة
/mystats - إحصائياتي الشخصية
/premium - الاشتراك المميز
/mydata - عرض بياناتي
/edit - تعديل بياناتي

👨‍💻 <b>المطور:</b> @E_Alshabany
"""
    # إنشاء لوحة مفاتيح مدمجة
    keyboard = [
        [InlineKeyboardButton("📋 سياسة الخصوصية", url="https://social-analyzer-flask.onrender.com/privacy")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
    ]
    
    await update.message.reply_text(
        help_text, 
        parse_mode='HTML', 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =================================================================================
# القسم 9: أوامر البوت - التحليل (Analysis Commands)
# =================================================================================

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية التحليل"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    accounts = get_user_social_accounts(user_id)
    
    if not accounts:
        await update.message.reply_text(
            "❌ لم تقم بتسجيل أي حسابات بعد.\n\nللتسجيل، أرسل /start",
            reply_markup=get_main_keyboard(is_premium)
        )
        return
    
    can_analyze_bool, current_uses = can_analyze(user_id)
    
    if not is_premium and not can_analyze_bool:
        remaining = FREE_LIMIT - current_uses
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("💎 اشتراك مميز - 10$ مدى الحياة", web_app=WebAppInfo(url=f"https://{RENDER_URL}/payment"))
        ]])
        
        await update.message.reply_text(
            f"⚠️ <b>لقد وصلت للحد اليومي المجاني!</b>\n\n"
            f"📊 <b>الحد المسموح:</b> {FREE_LIMIT} تحليل يومياً\n"
            f"✅ <b>التحليلات اليوم:</b> {current_uses}\n"
            f"🎯 <b>المتبقي اليوم:</b> {remaining}\n\n"
            f"💎 <b>للتحليل غير المحدود والمميزات الإضافية:</b>\n"
            f"• تحليل غير محدود\n"
            f"• توصيات الذكاء الاصطناعي\n"
            f"• صفحة بايو شخصية\n"
            f"• فحص توافر اليوزرنيم\n\n"
            f"🔽 <b>اشترك الآن في الخطة المميزة:</b>",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return
    
    await update.message.reply_text(
        "🎯 <b>اختر المنصة التي تريد تحليلها:</b>",
        parse_mode='HTML',
        reply_markup=get_analysis_keyboard()
    )

async def analyze_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    """تحليل قناة يوتيوب (نسخة محسنة وشاملة مع حفظ التحليلات)"""
    user_id = update.effective_user.id if not query else query.from_user.id
    
    if query:
        await query.answer()
        message = query.message
    else:
        message = update.message
    
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    # ========== التحقق من الحد اليومي للمجانيين ==========
    if not is_premium:
        can_analyze_bool, current_uses = can_analyze(user_id)
        if not can_analyze_bool:
            payment_url = f"https://{RENDER_URL}/payment"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 اشتراك مميز - 10$ مدى الحياة", web_app=WebAppInfo(url=payment_url))
            ]])
            await message.reply_text(
                f"⚠️ <b>لقد وصلت للحد اليومي المجاني!</b>\n\n"
                f"📊 <b>الحد المسموح:</b> {FREE_LIMIT} تحليل يومياً\n"
                f"✅ <b>التحليلات اليوم:</b> {current_uses}\n"
                f"🎯 <b>المتبقي اليوم:</b> {FREE_LIMIT - current_uses}\n\n"
                f"💎 <b>مميزات الخطة المميزة:</b>\n"
                f"• تحليل غير محدود لجميع الحسابات\n"
                f"• توصيات الذكاء الاصطناعي (5 يومياً)\n"
                f"• صفحة بايو شخصية\n"
                f"• فحص توافر اليوزرنيم\n\n"
                f"🔽 <b>للتحليل غير المحدود، اشترك الآن:</b>",
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return
    
    # جلب حساب يوتيوب المسجل
    youtube_account = get_user_account(user_id, 'youtube')
    
    if not youtube_account:
        await message.reply_text(
            "❌ لم تقم بتسجيل حساب يوتيوب بعد.\n\nللتسجيل، أرسل /start ثم اتبع التعليمات",
            reply_markup=get_main_keyboard(is_premium)
        )
        return
    
    status_msg = await message.reply_text("⏳ جاري تحليل القناة...")
    
    # تحليل القناة
    channel_details, error = await get_channel_details(youtube_account['account_identifier'])
    
    if error:
        await status_msg.edit_text(f"❌ حدث خطأ: {error}")
        return
    
    if not channel_details:
        await status_msg.edit_text("❌ لم يتم العثور على القناة")
        return
    
    # ========== حساب المقاييس المتقدمة ==========
    def parse_count(value):
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            value = value.lower().replace('m', '000000').replace('k', '000')
            try:
                return int(float(value))
            except:
                return 0
        return 0
    
    subscribers = parse_count(channel_details.get('subscribers', 0))
    total_views = parse_count(channel_details.get('total_views', 0))
    total_videos = parse_count(channel_details.get('total_videos', 0))
    
    # حساب متوسط المشاهدات
    avg_views = total_views // total_videos if total_videos > 0 else 0
    
    # حساب نسبة التفاعل المقدرة
    engagement_rate = round((avg_views / subscribers * 100), 2) if subscribers > 0 else 0
    
    # تحليل أوقات النشر (من أحدث الفيديوهات)
    best_hour = None
    best_day = None
    posting_times = []
    
    for video in channel_details.get('latest_videos', [])[:10]:
        published_at = video.get('published_at', '')
        if published_at:
            try:
                dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                posting_times.append({
                    'hour': dt.hour,
                    'day': dt.strftime('%A'),
                    'date': dt
                })
            except:
                pass
    
    if posting_times:
        hour_counts = {}
        day_counts = {}
        for pt in posting_times:
            hour_counts[pt['hour']] = hour_counts.get(pt['hour'], 0) + 1
            day_counts[pt['day']] = day_counts.get(pt['day'], 0) + 1
        
        if hour_counts:
            best_hour = max(hour_counts, key=hour_counts.get)
        if day_counts:
            best_day = max(day_counts, key=day_counts.get)
    
    # متوسط طول الفيديو (تقديري)
    avg_video_duration = 600  # افتراضي 10 دقائق
    
    # ========== حفظ التحليلات في قاعدة البيانات ==========
    account_identifier = youtube_account['account_identifier']
    account_name = channel_details.get('title', '')
    
    # تجهيز بيانات التحليل
    analysis_data = {
        'subscribers': subscribers,
        'followers': subscribers,
        'total_views': total_views,
        'total_videos': total_videos,
        'total_posts': total_videos,
        'avg_views_per_post': avg_views,
        'avg_video_duration': avg_video_duration,
        'engagement_rate': engagement_rate,
        'best_posting_hour': best_hour,
        'best_posting_day': best_day,
        'top_posts': channel_details.get('latest_videos', [])[:5],
        'account_name': account_name
    }
    
    # ========== ✅ الدالة 1: حفظ التحليل الأول (مرة واحدة فقط) ==========
    from utils.db import save_first_analysis, update_latest_analysis, get_analyses_for_ai, calculate_growth_metrics
    save_first_analysis(user_id, 'youtube', account_identifier, account_name, analysis_data)
    
    # ========== ✅ الدالة 2: تحديث آخر تحليل (في كل مرة) ==========
    update_latest_analysis(user_id, 'youtube', account_identifier, account_name, analysis_data)
    
    # ========== زيادة عدد الاستخدامات ==========
    remaining = get_remaining_analyses(user_id) if not is_premium else None
    increment_usage(user_id, 'youtube', {
        'account_name': channel_details['title'],
        'subscribers': channel_details['subscribers'],
        'total_posts': channel_details['total_videos'],
        'top_posts': channel_details['latest_videos'][:5],
        'duration': 0
    })
    
    # إضافة إحصائيات متقدمة للتقرير
    from utils.helpers import format_number
    channel_details['avg_views'] = format_number(avg_views)
    channel_details['engagement_rate'] = f"{engagement_rate}%"
    channel_details['best_posting_hour'] = best_hour
    channel_details['best_posting_day'] = best_day
    
    # تنسيق التقرير
    message_text, file_data = format_channel_report(
        channel_details, user_id, is_premium, remaining
    )
    
    await status_msg.delete()
    
    if file_data:
        file_content, filename = file_data
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(file_content)
        
        await message.reply_text(message_text, parse_mode='HTML')
        
        with open(filename, 'rb') as f:
            await message.reply_document(
                document=f,
                filename=filename,
                caption="📊 ملف التحليل الكامل"
            )
        
        os.remove(filename)
    else:
        await message.reply_text(message_text, parse_mode='HTML')
    
    # ========== عرض توصيات الذكاء الاصطناعي للمميزين ==========
    if is_premium:
        # ========== ✅ الدالة 3: جلب التحليلات للذكاء الاصطناعي ==========
        analyses = get_analyses_for_ai(user_id, 'youtube', account_identifier)
        
        # ========== ✅ الدالة 4: حساب مقاييس النمو ==========
        growth_metrics = calculate_growth_metrics(
            analyses.get('first'), 
            analyses.get('latest_analyses', [None])[0] if analyses.get('latest_analyses') else None
        )
        
        # إضافة مقاييس النمو
        channel_details['growth_metrics'] = growth_metrics
        channel_details['has_history'] = analyses.get('first') is not None
        
        # رسالة توضيحية محسنة
        ai_message = "🤖 <b>توصيات الذكاء الاصطناعي</b>\n\n"
        if growth_metrics.get('subscribers_growth', 0) != 0:
            ai_message += f"📊 <b>التطور منذ آخر تحليل:</b>\n"
            ai_message += f"👥 المشتركين: +{growth_metrics.get('subscribers_growth', 0):,} ({growth_metrics.get('subscribers_percent', 0)}%)\n"
            ai_message += f"👁️ المشاهدات: +{growth_metrics.get('views_growth', 0):,} ({growth_metrics.get('views_percent', 0)}%)\n"
            ai_message += f"📹 الفيديوهات: +{growth_metrics.get('posts_growth', 0):,}\n\n"
        ai_message += "✨ هل تريد الحصول على توصيات مخصصة لتحسين قناتك؟"
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🤖 احصل على توصيات ذكية", callback_data=f"ai_recommendations_{channel_details['channel_id']}")
        ]])
        await message.reply_text(
            ai_message,
            parse_mode='HTML',
            reply_markup=keyboard
        )
# =================================================================================
# دوال مساعدة (Helper Functions)
# =================================================================================

def generate_simple_chart(value, max_value=10000000):
    """توليد رسم بياني بسيط بالنص"""
    try:
        if isinstance(value, str):
            value = value.replace('M', '000000').replace('K', '000').replace('.', '')
            value = int(value) if value.isdigit() else 0
        else:
            value = int(value)
        percentage = min(100, int((value / max_value) * 100)) if max_value > 0 else 0
        filled = int(percentage / 10)
        empty = 10 - filled
        return f"📊 {value:,} مشاهدة: {'█' * filled}{'░' * empty} {percentage}%"
    except:
        return f"📊 {value} مشاهدة: ████████░░ 80%"


# ثم بعدها دالة ai_recommendations

# =================================================================================
# القسم 10: أوامر البوت - توصيات الذكاء الاصطناعي (AI Recommendations)
# =================================================================================

async def ai_recommendations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تقديم توصيات الذكاء الاصطناعي (نسخة متقدمة مع تحليل تاريخي وذاكرة)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    channel_id = query.data.split('_')[-1]
    
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if not is_premium:
        await query.edit_message_text(
            "💎 هذه الميزة متاحة فقط للمستخدمين المميزين!\n\nللاشتراك: /premium"
        )
        return
    
    # التحقق من صلاحية استخدام Gemini
    can_use, remaining, error_msg = can_use_gemini(user_id)
    
    if not can_use:
        await query.edit_message_text(error_msg)
        return
    
    # جلب تفاصيل القناة
    youtube_account = get_user_account(user_id, 'youtube')
    if not youtube_account:
        await query.edit_message_text("❌ لم يتم العثور على حساب يوتيوب مسجل")
        return
    
    channel_details, _ = await get_channel_details(youtube_account['account_identifier'])
    
    if not channel_details:
        await query.edit_message_text("❌ لم يتم العثور على القناة")
        return
    
    # ========== جلب التحليلات التاريخية ==========
    from utils.db import get_analyses_for_ai, calculate_growth_metrics, get_previous_recommendations, save_recommendation
    
    account_identifier = youtube_account['account_identifier']
    analyses = get_analyses_for_ai(user_id, 'youtube', account_identifier)
    
    first_analysis = analyses.get('first')
    latest_analyses = analyses.get('latest_analyses', [])
    
    # حساب مقاييس النمو
    growth_metrics = calculate_growth_metrics(first_analysis, latest_analyses[0] if latest_analyses else None)
    
    # ========== جلب التوصيات السابقة (جديد) ==========
    previous_recommendations = get_previous_recommendations(user_id, 'youtube', account_identifier, limit=3)
    
    # ========== تحليل إضافي للمحتوى ==========
    video_titles = [v.get('title', '') for v in channel_details.get('latest_videos', [])[:5]]
    
    # تحليل فئات المحتوى من العناوين
    content_categories = []
    keywords = {
        'تعليم': ['تعلم', 'درس', 'شرح', 'كيف', 'دورة', 'مهارة'],
        'ترفيه': ['كوميدي', 'ضحك', 'مزح', 'تحدي', 'لعبة'],
        'أخبار': ['خبر', 'حدث', 'عاجل', 'تطور', 'إعلان'],
        'تكنولوجيا': ['هاتف', 'كمبيوتر', 'تطبيق', 'برنامج', 'تقنية', 'AI'],
        'رياضة': ['مباراة', 'هدف', 'فريق', 'بطل', 'كأس'],
        'طبخ': ['وصفة', 'أكلة', 'طبخ', 'مطبخ', 'سناك'],
        'سفر': ['رحلة', 'سفر', 'مكان', 'وجهة', 'سياحة']
    }
    
    for title in video_titles:
        title_lower = title.lower()
        for category, words in keywords.items():
            if any(word in title_lower for word in words):
                content_categories.append(category)
                break
    
    from collections import Counter
    top_category = Counter(content_categories).most_common(1)[0][0] if content_categories else None
    
    # ========== تحليل أوقات النشر ==========
    posting_times = []
    for video in channel_details.get('latest_videos', [])[:10]:
        published_at = video.get('published_at', '')
        if published_at:
            try:
                dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                posting_times.append(dt.hour)
            except:
                pass
    
    best_hour = Counter(posting_times).most_common(1)[0][0] if posting_times else None
    
    # ========== بناء نص التوصيات السابقة للمقارنة ==========
    previous_rec_text = ""
    if previous_recommendations:
        previous_rec_text = "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📜 **التوصيات السابقة وتأثيرها:**\n"
        for i, rec in enumerate(previous_recommendations[:3], 1):
            status = "✅ تم التنفيذ" if rec.get('implemented') else "⏳ قيد الانتظار"
            previous_rec_text += f"\n**التوصية {i}** ({rec.get('created_at')[:10] if rec.get('created_at') else 'تاريخ غير معروف'}): {status}\n"
            previous_rec_text += f"📝 {rec.get('recommendation_summary', '')[:200]}...\n"
            if rec.get('impact_score'):
                previous_rec_text += f"📊 الأثر المقدر: {rec.get('impact_score')}/10\n"
    
    # ========== إعداد الـ Prompt المتقدم (مفصل بدون اختصار) ==========
    await query.edit_message_text("🤖 جاري تحليل بيانات قناتك وتوليد توصيات ذكية ومفصلة...")
    
    # زيادة عدد استخدامات Gemini
    increment_gemini_usage(user_id)
    
    # بناء الـ Prompt المحسن (مفصل)
    prompt = f"""
أنت خبير استراتيجي في تحسين قنوات يوتيوب وتحليل أدائها. بناءً على البيانات التالية، قدم توصيات ذكية ومخصصة **بشكل مفصل**:

⚠️ **تعليمات مهمة:**
1. استخدم الرموز التعبيرية بكثرة (📊 📈 🎯 💡 ⚠️ ✅ 🚀)
2. رتب التوصيات كنقاط مرقمة
3. اشرح بالتفصيل، لا تختصر
4. قارن مع التوصيات السابقة إن وجدت

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 معلومات القناة
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• الاسم: {channel_details.get('title', 'غير معروف')}
• تاريخ الإنشاء: {channel_details.get('published_at', 'غير معروف')}
• البلد: {channel_details.get('country', 'غير محدد')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 الإحصائيات الحالية
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• المشتركين: {channel_details.get('subscribers', '0')}
• إجمالي المشاهدات: {channel_details.get('total_views', '0')}
• عدد الفيديوهات: {channel_details.get('total_videos', '0')}
• متوسط المشاهدات لكل فيديو: {channel_details.get('avg_views', '0')}

📈 **رسم بياني بسيط للمشاهدات:**
{generate_simple_chart(channel_details.get('total_views', '0'), 10000000)}

{previous_rec_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 تطور القناة (مقارنة مع أول تحليل)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• نمو المشتركين: +{growth_metrics.get('subscribers_growth', 0):,} ({growth_metrics.get('subscribers_percent', 0)}%)
• نمو المشاهدات: +{growth_metrics.get('views_growth', 0):,} ({growth_metrics.get('views_percent', 0)}%)
• الفترة الزمنية: {growth_metrics.get('analysis_period_days', 0)} يوماً
• نسبة التفاعل المقدرة: {channel_details.get('engagement_rate', '0')}

📊 **رسم بياني للنمو:**
المشتركين قبل: {'█' * min(10, int(growth_metrics.get('subscribers_percent', 0)/10)) if growth_metrics.get('subscribers_percent', 0) > 0 else '░░░░░░░░░░'} {growth_metrics.get('subscribers_percent', 0)}%
المشتركين بعد: {'█' * min(10, int(growth_metrics.get('subscribers_percent', 0)/10) + 2) if growth_metrics.get('subscribers_percent', 0) > 0 else '█░░░░░░░░░'} 

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 تحليل المحتوى
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• عناوين الفيديوهات الأخيرة: {', '.join(video_titles[:3])}
• الفئة الأكثر شيوعاً: {top_category or 'غير محدد'}
• أفضل وقت للنشر: {best_hour}:00 أو {best_hour+1}:00

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

قدم توصياتك في هذه المجالات (اشرح بالتفصيل، لا تختصر، 6-8 نقاط):

1️⃣ **تحسين المحتوى** - بناءً على فئة القناة وعناوين الفيديوهات
2️⃣ **استراتيجية النشر** - بناءً على أوقات النشر وأيامه
3️⃣ **نمو الجمهور** - بناءً على معدل نمو المشتركين
4️⃣ **تحسين نسبة المشاهدة** - نصائح لزيادة الاحتفاظ بالمشاهدين
5️⃣ **مقارنة مع التوصيات السابقة** - هل نفذتها؟ ماذا تغير؟
6️⃣ **أخطاء شائعة يجب تجنبها** - بناءً على البيانات المتاحة
7️⃣ **خطوات محددة للشهر القادم** - أهداف قابلة للتحقيق
8️⃣ **نصيحة أخيرة وتشجيعية**

**أضف في النهاية سؤالاً للمستخدم مثل:**
"📌 هل قمت بتنفيذ أي من التوصيات السابقة؟ إذا لم تنفذها، ما السبب؟ سأساعدك في تخطي العقبات."

استخدم اللغة العربية البسيطة، والرموز التعبيرية بكثرة، والرسوم البيانية النصية البسيطة.
"""
    
        # ========== استدعاء Gemini API ==========
    from utils.gemini_ai import get_advanced_recommendations
    
    recommendations = await get_advanced_recommendations(channel_details, prompt)
    
    # ========== التحقق من أن التوصيات غير فارغة ==========
    if not recommendations or len(recommendations) < 50:
        recommendations = "⚠️ عذراً، لم يتمكن الذكاء الاصطناعي من توليد توصيات في هذا الوقت. يرجى المحاولة مرة أخرى لاحقاً."
    
    # ========== استخراج النقاط الرئيسية ==========
    key_points = []
    lines = recommendations.split('\n')
    for line in lines:
        line_stripped = line.strip()
        if line_stripped.startswith(('1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '•', '-', '📌', '✅', '⚠️', '💡')):
            key_points.append(line_stripped[:200])
    
    # ========== حفظ التوصية في قاعدة البيانات ==========
    saved_rec = save_recommendation(user_id, 'youtube', account_identifier, recommendations, key_points[:5])
    
    # ========== إرسال التوصية كملف نصي (مع التأكد من وجود المحتوى) ==========
    import io
    from telegram import InputFile
    
    # تأكد من أن recommendations غير فارغة
    if not recommendations or recommendations.strip() == "":
        recommendations = "لم يتمكن الذكاء الاصطناعي من توليد توصيات. يرجى المحاولة مرة أخرى."
    
    # تنسيق الملف النصي
    file_content = f"""╔══════════════════════════════════════════════════════════════════╗
║                    توصيات الذكاء الاصطناعي المفصلة                     ║
╚══════════════════════════════════════════════════════════════════╝

📺 القناة: {channel_details.get('title', 'غير معروف')}
📅 تاريخ التحليل: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🆔 معرف التوصية: {saved_rec.get('id', 'N/A') if saved_rec else 'N/A'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **ملخص سريع:**
• المشتركين: {channel_details.get('subscribers', '0')}
• المشاهدات: {channel_details.get('total_views', '0')}
• النمو منذ آخر تحليل: +{growth_metrics.get('subscribers_growth', 0):,} مشترك ({growth_metrics.get('subscribers_percent', 0)}%)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 **التوصيات المفصلة:**

{recommendations}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 **كيف تستفيد من هذه التوصيات؟**
1. اقرأ التوصيات بعناية
2. اختر 2-3 توصيات للبدء بها
3. رجع لي بعد أسبوعين لإعادة التقييم
4. أخبرني إذا نفذت أي توصية لأرى التحسن

📊 **المتبقي اليوم:** {remaining - 1}/5 توصيات
💎 **مستوى التوصية:** متقدم (تحليل تاريخي + ذاكرة)

💬 **للتواصل مع المطور:** @E_Alshabany

تم التحليل بواسطة Social Media Analyzer Bot
"""
    
    # طباعة للتأكد من وجود المحتوى (للتشخيص)
    print(f"DEBUG: recommendations length = {len(recommendations)}")
    print(f"DEBUG: file_content length = {len(file_content)}")
    
    # إرسال رسالة تعريفية قبل الملف
    await query.edit_message_text(
        f"🤖 <b>توصيات الذكاء الاصطناعي المفصلة</b>\n\n"
        f"📊 تم تحليل قناتك <b>{channel_details.get('title')}</b> بنجاح!\n"
        f"📈 {growth_metrics.get('subscribers_growth', 0):,} مشترك جديد ({growth_metrics.get('subscribers_percent', 0)}% نمو)\n\n"
        f"📄 تم إرسال <b>{len(recommendations)}</b> حرف من التوصيات المفصلة في ملف نصي.\n\n"
        f"📌 <b>المتبقي اليوم:</b> {remaining - 1}/5 توصيات\n"
        f"💎 <b>مستوى التوصية:</b> متقدم (تحليل تاريخي + ذاكرة)\n\n"
        f"💡 <b>نصيحة:</b> احفظ الملف للرجوع إليه لاحقاً!",
        parse_mode='HTML'
    )
    
    # إرسال الملف
    bio_file = io.BytesIO(file_content.encode('utf-8'))
    bio_file.name = f"توصيات_{channel_details.get('title', 'قناة')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    await query.message.reply_document(
        document=InputFile(bio_file, filename=bio_file.name),
        caption=f"📄 توصيات قناة {channel_details.get('title')} - {datetime.now().strftime('%Y-%m-%d')}"
    )


def generate_simple_chart(value, max_value=10000000):
    """توليد رسم بياني بسيط بالنص"""
    try:
        value = int(value)
        percentage = min(100, int((value / max_value) * 100)) if max_value > 0 else 0
        filled = int(percentage / 10)
        empty = 10 - filled
        return f"📊 {value:,} مشاهدة: {'█' * filled}{'░' * empty} {percentage}%"
    except:
        return f"📊 {value} مشاهدة: ████████░░ 80%"



# =================================================================================
# القسم 11: أوامر البوت - صفحة البايو (Bio Page)
# =================================================================================

async def bio_page_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء صفحة البايو أو عرض بياناتها"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if not is_premium:
        await update.message.reply_text(
            "💎 <b>صفحة البايو</b>\n\n"
            "هذه الميزة متاحة فقط للمستخدمين المميزين!\n\n"
            "للاشتراك: /premium",
            parse_mode='HTML'
        )
        return
    
    accounts = get_user_social_accounts(user_id)
    
    if not accounts:
        await update.message.reply_text(
            "❌ لم تقم بتسجيل أي حسابات بعد.\n\n"
            "للتسجيل، أرسل /start",
            parse_mode='HTML'
        )
        return
    
    existing_bio = get_bio_page(user_id)
    flask_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
    
    if existing_bio:
        page_url = existing_bio.get('page_url')
        full_url = f"https://{flask_url}/bio/{page_url}"
        bio_text = existing_bio.get('bio', 'لا يوجد')
        avatar = existing_bio.get('avatar_url', 'غير محددة')
        views = existing_bio.get('views_count', 0)
        theme = existing_bio.get('theme_name', 'default')
        theme_display = 'فاتح' if theme == 'default' else 'داكن'
        
        text = f"""
📄 <b>صفحة البايو الخاصة بك</b>

✅ لديك صفحة بايو نشطة بالفعل!

🔗 <b>رابط صفحتك:</b>
{full_url}

📊 <b>إحصائيات صفحتك:</b>
👁️ عدد المشاهدات: {views}
🎨 الثيم الحالي: {theme_display}

📝 <b>النبذة الحالية:</b>
{bio_text[:200]}{'...' if len(bio_text) > 200 else ''}

🖼️ <b>الصورة الشخصية:</b>
{'✅ محددة' if avatar and avatar != 'غير محددة' else '❌ غير محددة'}

⚙️ <b>لتعديل صفحة البايو:</b>
• اضغط على زر ✏️ تعديل بياناتي
• اختر ⚙️ إعدادات صفحة البايو
• يمكنك تغيير:
  - 🎨 الثيم
  - 📝 النبذة
  - 🖼️ الصورة الشخصية

💡 <b>ملاحظة:</b> أي تغييرات تقوم بها تظهر فوراً على الرابط أعلاه
"""
        await update.message.reply_text(text, parse_mode='HTML')
    else:
        formatted_accounts = {}
        for platform, acc in accounts.items():
            formatted_accounts[platform] = {
                'account_identifier': acc['account_identifier']
            }
        
        display_name = user_info.get('first_name', 'مستخدم')
        page_url = create_or_update_bio_page(user_id, display_name, formatted_accounts)
        
        if page_url:
            full_url = f"https://{flask_url}/bio/{page_url}"
            
            text = f"""
📄 <b>صفحة البايو الخاصة بك</b>

✅ تم إنشاء صفحتك بنجاح!

🔗 <b>رابط صفحتك:</b>
{full_url}

📱 <b>يمكنك:</b>
• مشاركة الرابط مع أصدقائك
• وضع الرابط في سيرتك الذاتية
• استخدامه للترويج لحساباتك

⚙️ <b>لتعديل صفحة البايو:</b>
• اضغط على زر ✏️ تعديل بياناتي
• اختر ⚙️ إعدادات صفحة البايو
• يمكنك تغيير:
  - 🎨 الثيم (فاتح/داكن)
  - 📝 النبذة (وصف تعريف عنك)
  - 🖼️ الصورة الشخصية

👁️ <b>سيتم احتساب المشاهدات</b> تلقائياً عند فتح الرابط
"""
            await update.message.reply_text(text, parse_mode='HTML')
        else:
            await update.message.reply_text(
                "❌ حدث خطأ في إنشاء صفحة البايو. حاول مرة أخرى لاحقاً.",
                parse_mode='HTML'
            )

# =================================================================================
# القسم 12: أوامر البوت - إدارة صفحة البايو (Bio Management)
# =================================================================================

async def edit_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل بيانات المستخدم"""
    user_id = update.effective_user.id
    accounts = get_user_social_accounts(user_id)
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    all_platforms = ['youtube', 'instagram', 'tiktok', 'facebook']
    keyboard = []
    
    for platform in all_platforms:
        if platform in accounts:
            keyboard.append([InlineKeyboardButton(
                f"✏️ تعديل {platform.capitalize()} ✅", 
                callback_data=f"edit_{platform}"
            )])
        else:
            keyboard.append([InlineKeyboardButton(
                f"➕ إضافة {platform.capitalize()}", 
                callback_data=f"add_{platform}"
            )])
    
    keyboard.append([InlineKeyboardButton(
        f"✏️ تعديل اسم العرض (الحالي: {user_info.get('first_name', 'غير محدد')[:20]})", 
        callback_data="edit_display_name"
    )])
    
    if is_premium:
        keyboard.append([InlineKeyboardButton("⚙️ إعدادات صفحة البايو", callback_data="bio_settings")])
    
    keyboard.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")])
    
    await update.message.reply_text(
        "✏️ <b>إدارة حساباتي</b>\n\n"
        "📌 <b>الحسابات الموجودة:</b> تظهر مع علامة ✅ ويمكن تعديلها\n"
        "📌 <b>الحسابات غير المضاف:</b> تظهر مع علامة ➕ ويمكن إضافتها\n\n"
        "👤 <b>اسم العرض:</b> هو الاسم الذي يظهر في صفحة البايو\n"
        "💡 يمكنك تغييره في أي وقت من الزر أدناه\n\n"
        "🔽 <b>اختر ما تريد:</b>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_edit_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة تعديل الحساب"""
    platform = context.user_data.get('editing_platform')
    if not platform:
        return
    
    user_id = update.effective_user.id
    new_identifier = update.message.text.strip()
    
    delete_user_account(user_id, platform)
    save_user_account(user_id, platform, new_identifier)
    
    context.user_data.pop('editing_platform', None)
    
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    await update.message.reply_text(
        f"✅ تم تحديث حساب {platform.capitalize()} إلى: {escape_html(new_identifier)}",
        parse_mode='HTML',
        reply_markup=get_main_keyboard(is_premium)
    )

# =================================================================================
# القسم 13: دوال إضافة حسابات جديدة وتعديل الاسم
# =================================================================================

async def add_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية إضافة حساب جديد"""
    query = update.callback_query
    await query.answer()
    
    platform = query.data.split('_')[1]
    context.user_data['adding_platform'] = platform
    
    keyboard = [[InlineKeyboardButton("🔙 إلغاء", callback_data="main_menu")]]
    
    await query.edit_message_text(
        f"➕ <b>إضافة حساب {platform.capitalize()}</b>\n\n"
        f"أرسل معرف حسابك على {platform.capitalize()}:\n\n"
        f"💡 مثال: @username أو https://{platform}.com/username\n\n"
        f"📌 ملاحظة: سيتم إضافة الحساب إلى صفحة البايو الخاصة بك فوراً.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إضافة حساب جديد"""
    platform = context.user_data.get('adding_platform')
    if not platform:
        return
    
    user_id = update.effective_user.id
    new_identifier = update.message.text.strip()
    
    save_user_account(user_id, platform, new_identifier)
    
    context.user_data.pop('adding_platform', None)
    
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if is_premium:
        accounts = get_user_social_accounts(user_id)
        formatted_accounts = {}
        for plat, acc in accounts.items():
            formatted_accounts[plat] = {
                'account_identifier': acc['account_identifier']
            }
        display_name = user_info.get('first_name', 'مستخدم')
        create_or_update_bio_page(user_id, display_name, formatted_accounts)
    
    await update.message.reply_text(
        f"✅ <b>تم إضافة حساب {platform.capitalize()} بنجاح!</b>\n\n"
        f"📌 المعرف: {escape_html(new_identifier)}\n\n"
        f"💡 يمكنك تعديله أو حذفه في أي وقت من قائمة تعديل البيانات.",
        parse_mode='HTML',
        reply_markup=get_main_keyboard(is_premium)
    )

async def edit_display_name_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية تعديل اسم العرض"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_info = get_user_info(user_id)
    current_name = user_info.get('first_name', '')
    
    context.user_data['editing_display_name'] = True
    
    keyboard = [[InlineKeyboardButton("🔙 إلغاء", callback_data="main_menu")]]
    
    await query.edit_message_text(
        f"✏️ <b>تعديل اسم العرض</b>\n\n"
        f"👤 <b>الاسم الحالي:</b> {current_name}\n\n"
        f"أرسل الاسم الجديد الذي تريد ظهوره في صفحة البايو:\n\n"
        f"💡 مثال: أحمد محمد | Ahmed\n\n"
        f"📌 ملاحظة: هذا الاسم سيظهر في صفحة البايو فقط، ولن يؤثر على اسم حسابك في تلجرام.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_display_name_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة تعديل اسم العرض"""
    if not context.user_data.get('editing_display_name'):
        return
    
    user_id = update.effective_user.id
    new_name = update.message.text.strip()
    
    if not new_name:
        await update.message.reply_text("❌ الاسم لا يمكن أن يكون فارغاً. حاول مرة أخرى.")
        return
    
    from utils.db import supabase
    result = supabase.table('users').update({
        'first_name': new_name,
        'updated_at': datetime.now().isoformat()
    }).eq('user_id', user_id).execute()
    
    if result.data:
        context.user_data.pop('editing_display_name', None)
        
        user_info = get_user_info(user_id)
        if user_info.get('status') == 'premium':
            accounts = get_user_social_accounts(user_id)
            formatted_accounts = {}
            for platform, acc in accounts.items():
                formatted_accounts[platform] = {
                    'account_identifier': acc['account_identifier']
                }
            create_or_update_bio_page(user_id, new_name, formatted_accounts)
        
        await update.message.reply_text(
            f"✅ <b>تم تحديث اسم العرض بنجاح!</b>\n\n"
            f"👤 الاسم الجديد: {escape_html(new_name)}\n\n"
            f"💡 سيظهر هذا الاسم في صفحة البايو الخاصة بك.",
            parse_mode='HTML'
        )
        
        user_info = get_user_info(user_id)
        is_premium = user_info['status'] == 'premium' if user_info else False
        await update.message.reply_text(
            "🏠 <b>القائمة الرئيسية</b>\n\nاختر ما تريد:",
            parse_mode='HTML',
            reply_markup=get_main_keyboard(is_premium)
        )
    else:
        await update.message.reply_text("❌ حدث خطأ في تحديث الاسم. حاول مرة أخرى.")

# =================================================================================
# القسم 14: إعدادات صفحة البايو (Bio Settings)
# =================================================================================

async def bio_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعدادات صفحة البايو (للمستخدمين المميزين فقط)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if not is_premium:
        await query.edit_message_text("💎 هذه الميزة متاحة فقط للمستخدمين المميزين!")
        return
    
    bio_page = get_bio_page(user_id)
    if not bio_page:
        await query.edit_message_text("❌ لم يتم العثور على صفحة البايو. اضغط على '📄 صفحة البايو' أولاً.")
        return
    
    current_theme = bio_page.get('theme_name', 'default')
    current_bio = bio_page.get('bio', 'لا يوجد')
    current_avatar = bio_page.get('avatar_url', None)
    
    # جلب جميع الثيمات المتاحة
    from utils.db import get_all_themes
    all_themes = get_all_themes()
    
    bio_preview = current_bio[:40] + "..." if len(current_bio) > 40 else current_bio
    
    # بناء قائمة أزرار الثيمات
    keyboard = []
    for theme in all_themes:
        theme_name = theme.get('name')
        theme_display = theme.get('display_name', theme_name.capitalize())
        is_current = (theme_name == current_theme)
        # علامة ✅ بجانب الثيم الحالي
        display_text = f"{'✅ ' if is_current else '   '}{theme_display}"
        keyboard.append([InlineKeyboardButton(display_text, callback_data=f"bio_set_theme_{theme_name}")])
    
    # إضافة باقي الأزرار
    keyboard.extend([
        [InlineKeyboardButton(f"📝 تعديل النبذة ({bio_preview})", callback_data="bio_edit_bio")],
        [InlineKeyboardButton(f"🖼️ تغيير الصورة الشخصية {'✅' if current_avatar else '❌'}", callback_data="bio_edit_avatar")],
        [InlineKeyboardButton("🔄 إعادة تعيين (مسح النبذة والصورة)", callback_data="bio_reset_page_warning")],
        [InlineKeyboardButton("🔗 إنشاء رابط جديد للصفحة", callback_data="bio_reset_url_warning")],
        [InlineKeyboardButton("🗑️ حذف صفحة البايو بالكامل", callback_data="bio_delete_page_warning")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]
    ])
    
    page_url = bio_page.get('page_url')
    flask_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
    full_url = f"https://{flask_url}/bio/{page_url}"
    
    await query.edit_message_text(
        f"⚙️ <b>إعدادات صفحة البايو</b>\n\n"
        f"🔗 <b>رابط صفحتك:</b>\n"
        f"<code>{full_url}</code>\n\n"
        f"📊 <b>الإعدادات الحالية:</b>\n"
        f"📝 النبذة: {bio_preview}\n"
        f"🖼️ الصورة الشخصية: {'موجودة ✅' if current_avatar else 'غير محددة ❌'}\n"
        f"👁️ المشاهدات: {bio_page.get('views_count', 0)}\n\n"
        f"🎨 <b>اختر الثيم المفضل لديك:</b>\n"
        f"💡 اضغط على أي ثيم لتغييره فوراً\n\n"
        f"⚠️ <b>تنبيه:</b> الإجراءات التالية تتطلب تأكيداً إضافياً:\n"
        f"• إعادة تعيين (مسح النبذة والصورة)\n"
        f"• إنشاء رابط جديد (سيوقف الرابط القديم)\n"
        f"• حذف الصفحة بالكامل (نهائي)\n\n"
        f"💡 اختر ما تريد تعديله:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =================================================================================
# القسم 15: دوال تعديل النبذة والصورة الشخصية
# =================================================================================

async def bio_edit_bio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية تعديل النبذة"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    bio_page = get_bio_page(user_id)
    if not bio_page:
        await query.edit_message_text("❌ لم يتم العثور على صفحة البايو. اضغط على '📄 صفحة البايو' أولاً.")
        return
    
    context.user_data['editing_bio_text'] = True
    
    keyboard = [[InlineKeyboardButton("🔙 إلغاء", callback_data="bio_settings")]]
    
    await query.edit_message_text(
        "📝 <b>تعديل النبذة</b>\n\n"
        "أرسل النص الجديد للنبذة (الوصف الشخصي):\n\n"
        "💡 مثال: مبرمج ومطور ويب | مهتم بالذكاء الاصطناعي\n\n"
        "📌 ملاحظة: يمكنك استخدام الإيموجي والرموز",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def bio_edit_avatar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية تغيير الصورة الشخصية"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    bio_page = get_bio_page(user_id)
    if not bio_page:
        await query.edit_message_text("❌ لم يتم العثور على صفحة البايو.")
        return
    
    context.user_data['editing_avatar'] = True
    
    keyboard = [[InlineKeyboardButton("🔙 إلغاء", callback_data="bio_cancel_edit")]]
    
    await query.edit_message_text(
        "🖼️ <b>تغيير الصورة الشخصية</b>\n\n"
        "أرسل رابط الصورة الجديدة (URL):\n\n"
        "💡 مثال: https://example.com/my-photo.jpg\n\n"
        "📌 ملاحظات:\n"
        "• يجب أن يكون الرابط عاماً (يبدأ بـ http:// أو https://)\n"
        "• يفضل استخدام صور من Imgur أو أي خدمة استضافة صور\n\n"
        "🔘 أو اضغط على زر إلغاء للخروج",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_bio_text_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة النبذة المرسلة من المستخدم"""
    if not context.user_data.get('editing_bio_text'):
        return
    
    user_id = update.effective_user.id
    new_bio = update.message.text.strip()
    
    if update_bio_text(user_id, new_bio):
        context.user_data.pop('editing_bio_text', None)
        await update.message.reply_text("✅ تم تحديث النبذة بنجاح!")
        await show_bio_management(update, context, user_id)
    else:
        await update.message.reply_text("❌ حدث خطأ في تحديث النبذة. حاول مرة أخرى.")

async def handle_avatar_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة رابط الصورة المرسل من المستخدم"""
    if not context.user_data.get('editing_avatar'):
        return
    
    user_id = update.effective_user.id
    avatar_url = update.message.text.strip()
    
    if not avatar_url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ الرابط غير صالح. يجب أن يبدأ بـ http:// أو https://")
        return
    
    if update_bio_avatar(user_id, avatar_url):
        context.user_data.pop('editing_avatar', None)
        await update.message.reply_text("✅ تم تحديث الصورة الشخصية بنجاح!")
        await show_bio_management(update, context, user_id)
    else:
        await update.message.reply_text("❌ حدث خطأ في تحديث الصورة. حاول مرة أخرى.")

# =================================================================================
# القسم 16: دوال تحذيرية للإجراءات الهامة
# =================================================================================

async def bio_reset_page_warning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحذير قبل إعادة تعيين صفحة البايو"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("✅ نعم، أعد التعيين", callback_data="bio_reset_page")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="bio_settings")]
    ]
    
    await query.edit_message_text(
        "⚠️ <b>تحذير: إعادة تعيين صفحة البايو</b>\n\n"
        "هل أنت متأكد من إعادة تعيين صفحة البايو؟\n\n"
        "📌 ملاحظة: سيتم مسح:\n"
        "• النبذة التعريفية\n"
        "• الصورة الشخصية\n\n"
        "✅ سيتم الاحتفاظ بـ:\n"
        "• رابط الصفحة (لن يتغير)\n"
        "• حسابات التواصل الاجتماعي\n"
        "• إعدادات الثيم\n\n"
        "⚠️ هذا الإجراء يمكن التراجع عنه بإعادة إدخال النبذة والصورة.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def bio_reset_url_warning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحذير قبل إنشاء رابط جديد"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("✅ نعم، أنشئ رابطاً جديداً", callback_data="bio_reset_url")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="bio_settings")]
    ]
    
    await query.edit_message_text(
        "⚠️ <b>تحذير: إنشاء رابط جديد لصفحة البايو</b>\n\n"
        "هل أنت متأكد من إنشاء رابط جديد؟\n\n"
        "📌 ملاحظة مهمة:\n"
        "• سيتم إنشاء رابط جديد تماماً لصفحتك\n"
        "• <b>الرابط القديم سيتوقف عن العمل فوراً</b>\n"
        "• أي شخص لديه الرابط القديم لن يتمكن من الوصول لصفحتك\n"
        "• سيتم الاحتفاظ بجميع بياناتك (النبذة، الصورة، الحسابات)\n\n"
        "⚠️ يرجى نشر الرابط الجديد بعد إنشائه!",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def bio_delete_page_warning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحذير قبل حذف صفحة البايو بالكامل"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("✅ نعم، احذف الصفحة نهائياً", callback_data="bio_delete_page")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="bio_settings")]
    ]
    
    await query.edit_message_text(
        "⚠️ <b>تحذير: حذف صفحة البايو بالكامل</b>\n\n"
        "هل أنت متأكد من حذف صفحة البايو؟\n\n"
        "📌 ملاحظة: سيتم حذف:\n"
        "• الرابط الخاص بالصفحة (نهائياً)\n"
        "• النبذة التعريفية\n"
        "• الصورة الشخصية\n"
        "• جميع الإعدادات\n\n"
        "⚠️ <b>هذا الإجراء لا يمكن التراجع عنه!</b>\n"
        "⚠️ بعد الحذف، ستحتاج إلى إنشاء صفحة جديدة من البداية.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =================================================================================
# القسم 17: دوال التنفيذ الفعلي للإجراءات
# =================================================================================

async def bio_reset_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعادة تعيين صفحة البايو (مسح النبذة والصورة فقط)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    bio_page = get_bio_page(user_id)
    if not bio_page:
        await query.edit_message_text("❌ لم يتم العثور على صفحة البايو.", parse_mode='HTML')
        return
    
    from utils.db import supabase_admin
    
    try:
        supabase_admin.table('bio_pages').update({
            'bio': '',
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        
        supabase_admin.table('bio_pages').update({
            'avatar_url': None,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        
        await query.edit_message_text(
            "✅ <b>تم إعادة تعيين صفحة البايو!</b>\n\n"
            "تم مسح:\n"
            "• النبذة التعريفية\n"
            "• الصورة الشخصية\n\n"
            "يمكنك إضافة نص وصورة جديدة من خلال الإعدادات.",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error in bio_reset_page: {e}")
        await query.edit_message_text(f"❌ حدث خطأ: {e}", parse_mode='HTML')

async def bio_reset_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعادة تعيين رابط صفحة البايو (إنشاء رابط جديد)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_info = get_user_info(user_id)
    accounts = get_user_social_accounts(user_id)
    
    if not accounts:
        await query.edit_message_text("❌ لا توجد حسابات مسجلة.", parse_mode='HTML')
        return
    
    formatted_accounts = {}
    for platform, acc in accounts.items():
        formatted_accounts[platform] = {
            'account_identifier': acc['account_identifier']
        }
    
    display_name = user_info.get('first_name', 'مستخدم')
    
    old_bio = get_bio_page(user_id)
    old_bio_text = old_bio.get('bio', '') if old_bio else ''
    old_avatar = old_bio.get('avatar_url', None) if old_bio else None
    
    from utils.db import supabase_admin
    supabase_admin.table('bio_pages').delete().eq('user_id', user_id).execute()
    
    page_url = create_or_update_bio_page(user_id, display_name, formatted_accounts)
    
    if page_url:
        if old_bio_text:
            update_bio_text(user_id, old_bio_text)
        if old_avatar:
            update_bio_avatar(user_id, old_avatar)
        
        flask_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
        full_url = f"https://{flask_url}/bio/{page_url}"
        
        await query.edit_message_text(
            f"✅ <b>تم إنشاء رابط جديد لصفحة البايو!</b>\n\n"
            f"🔗 <b>الرابط الجديد:</b>\n{full_url}\n\n"
            f"📌 تم الاحتفاظ بنبذتك وصورتك الشخصية.\n"
            f"⚠️ الرابط القديم لم يعد يعمل.",
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text("❌ حدث خطأ في إنشاء رابط جديد.", parse_mode='HTML')

async def bio_delete_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف صفحة البايو بالكامل"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if not is_premium:
        await query.edit_message_text("💎 هذه الميزة متاحة فقط للمستخدمين المميزين!")
        return
    
    try:
        from utils.db import supabase_admin
        supabase_admin.table('bio_pages').delete().eq('user_id', user_id).execute()
        
        await query.edit_message_text(
            "✅ <b>تم حذف صفحة البايو بنجاح!</b>\n\n"
            "📌 <b>ملاحظة:</b>\n"
            "• الرابط القديم لم يعد يعمل\n"
            "• يمكنك إنشاء صفحة جديدة بالضغط على '📄 صفحة البايو' مرة أخرى\n"
            "• سيتم إنشاء رابط جديد تماماً للصفحة الجديدة\n\n"
            "💡 سيتم نقلك إلى القائمة الرئيسية...",
            parse_mode='HTML'
        )
        
        await asyncio.sleep(2)
        await query.message.reply_text(
            "🏠 <b>القائمة الرئيسية</b>\n\nاختر ما تريد:",
            parse_mode='HTML',
            reply_markup=get_main_keyboard(is_premium)
        )
        
    except Exception as e:
        logger.error(f"Error deleting bio page: {e}")
        await query.edit_message_text(f"❌ حدث خطأ أثناء حذف الصفحة: {e}", parse_mode='HTML')

# =================================================================================
# القسم 18: دوال حذف الحسابات الاجتماعية
# =================================================================================

async def delete_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة طلب حذف حساب اجتماعي"""
    query = update.callback_query
    await query.answer()
    
    platform = query.data.split('_')[1]
    context.user_data['deleting_platform'] = platform
    
    keyboard = [
        [InlineKeyboardButton("✅ نعم، احذف الحساب", callback_data=f"confirm_delete_{platform}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_delete_{platform}")]
    ]
    
    await query.edit_message_text(
        f"⚠️ <b>تحذير: حذف حساب {platform.capitalize()}</b>\n\n"
        f"هل أنت متأكد من حذف حساب {platform.capitalize()} من بياناتك؟\n\n"
        f"📌 ملاحظة:\n"
        f"• سيتم إزالة الحساب من صفحة البايو الخاصة بك\n"
        f"• لن يتم حذف حسابك من منصة {platform.capitalize()} نفسها\n"
        f"• يمكنك إعادة إضافته لاحقاً من خلال التعديل\n\n"
        f"⚠️ هذا الإجراء لا يمكن التراجع عنه فورياً!",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد حذف الحساب"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    platform = query.data.split('_')[2]
    
    deletion_success = delete_user_account(user_id, platform)
    
    if not deletion_success:
        await query.edit_message_text(
            f"❌ حدث خطأ أثناء محاولة حذف حساب {platform.capitalize()}.\nالرجاء المحاولة مرة أخرى لاحقاً.",
            parse_mode='HTML'
        )
        return
    
    user_info = get_user_info(user_id)
    all_accounts = get_user_social_accounts(user_id)
    
    formatted_accounts = {}
    for plat, acc in all_accounts.items():
        formatted_accounts[plat] = {
            'account_identifier': acc['account_identifier']
        }
    
    display_name = user_info.get('first_name', 'مستخدم')
    create_or_update_bio_page(user_id, display_name, formatted_accounts)
    
    context.user_data.pop('deleting_platform', None)
    
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    await query.edit_message_text(
        f"✅ <b>تم حذف حساب {platform.capitalize()} بنجاح!</b>\n\n"
        f"تم إزالة الحساب من بياناتك ومن صفحة البايو الخاصة بك.\n\n"
        f"📌 يمكنك إضافة حساب جديد من خلال زر '✏️ تعديل بياناتي' في أي وقت.",
        parse_mode='HTML'
    )
    
    await asyncio.sleep(2)
    await query.message.reply_text(
        "🏠 <b>القائمة الرئيسية</b>\n\nاختر ما تريد:",
        parse_mode='HTML',
        reply_markup=get_main_keyboard(is_premium)
    )

async def cancel_delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء حذف الحساب والعودة إلى قائمة التعديل"""
    query = update.callback_query
    await query.answer()
    
    platform = query.data.split('_')[2]
    context.user_data.pop('deleting_platform', None)
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=f"edit_{platform}")]]
    
    await query.edit_message_text(
        f"✏️ <b>تعديل حساب {platform.capitalize()}</b>\n\n"
        f"أرسل المعرف الجديد أو الرابط:\n\n"
        f"💡 مثال: @username أو https://instagram.com/username",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =================================================================================
# القسم 19: معالج الأزرار (Callback Query Handler)
# =================================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأزرار"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # ----- أزرار التحليل -----
    if data == "analyze_youtube":
        await analyze_youtube(update, context, query)
    elif data == "analyze_instagram":
        await query.answer("📸 هذه الميزة قيد التطوير حالياً", show_alert=True)
    elif data == "analyze_tiktok":
        await query.answer("🎵 هذه الميزة قيد التطوير حالياً", show_alert=True)
    elif data == "analyze_facebook":
        await query.answer("📘 هذه الميزة قيد التطوير حالياً", show_alert=True)
    # ========== أزرار الاشتراك ==========
    elif data == "subscribe_monthly":
        await subscription_callback(update, context, 'monthly')
    elif data == "subscribe_half_yearly":
        await subscription_callback(update, context, 'half_yearly')
    elif data == "subscribe_yearly":
        await subscription_callback(update, context, 'yearly')
    elif data == "subscribe_lifetime":
        await subscription_callback(update, context, 'lifetime')
    elif data == "subscribe_promo":
        await subscription_callback(update, context, 'promo')
 
    # ----- زر القائمة الرئيسية -----
    elif data == "main_menu":
        user_info = get_user_info(user_id)
        is_premium = user_info['status'] == 'premium' if user_info else False
        await query.message.reply_text(
            "🏠 <b>القائمة الرئيسية</b>\n\nاختر ما تريد:",
            parse_mode='HTML',
            reply_markup=get_main_keyboard(is_premium)
        )
        await query.delete_message()
    
    # ----- توصيات الذكاء الاصطناعي -----
    elif data.startswith("ai_recommendations"):
        await ai_recommendations(update, context)
    
    # ========== أزرار إضافة حساب جديد ==========
    elif data.startswith("add_"):
        await add_account_callback(update, context)
    
    # ========== أزرار تعديل اسم العرض ==========
    elif data == "edit_display_name":
        await edit_display_name_callback(update, context)
    
    # ========== أزرار تعديل وحذف الحسابات ==========
    elif data.startswith("edit_"):
        platform = data.split('_')[1]
        context.user_data['editing_platform'] = platform
        keyboard = [
            [InlineKeyboardButton("🗑️ حذف الحساب", callback_data=f"delete_{platform}")],
            [InlineKeyboardButton("🔙 إلغاء", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"✏️ <b>تعديل حساب {platform.capitalize()}</b>\n\n"
            f"📌 <b>للتعديل:</b> أرسل المعرف الجديد أو الرابط\n"
            f"🗑️ <b>لحذف الحساب:</b> اضغط على زر الحذف أدناه\n\n"
            f"💡 مثال: @username أو https://instagram.com/username\n\n"
            f"⚠️ ملاحظة: حذف الحساب يعني إزالته من صفحة البايو الخاصة بك فقط، وليس من المنصة نفسها.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # ----- معالج طلب حذف الحساب -----
    elif data.startswith("delete_"):
        await delete_account_callback(update, context)
    
    # ----- تأكيد حذف الحساب -----
    elif data.startswith("confirm_delete_"):
        await confirm_delete_account(update, context)
    
    # ----- إلغاء حذف الحساب والعودة للتعديل -----
    elif data.startswith("cancel_delete_"):
        await cancel_delete_account(update, context)
    
    # ----- إعدادات صفحة البايو -----
    elif data == "bio_settings":
        await bio_settings_command(update, context)
    elif data == "bio_settings_theme":
        await bio_change_theme_callback(update, context)
    
    # ========== معالج تغيير الثيم من القائمة (الجديد) ==========
    elif data.startswith("bio_set_theme_"):
        theme_name = data.replace("bio_set_theme_", "")
        update_bio_theme(user_id, theme_name)
        await query.answer(f"✅ تم تغيير الثيم إلى {theme_name}")
        await bio_settings_command(update, context)
    
    # ----- أزرار تعديل النبذة والصورة -----
    elif data == "bio_edit_bio":
        await bio_edit_bio_callback(update, context)
    elif data == "bio_edit_avatar":
        await bio_edit_avatar_callback(update, context)
    
    # ----- زر إلغاء التعديل (للصورة) -----
    elif data == "bio_cancel_edit":
        context.user_data.pop('editing_avatar', None)
        context.user_data.pop('editing_bio_text', None)
        await bio_settings_command(update, context)
    
    # ========== أزرار إدارة صفحة البايو (مع التحذير) ==========
    elif data == "bio_reset_page_warning":
        await bio_reset_page_warning(update, context)
    elif data == "bio_reset_url_warning":
        await bio_reset_url_warning(update, context)
    elif data == "bio_delete_page_warning":
        await bio_delete_page_warning(update, context)
    
    # ----- التنفيذ الفعلي للإجراءات -----
    elif data == "bio_reset_page":
        await bio_reset_page(update, context)
    elif data == "bio_reset_url":
        await bio_reset_url(update, context)
    elif data == "bio_delete_page":
        await bio_delete_page(update, context)
    
    # ----- أزرار إدارة صفحة البايو (القديمة) -----
    elif data == "bio_change_theme":
        keyboard = [
            [InlineKeyboardButton("☀️ فاتح", callback_data="bio_set_theme_default")],
            [InlineKeyboardButton("🌙 داكن", callback_data="bio_set_theme_dark")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="bio_back")]
        ]
        await query.edit_message_text(
            "🎨 <b>اختر الثيم المفضل لديك:</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data == "bio_set_theme_default":
        update_bio_theme(user_id, 'default')
        await query.answer("✅ تم تغيير الثيم إلى الفاتح")
        await show_bio_management(update, context, user_id)
    elif data == "bio_set_theme_dark":
        update_bio_theme(user_id, 'dark')
        await query.answer("✅ تم تغيير الثيم إلى الداكن")
        await show_bio_management(update, context, user_id)
    elif data == "bio_show_link":
        bio_page = get_bio_page(user_id)
        if bio_page:
            flask_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
            await query.answer(f"رابط صفحتك: https://{flask_url}/bio/{bio_page['page_url']}", show_alert=True)
    elif data == "bio_back":
        await show_bio_management(update, context, user_id)
    else:
        await query.answer("⚠️ هذا الزر غير مفعل بعد", show_alert=True)

# =================================================================================
# القسم 20: دوال إدارة صفحة البايو (show_bio_management و bio_change_theme)
# =================================================================================

async def show_bio_management(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None):
    """عرض إدارة صفحة البايو"""
    
    if user_id is None:
        if update.callback_query:
            user_id = update.callback_query.from_user.id
        elif update.effective_user:
            user_id = update.effective_user.id
        else:
            await update.message.reply_text("❌ حدث خطأ: لم يتم التعرف على المستخدم")
            return
    
    try:
        user_id = int(user_id)
    except:
        await update.message.reply_text("❌ حدث خطأ: معرف المستخدم غير صالح")
        return
    
    from utils.db import supabase
    
    try:
        response = supabase.table('bio_pages').select('*').eq('user_id', user_id).execute()
        
        if not response.data:
            accounts = get_user_social_accounts(user_id)
            if not accounts:
                await update.message.reply_text("❌ لا توجد حسابات مسجلة. أرسل /start أولاً")
                return
            
            user_info = get_user_info(user_id)
            display_name = user_info.get('first_name', 'مستخدم')
            
            formatted_accounts = {}
            for platform, acc in accounts.items():
                formatted_accounts[platform] = {
                    'account_identifier': acc['account_identifier']
                }
            
            page_url = create_or_update_bio_page(user_id, display_name, formatted_accounts)
            
            if not page_url:
                await update.message.reply_text("❌ حدث خطأ في إنشاء صفحة البايو")
                return
            
            response = supabase.table('bio_pages').select('*').eq('user_id', user_id).execute()
            if not response.data:
                await update.message.reply_text("❌ حدث خطأ في إنشاء صفحة البايو")
                return
        
        bio_page = response.data[0]
        page_url = bio_page.get('page_url')
        theme_name = bio_page.get('theme_name', 'default')
        views_count = bio_page.get('views_count', 0)
        flask_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
        
        def get_theme_display(theme):
            themes = {'default': '☀️ فاتح', 'dark': '🌙 داكن'}
            return themes.get(theme, '☀️ فاتح')
        
        keyboard = [
            [InlineKeyboardButton(f"🎨 الثيم الحالي: {get_theme_display(theme_name)}", callback_data="bio_change_theme")],
            [InlineKeyboardButton("📝 تعديل النبذة", callback_data="bio_edit_bio")],
            [InlineKeyboardButton("🔗 عرض رابط الصفحة", callback_data="bio_show_link")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
        ]
        
        bio_text = bio_page.get('bio', 'لا يوجد')
        if len(bio_text) > 100:
            bio_text = bio_text[:100] + "..."
        
        text = f"""
📄 <b>إدارة صفحة البايو</b>

🔗 <b>رابط صفحتك:</b>
https://{flask_url}/bio/{page_url}

👁️ <b>عدد المشاهدات:</b> {views_count}

🎨 <b>الثيم الحالي:</b> {get_theme_display(theme_name)}

📝 <b>النبذة الحالية:</b>
{bio_text}

💡 يمكنك تعديل أي من الإعدادات أدناه
"""
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
    except Exception as e:
        logger.error(f"Error in show_bio_management: {e}")
        error_msg = f"❌ حدث خطأ: {str(e)[:200]}"
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)

async def bio_change_theme_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغيير ثيم صفحة البايو من داخل البوت"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    bio_page = get_bio_page(user_id)
    
    if not bio_page:
        await query.edit_message_text("❌ لم يتم العثور على صفحة البايو")
        return
    
    current_theme = bio_page.get('theme_name', 'default')
    new_theme = 'dark' if current_theme == 'default' else 'default'
    
    update_bio_theme(user_id, new_theme)
    
    theme_name_display = 'داكن' if new_theme == 'dark' else 'فاتح'
    await query.edit_message_text(
        f"✅ تم تغيير الثيم إلى <b>{theme_name_display}</b> بنجاح!",
        parse_mode='HTML'
    )

# =================================================================================
# القسم 21: معالجة الرسائل النصية والدالة الرئيسية
# =================================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    # إلغاء حالات التعديل عند الضغط على أزرار القائمة
    if text in ["🎯 تحليل حساباتي", "📊 إحصائياتي", "📝 بياناتي", "✏️ تعديل بياناتي", 
                "💎 اشتراك مميز", "ℹ️ المساعدة", "📄 صفحة البايو", "🔍 فحص يوزرنيم"]:
        context.user_data.pop('editing_avatar', None)
        context.user_data.pop('editing_bio_text', None)
        context.user_data.pop('editing_platform', None)
        context.user_data.pop('adding_platform', None)
        context.user_data.pop('editing_display_name', None)
    
    # ----- معالجة إضافة حساب جديد -----
    if context.user_data.get('adding_platform'):
        await handle_add_account(update, context)
        return
    
    # ----- معالجة تعديل اسم العرض -----
    if context.user_data.get('editing_display_name'):
        await handle_display_name_edit(update, context)
        return
    
    # ----- معالجة تعديل النبذة -----
    if context.user_data.get('editing_bio_text'):
        await handle_bio_text_edit(update, context)
        return
    
    # ----- معالجة تغيير الصورة -----
    if context.user_data.get('editing_avatar'):
        await handle_avatar_edit(update, context)
        return
    
    # ----- معالجة الأزرار النصية -----
    if text == "🎯 تحليل حساباتي":
        await analyze_command(update, context)
    elif text == "📊 إحصائياتي":
        await my_stats_command(update, context)
    elif text == "📝 بياناتي":
        await my_data_command(update, context)
    elif text == "✏️ تعديل بياناتي":
        await edit_data_command(update, context)
    elif text == "💎 اشتراك مميز":
        await premium_command(update, context)
    elif text == "ℹ️ المساعدة":
        await help_command(update, context)
    elif text == "📄 صفحة البايو":
        await bio_page_command(update, context)
    elif text == "🔍 فحص يوزرنيم":
        await username_check_command(update, context)
    
    # ----- معالجة تعديل الحساب -----
    elif context.user_data.get('editing_platform'):
        await handle_edit_account(update, context)
    
    # ----- معالجة فحص اليوزرنيم -----
    elif context.user_data.get('awaiting_username'):
        await handle_username_check(update, context)
    
    # ----- رسالة افتراضية -----
    else:
        user_info = get_user_info(user_id)
        is_premium = user_info['status'] == 'premium' if user_info else False
        await update.message.reply_text(
            "❓ عذراً، لم أتعرف على طلبك.\n\n"
            "📌 يمكنك استخدام الأزرار أدناه أو إرسال /help للمساعدة.",
            parse_mode='HTML',
            reply_markup=get_main_keyboard(is_premium)
        )

async def username_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فحص توافر اليوزرنيم"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if not is_premium:
        await update.message.reply_text(
            "🔍 <b>فحص توافر اليوزرنيم</b>\n\n"
            "هذه الميزة متاحة فقط للمستخدمين المميزين!\n\n"
            "للاشتراك: /premium",
            parse_mode='HTML',
            reply_markup=get_premium_keyboard()
        )
        return
    
    await update.message.reply_text(
        "🔍 <b>فحص توافر اليوزرنيم</b>\n\n"
        "أرسل اليوزرنيم الذي تريد التحقق منه (بدون @):",
        parse_mode='HTML'
    )
    context.user_data['awaiting_username'] = True

async def handle_username_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اليوزرنيم المرسل للفحص"""
    if not context.user_data.get('awaiting_username'):
        return
    
    username = update.message.text.strip()
    context.user_data['awaiting_username'] = False
    
    await update.message.reply_text(
        f"🔍 <b>نتيجة فحص اليوزرنيم @{escape_html(username)}</b>\n\n"
        f"📊 <b>النتائج:</b>\n"
        f"• 🎬 يوتيوب: ⏳ قيد التطوير\n"
        f"• 📸 انستقرام: ⏳ قيد التطوير\n"
        f"• 🎵 تيك توك: ⏳ قيد التطوير\n"
        f"• 📘 فيسبوك: ⏳ قيد التطوير\n\n"
        f"💎 <b>هذه الميزة ستعمل قريباً!</b>\n\n"
        f"🚀 <b>قريباً في التحديث القادم</b>",
        parse_mode='HTML'
    )

# =================================================================================
# القسم 22: الدالة الرئيسية (Main Function)
# =================================================================================

def main():
    """تشغيل البوت"""
    application = Application.builder().token(TOKEN).build()
    
    # معالج التسجيل (ConversationHandler)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_YOUTUBE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^/skip$'), ask_youtube),
                CommandHandler("skip", skip_youtube)
            ],
            ASK_INSTAGRAM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^/skip$'), ask_instagram),
                CommandHandler("skip", skip_instagram)
            ],
            ASK_TIKTOK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^/skip$'), ask_tiktok),
                CommandHandler("skip", skip_tiktok)
            ],
            ASK_FACEBOOK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^/skip$'), ask_facebook),
                CommandHandler("skip", skip_facebook)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)]
    )
    
    # إضافة جميع المعالجات
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("mystats", my_stats_command))
    application.add_handler(CommandHandler("premium", premium_command))
    application.add_handler(CommandHandler("mydata", my_data_command))
    application.add_handler(CommandHandler("edit", edit_data_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # طباعة معلومات بدء التشغيل
    print("=" * 60)
    print("📊 Social Media Analyzer Bot - النسخة المميزة")
    print("🤖 @Social_Media_tools_bot")
    print("✅ أوامر: /start /help /mystats /premium /mydata /edit")
    print(f"✅ نظام المدفوعات: مجاني {FREE_LIMIT} تحليل - مميز غير محدود")
    print("✅ قاعدة بيانات: Supabase (متكاملة مع النظام الموحد)")
    print("✅ الذكاء الاصطناعي: Gemini API (قيد التطوير)")
    print("✅ خادم HTTP يعمل على المنفذ", os.environ.get('PORT', 10000))
    print("=" * 60)
    
    # تشغيل البوت
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        timeout=60
    )

# =================================================================================
# نقطة دخول البرنامج (Entry Point)
# =================================================================================

if __name__ == '__main__':
    main()
