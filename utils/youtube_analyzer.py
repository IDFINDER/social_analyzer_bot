# -*- coding: utf-8 -*-
"""
دوال تحليل قنوات يوتيوب
"""

import os
import logging
from datetime import datetime
from googleapiclient.discovery import build
from .helpers import format_number, format_duration, escape_html
from utils.texts import BOT_LINK, DEVELOPER_LINK

logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '2'))
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY) if YOUTUBE_API_KEY else None


def extract_channel_info(channel_input):
    """
    استخراج معلومات القناة من الإدخال
    """
    channel_input = channel_input.strip()
    
    # إزالة @ إذا كانت موجودة
    if channel_input.startswith('@'):
        channel_input = channel_input[1:]
    
    # إزالة الروابط
    if 'youtube.com' in channel_input:
        if '/@' in channel_input:
            channel_input = channel_input.split('/@')[-1].split('?')[0]
        elif '/channel/' in channel_input:
            channel_input = channel_input.split('/channel/')[-1].split('?')[0]
        elif '/c/' in channel_input:
            channel_input = channel_input.split('/c/')[-1].split('?')[0]
    
    return channel_input


async def get_channel_details(channel_identifier):
    """
    تحليل قناة يوتيوب
    """
    if not youtube:
        return None, "YouTube API key not configured"
    
    try:
        channel_identifier = extract_channel_info(channel_identifier)
        channel_id = None
        
        # البحث عن القناة
        search_response = youtube.search().list(
            part='snippet',
            q=channel_identifier,
            type='channel',
            maxResults=1
        ).execute()
        
        if not search_response.get('items'):
            return None, "لم يتم العثور على القناة"
        
        channel_id = search_response['items'][0]['snippet']['channelId']
        
        # جلب تفاصيل القناة
        channel_response = youtube.channels().list(
            part='snippet,statistics,contentDetails,status',
            id=channel_id
        ).execute()
        
        if not channel_response.get('items'):
            return None, "لم يتم العثور على القناة"
        
        channel_data = channel_response['items'][0]
        snippet = channel_data['snippet']
        statistics = channel_data.get('statistics', {})
        status = channel_data.get('status', {})
        
        # جلب أحدث الفيديوهات
        uploads_playlist_id = channel_data.get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads')
        latest_videos = []
        
        if uploads_playlist_id:
            playlist_response = youtube.playlistItems().list(
                part='snippet',
                playlistId=uploads_playlist_id,
                maxResults=5
            ).execute()
            
            for item in playlist_response.get('items', []):
                video_snippet = item['snippet']
                latest_videos.append({
                    'title': video_snippet['title'],
                    'video_id': video_snippet['resourceId']['videoId'],
                    'published_at': video_snippet['publishedAt'][:10]
                })
        
        # حساب المتوسطات
        total_views = int(statistics.get('viewCount', 0))
        total_videos = int(statistics.get('videoCount', 1))
        avg_views = total_views / total_videos if total_videos > 0 else 0
        
        channel_details = {
            'title': snippet['title'],
            'description': snippet.get('description', 'لا يوجد وصف')[:200],
            'custom_url': snippet.get('customUrl', 'N/A'),
            'published_at': snippet['publishedAt'][:10],
            'country': snippet.get('country', 'غير محدد'),
            'subscribers': format_number(statistics.get('subscriberCount', 0)),
            'total_views': format_number(total_views),
            'total_videos': format_number(total_videos),
            'hidden_subscribers': statistics.get('hiddenSubscriberCount', False),
            'privacy_status': status.get('privacyStatus', 'غير معروف'),
            'avg_views': format_number(avg_views),
            'latest_videos': latest_videos,
            'channel_id': channel_id
        }
        
        return channel_details, None
        
    except Exception as e:
        logger.error(f"Error getting channel details: {e}")
        return None, str(e)


def format_channel_report(channel_details, user_id=None, is_premium=False, remaining_analyses=None):
    """
    تنسيق تقرير تحليل القناة
    """
    if not channel_details:
        return None, None
    
    from .helpers import clean_filename, escape_html
    
    # إزالة @ من البداية إذا وجدت
    custom_url = channel_details.get('custom_url', 'N/A')
    if custom_url.startswith('@'):
        custom_url = custom_url[1:]
    
    # بناء الرسالة النصية
    message = f"✅ <b>تم تحليل القناة بنجاح!</b>\n\n"
    message += f"📺 <b>القناة:</b> {escape_html(channel_details['title'])}\n"
    message += f"🆔 <b>المعرف:</b> @{escape_html(custom_url)}\n"
    message += f"📅 <b>الإنشاء:</b> {channel_details['published_at']}\n"
    message += f"🌍 <b>البلد:</b> {channel_details['country']}\n\n"
    
    message += f"📊 <b>الإحصائيات:</b>\n"
    subs_text = "🔒 مخفي" if channel_details['hidden_subscribers'] else channel_details['subscribers']
    message += f"👥 <b>المشتركين:</b> {subs_text}\n"
    message += f"📹 <b>عدد الفيديوهات:</b> {channel_details['total_videos']}\n"
    message += f"👁️ <b>إجمالي المشاهدات:</b> {channel_details['total_views']}\n"
    message += f"📊 <b>متوسط المشاهدات/فيديو:</b> {channel_details['avg_views']}\n\n"
    
    message += f"🔥 <b>أحدث 5 فيديوهات:</b>\n"
    for i, v in enumerate(channel_details['latest_videos'][:5], 1):
        title = escape_html(v['title'][:60])
        video_id = v.get('video_id', '')
        message += f"{i}. <a href='https://youtu.be/{video_id}'>{title}</a>\n"
    
    if not is_premium:
        message += f"\n📊 <b>المتبقي اليوم:</b> {remaining_analyses}/{FREE_LIMIT}"
    
    # بناء الملف النصي
    file_content = build_text_file(channel_details, is_premium)
    
    # اسم الملف (نفس الاسم القديم مع الحفاظ على التنسيق)
    filename = f"تحليل_يوتيوب_{datetime.now().strftime('%Y_%m_%d')}.txt"
    
    return message, (file_content, filename)


def build_text_file(channel_details, is_premium):
    """
    بناء محتوى الملف النصي
    """
    now = datetime.now()
    
    # إزالة @ من البداية إذا وجدت
    custom_url = channel_details.get('custom_url', 'N/A')
    if custom_url.startswith('@'):
        custom_url = custom_url[1:]
    
    # خط فاصل أقصر (40 علامة بدلاً من 60)
    separator = "━" * 40
    
    content = separator + "\n"
    content += f"          📊 تقرير قناة {custom_url}\n"
    content += separator + "\n\n"
    
    content += f"📅 التاريخ: {now.strftime('%Y-%m-%d')}\n"
    content += f"⏰ الوقت: {now.strftime('%H:%M')}\n\n"
    
    content += f"📺 القناة: {channel_details['title']}\n"
    content += f"🆔 المعرف: @{custom_url}\n"
    content += f"📅 الإنشاء: {channel_details['published_at']}\n"
    content += f"🌍 البلد: {channel_details['country']}\n\n"
    
    content += "📊 الإحصائيات:\n"
    subs_text = "🔒 مخفي" if channel_details['hidden_subscribers'] else channel_details['subscribers']
    content += f"👥 المشتركين: {subs_text}\n"
    content += f"📹 عدد الفيديوهات: {channel_details['total_videos']}\n"
    content += f"👁️ المشاهدات: {channel_details['total_views']}\n"
    content += f"📊 متوسط المشاهدات/فيديو: {channel_details['avg_views']}\n\n"
    
    content += "🔥 أحدث 5 فيديوهات:\n"
    for i, v in enumerate(channel_details['latest_videos'][:5], 1):
        content += f"{i}. {v['title'][:80]}\n"
        content += f"   👉 https://youtu.be/{v['video_id']}\n\n"
    
    content += separator + "\n"
    
    if not is_premium:
        content += "🤖 تم التحليل بواسطة بوت تحليل حسابات السوشيال ميديا\n"
        content += f"📌 للاشتراك المميز: /premium\n"
        content += f"🔗 رابط البوت: {BOT_LINK}\n"
        content += f"👨‍💻 المطور: {DEVELOPER_LINK}\n"
    
    content += separator + "\n"
    
    return content
