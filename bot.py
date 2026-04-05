# -*- coding: utf-8 -*-
"""
Social Media Analyzer Bot - تحليل حسابات السوشيال ميديا
@Social_Media_tools_bot
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

# ========== خادم HTTP لإبقاء السيرفر نشطاً على Render ==========
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

# ========== متغيرات البيئة ==========
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

# ========== ثوابت المحادثة ==========
(ASK_NAME, ASK_YOUTUBE, ASK_INSTAGRAM, ASK_TIKTOK, ASK_FACEBOOK) = range(5)

# تخزين مؤقت لبيانات المستخدم أثناء التسجيل
user_registration_data = {}

# ========== دوال المساعدة ==========

def get_platform_icon(platform):
    """الحصول على أيقونة المنصة"""
    icons = {
        'youtube': '🎬',
        'instagram': '📸',
        'tiktok': '🎵',
        'facebook': '📘'
    }
    return icons.get(platform, '🔗')

# ========== لوحات المفاتيح ==========

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

# ========== أوامر البوت ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء البوت وتسجيل المستخدم"""
    user = update.effective_user
    
    # جلب أو إنشاء المستخدم
    user_data = get_or_create_user(
        user.id,
        user.first_name,
        user.username or "",
        user.language_code or ""
    )
    
    if not user_data:
        await update.message.reply_text("❌ حدث خطأ، يرجى المحاولة لاحقاً")
        return ConversationHandler.END
    
    # التحقق من وجود حسابات مسجلة
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
        # مستخدم جديد - بدء التسجيل
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
    
    await update.message.reply_text(
        f"⏭️ تم تجاوز إضافة حساب يوتيوب\n\n"
        f"📸 الآن أدخل معرف حسابك على انستقرام أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة"
    )
    return ASK_INSTAGRAM


async def ask_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب يوتيوب"""
    user_id = update.effective_user.id
    youtube_input = update.message.text.strip()
    
    if user_id in user_registration_data:
        user_registration_data[user_id]['youtube'] = youtube_input
    
    await update.message.reply_text(
        f"✅ تم إضافة حساب يوتيوب: {escape_html(youtube_input)}\n\n"
        f"📸 الآن أدخل معرف حسابك على انستقرام أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة",
        parse_mode='HTML'
    )
    return ASK_INSTAGRAM


async def skip_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تجاوز إدخال انستقرام"""
    user_id = update.effective_user.id
    if user_id in user_registration_data:
        user_registration_data[user_id]['instagram'] = None
    
    await update.message.reply_text(
        f"⏭️ تم تجاوز إضافة حساب انستقرام\n\n"
        f"🎵 الآن أدخل معرف حسابك على تيك توك أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة"
    )
    return ASK_TIKTOK


async def ask_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب انستقرام"""
    user_id = update.effective_user.id
    instagram_input = update.message.text.strip()
    
    if user_id in user_registration_data:
        user_registration_data[user_id]['instagram'] = instagram_input
    
    await update.message.reply_text(
        f"✅ تم إضافة حساب انستقرام: {escape_html(instagram_input)}\n\n"
        f"🎵 الآن أدخل معرف حسابك على تيك توك أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة",
        parse_mode='HTML'
    )
    return ASK_TIKTOK


async def skip_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تجاوز إدخال تيك توك"""
    user_id = update.effective_user.id
    if user_id in user_registration_data:
        user_registration_data[user_id]['tiktok'] = None
    
    await update.message.reply_text(
        f"⏭️ تم تجاوز إضافة حساب تيك توك\n\n"
        f"📘 الآن أدخل معرف حسابك على فيسبوك أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة"
    )
    return ASK_FACEBOOK


async def ask_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب تيك توك"""
    user_id = update.effective_user.id
    tiktok_input = update.message.text.strip()
    
    if user_id in user_registration_data:
        user_registration_data[user_id]['tiktok'] = tiktok_input
    
    await update.message.reply_text(
        f"✅ تم إضافة حساب تيك توك: {escape_html(tiktok_input)}\n\n"
        f"📘 الآن أدخل معرف حسابك على فيسبوك أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة",
        parse_mode='HTML'
    )
    return ASK_FACEBOOK


async def skip_facebook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تجاوز إدخال فيسبوك"""
    user_id = update.effective_user.id
    data = user_registration_data.get(user_id, {})
    
    # حفظ جميع الحسابات
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
    
    # تنظيف البيانات المؤقتة
    if user_id in user_registration_data:
        del user_registration_data[user_id]
    
    # عرض ملخص الحسابات
    accounts = get_user_social_accounts(user.id)
    summary = f"✅ <b>تم تسجيل بياناتك بنجاح!</b>\n\n📊 <b>ملخص حساباتك:</b>\n"
    for platform, acc in accounts.items():
        summary += f"• {get_platform_icon(platform)} {platform.capitalize()}: @{acc['account_identifier']}\n"
    
    summary += f"\n💰 <b>خطتك الحالية:</b> مجانية ({FREE_LIMIT} تحليل يومياً)\n"
    summary += f"💎 <b>للبحث غير المحدود:</b> /premium\n\n"
    summary += f"🎯 <b>للبدء، اضغط على 🎯 تحليل حساباتي</b>"
    
    await update.message.reply_text(summary, parse_mode='HTML', reply_markup=get_main_keyboard(False))
    return ConversationHandler.END


async def ask_facebook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب فيسبوك وإنهاء التسجيل"""
    user_id = update.effective_user.id
    facebook_input = update.message.text.strip()
    
    data = user_registration_data.get(user_id, {})
    data['facebook'] = facebook_input
    
    # حفظ جميع الح accounts
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
    
    # تنظيف البيانات المؤقتة
    if user_id in user_registration_data:
        del user_registration_data[user_id]
    
    # عرض ملخص الحسابات
    accounts = get_user_social_accounts(user.id)
    summary = f"✅ <b>تم تسجيل بياناتك بنجاح!</b>\n\n📊 <b>ملخص حساباتك:</b>\n"
    for platform, acc in accounts.items():
        summary += f"• {get_platform_icon(platform)} {platform.capitalize()}: @{acc['account_identifier']}\n"
    
    summary += f"\n💰 <b>خطتك الحالية:</b> مجانية ({FREE_LIMIT} تحليل يومياً)\n"
    summary += f"💎 <b>للبحث غير المحدود:</b> /premium\n\n"
    summary += f"🎯 <b>للبدء، اضغط على 🎯 تحليل حساباتي</b>"
    
    await update.message.reply_text(summary, parse_mode='HTML', reply_markup=get_main_keyboard(False))
    return ConversationHandler.END


async def my_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض بيانات المستخدم"""
    user_id = update.effective_user.id
    accounts = get_user_social_accounts(user_id)
    
    if not accounts:
        await update.message.reply_text(
            "❌ لم تقم بتسجيل أي حسابات بعد.\n\n"
            "للتسجيل، أرسل /start",
            reply_markup=get_main_keyboard(False)
        )
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
            text += f"\n📄 <b>صفحة البايو:</b>\n"
            text += f"🔗 https://{RENDER_URL}/bio/{bio_page['page_url']}"
    
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=get_main_keyboard(is_premium))


async def edit_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل بيانات المستخدم"""
    user_id = update.effective_user.id
    accounts = get_user_social_accounts(user_id)
    
    keyboard = []
    for platform in ['youtube', 'instagram', 'tiktok', 'facebook']:
        if platform in accounts:
            keyboard.append([InlineKeyboardButton(f"✏️ تعديل {platform.capitalize()}", callback_data=f"edit_{platform}")])
    
    keyboard.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")])
    
    await update.message.reply_text(
        "✏️ <b>اختر الحساب الذي تريد تعديله:</b>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


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


async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معلومات الاشتراك المميز"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if is_premium:
        text = """
👑 <b>أنت مشترك في الخطة المميزة!</b>

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
• ✅ توصيات الذكاء الاصطناعي
• ✅ صفحة بايو شخصية
• ✅ فحص توافر اليوزرنيم
• ✅ دعم أولوية في المعالجة

💰 <b>السعر:</b>
• <b>10 دولار مدى الحياة</b>

📊 <b>حالتك الحالية:</b>
• نوع الخطة: مجانية
• التحليلات المتبقية اليوم: {remaining}/{FREE_LIMIT}

🔽 <b>للاشتراك، اضغط على الزر أدناه:</b>
"""
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=get_premium_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعليمات المساعدة"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    help_text = f"""
🆘 <b>مساعدة بوت تحليل الحسابات الاجتماعية</b>

🔹 <b>لتحليل حساب:</b>
• اضغط على زر 🎯 تحليل حساباتي
• اختر المنصة المطلوبة
• سيتم تحليل الحساب المسجل تلقائياً

🔹 <b>للتسجيل أو تعديل البيانات:</b>
• اضغط على 📝 بياناتي لعرض الحسابات المسجلة
• اضغط على ✏️ تعديل بياناتي لتعديل الحسابات

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
    await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=get_main_keyboard(is_premium))


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية التحليل"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    # التحقق من وجود حسابات مسجلة
    accounts = get_user_social_accounts(user_id)
    
    if not accounts:
        await update.message.reply_text(
            "❌ لم تقم بتسجيل أي حسابات بعد.\n\n"
            "للتسجيل، أرسل /start",
            reply_markup=get_main_keyboard(is_premium)
        )
        return
    
    # التحقق من الحد اليومي للمجانيين
    can_analyze_bool, current_uses = can_analyze(user_id)
    
    # إذا كان المستخدم مجاني ووصل للحد اليومي
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
    
    # إذا كان المستخدم مميز أو لديه تحليلات متبقية
    await update.message.reply_text(
        "🎯 <b>اختر المنصة التي تريد تحليلها:</b>",
        parse_mode='HTML',
        reply_markup=get_analysis_keyboard()
    )


async def analyze_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    """تحليل قناة يوتيوب"""
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
            # إنشاء رابط الدفع الصحيح
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
            "❌ لم تقم بتسجيل حساب يوتيوب بعد.\n\n"
            "للتسجيل، أرسل /start ثم اتبع التعليمات",
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
    
    # زيادة عدد الاستخدامات
    remaining = get_remaining_analyses(user_id) if not is_premium else None
    increment_usage(user_id, 'youtube', {
        'account_name': channel_details['title'],
        'subscribers': channel_details['subscribers'],
        'total_posts': channel_details['total_videos'],
        'top_posts': channel_details['latest_videos'][:5],
        'duration': 0
    })
    
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
    
    # عرض خيار إضافة توصيات AI للمميزين
    if is_premium:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🤖 توصيات الذكاء الاصطناعي", callback_data=f"ai_recommendations_{channel_details['channel_id']}")
        ]])
        await message.reply_text(
            "🤖 <b>هل تريد الحصول على توصيات لتحسين قناتك؟</b>",
            parse_mode='HTML',
            reply_markup=keyboard
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
    
    # عرض خيار إضافة توصيات AI للمميزين
    if is_premium:
        keyboard = [[InlineKeyboardButton("🤖 توصيات الذكاء الاصطناعي", callback_data=f"ai_recommendations_{channel_details['channel_id']}")]]
        await message.reply_text(
            "🤖 <b>هل تريد الحصول على توصيات لتحسين قناتك؟</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def ai_recommendations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تقديم توصيات الذكاء الاصطناعي"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    channel_id = query.data.split('_')[-1]
    
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if not is_premium:
        await query.edit_message_text(
            "💎 هذه الميزة متاحة فقط للمستخدمين المميزين!\n\n"
            "للاشتراك: /premium"
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
    
    await query.edit_message_text("🤖 جاري توليد توصيات الذكاء الاصطناعي...")
    
    # زيادة عدد استخدامات Gemini
    increment_gemini_usage(user_id)
    
    # الحصول على التوصيات
    recommendations = await get_channel_recommendations(channel_details)
    
    response = f"🤖 <b>توصيات الذكاء الاصطناعي:</b>\n\n{recommendations}\n\n📊 <b>المتبقي اليوم:</b> {remaining - 1}/5 توصيات"
    
    await query.edit_message_text(response, parse_mode='HTML')


async def bio_page_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء صفحة البايو وإرسال الرابط فقط"""
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
    
    # تحويل تنسيق الحسابات
    formatted_accounts = {}
    for platform, acc in accounts.items():
        formatted_accounts[platform] = {
            'account_identifier': acc['account_identifier']
        }
    
    # إنشاء أو تحديث صفحة البايو
    display_name = user_info.get('first_name', 'مستخدم')
    page_url = create_or_update_bio_page(user_id, display_name, formatted_accounts)
    
    if page_url:
        flask_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
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

👁️ <b>سيتم احتساب المشاهدات</b> تلقائياً عند فتح الرابط
"""
        await update.message.reply_text(text, parse_mode='HTML')
    else:
        await update.message.reply_text(
            "❌ حدث خطأ في إنشاء صفحة البايو. حاول مرة أخرى لاحقاً.",
            parse_mode='HTML'
        )


async def show_bio_management(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None):
    """عرض إدارة صفحة البايو"""
    
    # استخراج user_id بشكل صحيح
    if user_id is None:
        if update.callback_query:
            user_id = update.callback_query.from_user.id
        elif update.effective_user:
            user_id = update.effective_user.id
        else:
            await update.message.reply_text("❌ حدث خطأ: لم يتم التعرف على المستخدم")
            return
    
    # التأكد من أن user_id رقم صحيح
    try:
        user_id = int(user_id)
    except:
        await update.message.reply_text("❌ حدث خطأ: معرف المستخدم غير صالح")
        return
    
    # جلب صفحة البايو مباشرة من قاعدة البيانات
    from utils.db import supabase
    
    try:
        response = supabase.table('bio_pages').select('*').eq('user_id', user_id).execute()
        
        if not response.data:
            # لم يتم العثور على صفحة، قم بإنشائها
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
            
            # جلب الصفحة مرة أخرى
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


async def username_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فحص توافر اليوزرنيم"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if not is_premium:
        await update.message.reply_text(
            "🔍 <b>فحص توافر اليوزرنيم</b>\n\n"
            "هذه الميزة متاحة فقط للمستخدمين المميزين!\n\n"
            "💎 <b>مميزات فحص اليوزرنيم:</b>\n"
            "• فحص توافر الاسم في جميع المنصات\n"
            "• اقتراحات ذكية لتحسين الاسم\n"
            "• توصيات لتوحيد الاسم بين المنصات\n\n"
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
        f"💎 <b>هذه الميزة ستعمل قريباً!</b>\n"
        f"سيتمكن المستخدمون المميزون من فحص توافر اليوزرنيم على جميع المنصات دفعة واحدة.\n\n"
        f"🚀 <b>قريباً في التحديث القادم</b>",
        parse_mode='HTML'
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأزرار"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # ========== أزرار التحليل ==========
    if data == "analyze_youtube":
        await analyze_youtube(update, context, query)
    
    elif data == "analyze_instagram":
        await query.answer("📸 هذه الميزة قيد التطوير حالياً", show_alert=True)
    
    elif data == "analyze_tiktok":
        await query.answer("🎵 هذه الميزة قيد التطوير حالياً", show_alert=True)
    
    elif data == "analyze_facebook":
        await query.answer("📘 هذه الميزة قيد التطوير حالياً", show_alert=True)
    
    # ========== زر القائمة الرئيسية ==========
    elif data == "main_menu":
        user_info = get_user_info(user_id)
        is_premium = user_info['status'] == 'premium' if user_info else False
        await query.message.reply_text(
            "🏠 <b>القائمة الرئيسية</b>\n\nاختر ما تريد:",
            parse_mode='HTML',
            reply_markup=get_main_keyboard(is_premium)
        )
        await query.delete_message()
    
    # ========== توصيات الذكاء الاصطناعي ==========
    elif data.startswith("ai_recommendations"):
        await ai_recommendations(update, context)
    
    # ========== تعديل الحسابات ==========
    elif data.startswith("edit_"):
        platform = data.split('_')[1]
        context.user_data['editing_platform'] = platform
        keyboard = [[InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]]
        await query.edit_message_text(
            f"✏️ <b>تعديل حساب {platform.capitalize()}</b>\n\n"
            f"أرسل المعرف الجديد أو الرابط:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # ========== أزرار إدارة صفحة البايو ==========
    elif data == "bio_change_theme":
        # تغيير الثيم
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
    
    elif data == "bio_edit_bio":
        context.user_data['editing_bio'] = True
        keyboard = [[InlineKeyboardButton("🔙 إلغاء", callback_data="bio_back")]]
        await query.edit_message_text(
            "📝 <b>تعديل النبذة</b>\n\n"
            "أرسل النص الجديد للنبذة (الوصف الشخصي):\n\n"
            "💡 مثال: مبرمج ومطور ويب | مهتم بالذكاء الاصطناعي",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "bio_show_link":
        bio_page = get_bio_page(user_id)
        if bio_page:
            flask_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
            await query.answer(f"رابط صفحتك: https://{flask_url}/bio/{bio_page['page_url']}", show_alert=True)
    
    elif data == "bio_back":
        await show_bio_management(update, context, user_id)


async def handle_bio_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة تعديل النبذة في صفحة البايو"""
    if context.user_data.get('editing_bio'):
        user_id = update.effective_user.id
        new_bio = update.message.text.strip()
        
        if update_bio_text(user_id, new_bio):
            context.user_data.pop('editing_bio', None)
            await update.message.reply_text("✅ تم تحديث النبذة بنجاح!")
            # عرض إدارة الصفحة مرة أخرى
            await show_bio_management(update, context, user_id)
        else:
            await update.message.reply_text("❌ حدث خطأ في تحديث النبذة")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    # معالجة تعديل النبذة في صفحة البايو
    if context.user_data.get('editing_bio'):
        await handle_bio_edit(update, context)
        return
    
    # معالجة الأزرار
    if text == "🎯 تحليل حساباتي":
        await analyze_command(update, context)
        return
    
    elif text == "📊 إحصائياتي":
        await my_stats_command(update, context)
        return
    
    elif text == "📝 بياناتي":
        await my_data_command(update, context)
        return
    
    elif text == "✏️ تعديل بياناتي":
        await edit_data_command(update, context)
        return
    
    elif text == "💎 اشتراك مميز":
        await premium_command(update, context)
        return
    
    elif text == "ℹ️ المساعدة":
        await help_command(update, context)
        return
    
    elif text == "📄 صفحة البايو":
        await bio_page_command(update, context)
        return
    
    elif text == "🔍 فحص يوزرنيم":
        await username_check_command(update, context)
        return
    
    # معالجة تعديل الحساب
    if context.user_data.get('editing_platform'):
        await handle_edit_account(update, context)
        return
    
    # معالجة فحص اليوزرنيم
    if context.user_data.get('awaiting_username'):
        await handle_username_check(update, context)
        return
    
    # رسالة افتراضية
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    await update.message.reply_text(
        "❓ عذراً، لم أتعرف على طلبك.\n\n"
        "📌 يمكنك استخدام الأزرار أدناه أو إرسال /help للمساعدة.",
        parse_mode='HTML',
        reply_markup=get_main_keyboard(is_premium)
    )


# ========== الدالة الرئيسية ==========

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
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("mystats", my_stats_command))
    application.add_handler(CommandHandler("premium", premium_command))
    application.add_handler(CommandHandler("mydata", my_data_command))
    application.add_handler(CommandHandler("edit", edit_data_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("="*60)
    print("📊 Social Media Analyzer Bot - النسخة المميزة")
    print("🤖 @Social_Media_tools_bot")
    print("✅ أوامر: /start /help /mystats /premium /mydata /edit")
    print(f"✅ نظام المدفوعات: مجاني {FREE_LIMIT} تحليل - مميز غير محدود")
    print("✅ قاعدة بيانات: Supabase (متكاملة مع النظام الموحد)")
    print("✅ الذكاء الاصطناعي: Gemini API (قيد التطوير)")
    print("✅ خادم HTTP يعمل على المنفذ", os.environ.get('PORT', 10000))
    print("="*60)
    
    # تشغيل البوت مع إعدادات محسنة لمنع التعارض
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        timeout=60
    )


if __name__ == '__main__':
    main()
