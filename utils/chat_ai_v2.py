"""
المساعد الذكي المتطور (Smart Chat AI Assistant) - الإصدار 4.2.5
دعم كامل للربط مع تحليلات وتوصيات المستخدم السابقة مع برومبت احترافي محسن.
تطوير: @Alshabany_Ai
"""

import google.generativeai as genai
import os
from datetime import date, datetime
from supabase import create_client, Client

# ========== تهيئة Supabase (دعم أسماء متعددة) ==========
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_ANON_KEY") or 
    os.getenv("SUPABASE_SERVICE_ROLE_KEY") or 
    os.getenv("SUPABASE_KEY")
)

print(f"🔑 SUPABASE_URL: {'✅ Found' if SUPABASE_URL else '❌ Missing'}")
print(f"🔑 SUPABASE_KEY: {'✅ Found' if SUPABASE_KEY else '❌ Missing'}")

supabase: Client = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase connected for Chat AI")
else:
    print("❌ Supabase not configured - missing URL or KEY")

# ========== تهيئة Gemini ==========
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHAT_GEMINI_API_KEY = os.getenv("CHAT_GEMINI_API_KEY") or GEMINI_API_KEY
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")

if CHAT_GEMINI_API_KEY:
    genai.configure(api_key=CHAT_GEMINI_API_KEY)
    print(f"✅ Gemini configured with model: {GEMINI_MODEL}")
else:
    print("❌ Gemini not configured - missing API key")


# ========== دوال قراءة الإعدادات والبيانات التاريخية ==========

def get_chat_settings() -> dict:
    """قراءة إعدادات المساعد الذكي من جدول bot_settings_social"""
    default_settings = {
        'daily_limit_free': 20,
        'daily_limit_premium': 200,
        'enabled': True
    }
    
    if not supabase:
        return default_settings
    
    try:
        result = supabase.table('bot_settings_social')\
            .select('setting_key, setting_value')\
            .in_('setting_key', [
                'chat_daily_limit_free',
                'chat_daily_limit_premium', 
                'chat_enabled'
            ])\
            .execute()
        
        if result.data:
            for item in result.data:
                key = item['setting_key']
                value = item['setting_value']
                
                if key == 'chat_daily_limit_free':
                    default_settings['daily_limit_free'] = int(value) if value.isdigit() else 20
                elif key == 'chat_daily_limit_premium':
                    default_settings['daily_limit_premium'] = int(value) if value.isdigit() else 200
                elif key == 'chat_enabled':
                    default_settings['enabled'] = value.lower() == 'true'
        
        print(f"📊 Chat settings loaded: {default_settings}")
        return default_settings
    except Exception as e:
        print(f"❌ Error loading chat settings: {e}")
        return default_settings


def get_user_subscription_status(user_id: str) -> dict:
    """الحصول على حالة اشتراك المستخدم"""
    if not supabase:
        return {'is_premium': False, 'plan': 'free'}
    
    try:
        user_result = supabase.table('users')\
            .select('status, premium_until')\
            .eq('user_id', int(user_id))\
            .execute()
        
        if user_result.data:
            user = user_result.data[0]
            status = user.get('status', 'free')
            premium_until = user.get('premium_until')
            
            is_premium = (status == 'premium')
            
            if is_premium and premium_until:
                if isinstance(premium_until, str):
                    premium_until = datetime.strptime(premium_until, '%Y-%m-%d').date()

                if date.today() > premium_until:
                    is_premium = False
                    status = 'expired'
            
            return {
                'is_premium': is_premium,
                'plan': status,
                'premium_until': premium_until
            }
        
        return {'is_premium': False, 'plan': 'free'}
    except Exception as e:
        print(f"❌ Error getting subscription: {e}")
        return {'is_premium': False, 'plan': 'free'}


def get_user_history_context(user_id: str) -> str:
    """
    جلب سجل التوصيات السابقة والتحليلات الأخيرة لبناء سياق غني للذكاء الاصطناعي
    """
    if not supabase:
        return ""
    
    context_parts = []
    
    try:
        # 1. جلب آخر 5 توصيات قُدمت للمستخدم من جدول recommendations_history أو recommendations
        # قمنا بدعم الجدولين لضمان عدم حدوث أخطاء تبعاً لتصميم قاعدة بياناتك المعتمد
        rec_table = 'recommendations_history'
        try:
            rec_result = supabase.table(rec_table)\
                .select('recommendation_text, created_at')\
                .eq('user_id', str(user_id))\
                .order('created_at', desc=True)\
                .limit(5)\
                .execute()
        except Exception:
            # جدول بديل في حال لم يكن الاسم الأول موجوداً
            rec_table = 'recommendations'
            rec_result = supabase.table(rec_table)\
                .select('recommendation_text, created_at')\
                .eq('user_id', str(user_id))\
                .order('created_at', desc=True)\
                .limit(5)\
                .execute()

        if rec_result.data:
            context_parts.append("=== التوصيات الاستراتيجية السابقة للمستخدم ===")
            for idx, rec in enumerate(rec_result.data, 1):
                clean_rec = rec.get('recommendation_text', '').strip()[:300]
                created_at = rec.get('created_at', 'تاريخ غير معروف')[:10]
                context_parts.append(f"التوصية #{idx} ({created_at}):\n{clean_rec}...")
        
        # 2. جلب آخر تحليل حساب (يوتيوب أو غيره) مسجل للمستخدم لربطه بالنقاش
        analysis_result = supabase.table('analysis_history')\
            .select('platform, channel_title, subscribers, videos_count, created_at')\
            .eq('user_id', str(user_id))\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()
            
        if analysis_result.data:
            analysis = analysis_result.data[0]
            context_parts.append("\n=== بيانات آخر تحليل تم على منصتنا لمستودع حسابات المستخدم ===")
            context_parts.append(
                f"- المنصة: {analysis.get('platform')}\n"
                f"- اسم الحساب/القناة: {analysis.get('channel_title')}\n"
                f"- عدد المشتركين/المتابعين الحالي: {analysis.get('subscribers', 'غير متوفر')}\n"
                f"- عدد الفيديوهات: {analysis.get('videos_count', 'غير متوفر')}\n"
                f"- تاريخ التحليل: {analysis.get('created_at', '')[:10]}"
            )
            
    except Exception as e:
        print(f"⚠️ Error gathering history context: {e}")
        
    return "\n".join(context_parts)


# ========== دوال الـ Embedding ==========

def get_embedding(text: str):
    """توليد embedding للنص للبحث المتجه - يدعم نماذج متعددة"""
    if not text or not CHAT_GEMINI_API_KEY:
        return None
    
    embedding_models = [
        "models/text-embedding-004",
        "models/embedding-001", 
        "models/text-embedding-003",
        "text-embedding-004"
    ]
    
    for model_name in embedding_models:
        try:
            clean_text = text.strip()[:1000]
            
            result = genai.embed_content(
                model=model_name,
                content=clean_text,
                task_type="retrieval_document"
            )
            
            if result and 'embedding' in result:
                embedding = result['embedding']
                print(f"✅ Embedding generated using {model_name}: {len(embedding)} dimensions")
                return embedding
        except Exception as e:
            print(f"⚠️ Failed with {model_name}: {e}")
            continue
    
    print(f"❌ All embedding models failed")
    return None


# ========== دوال الحفظ ==========

def save_to_chat_history(user_id: str, question: str, answer: str, source: str = 'gemini'):
    """حفظ المحادثة في جدول chat_history مع embedding للبحث المتجه"""
    if not supabase:
        print("❌ Supabase not available for saving chat history")
        return False
    
    try:
        data = {
            'user_id': str(user_id),
            'question': question[:500],
            'answer': answer[:2000],
            'source': source,
            'created_at': datetime.utcnow().isoformat(),
            'last_used_at': datetime.utcnow().isoformat()
        }
        
        embedding = get_embedding(question)
        if embedding:
            data['question_embedding'] = embedding
            print(f"✅ Embedding added to chat_history")
        else:
            print(f"⚠️ No embedding generated for this question")
        
        result = supabase.table('chat_history').insert(data).execute()
        print(f"✅ Saved to chat_history for user {user_id}")
        return True
    except Exception as e:
        print(f"❌ Error saving to chat_history: {e}")
        return False


def save_to_usage_stats(user_id: str, tokens_used: int = 0, cached_hit: bool = False, gemini_call: bool = False):
    """حفظ إحصائيات الاستخدام في جدول chat_usage_stats"""
    if not supabase:
        print("❌ Supabase not available for saving usage stats")
        return False
    
    try:
        today = date.today().isoformat()
        
        existing = supabase.table('chat_usage_stats')\
            .select('*')\
            .eq('user_id', str(user_id))\
            .eq('usage_date', today)\
            .execute()
        
        if existing.data and len(existing.data) > 0:
            new_count = existing.data[0].get('questions_count', 0) + 1
            new_tokens = existing.data[0].get('tokens_used', 0) + tokens_used
            new_cached = existing.data[0].get('cached_hits', 0) + (1 if cached_hit else 0)
            new_gemini = existing.data[0].get('gemini_calls', 0) + (1 if gemini_call else 0)
            
            supabase.table('chat_usage_stats')\
                .update({
                    'questions_count': new_count,
                    'tokens_used': new_tokens,
                    'cached_hits': new_cached,
                    'gemini_calls': new_gemini
                })\
                .eq('user_id', str(user_id))\
                .eq('usage_date', today)\
                .execute()
            
            print(f"✅ Updated usage stats for {user_id}: {new_count} questions today")
        else:
            supabase.table('chat_usage_stats').insert({
                'user_id': str(user_id),
                'usage_date': today,
                'questions_count': 1,
                'tokens_used': tokens_used,
                'cached_hits': 1 if cached_hit else 0,
                'gemini_calls': 1 if gemini_call else 0
            }).execute()
            
            print(f"✅ Created new usage stats for {user_id}")
        
        return True
    except Exception as e:
        print(f"❌ Error saving to usage_stats: {e}")
        return False


def check_daily_limit(user_id: str, is_premium: bool = False) -> tuple:
    """التحقق من الحد اليومي للمستخدم"""
    if not supabase:
        return True, 0, 20
    
    try:
        settings = get_chat_settings()
        daily_limit = settings['daily_limit_premium'] if is_premium else settings['daily_limit_free']
        
        today = date.today().isoformat()
        
        result = supabase.table('chat_usage_stats')\
            .select('questions_count')\
            .eq('user_id', str(user_id))\
            .eq('usage_date', today)\
            .execute()
        
        if result.data and len(result.data) > 0:
            used = result.data[0].get('questions_count', 0)
            remaining = daily_limit - used
            can_ask = remaining > 0
            return can_ask, used, daily_limit
        else:
            return True, 0, daily_limit
    except Exception as e:
        print(f"❌ Error checking limit: {e}")
        return True, 0, 20


# ========== الدالة الرئيسية ==========

def get_chat_response(question: str, user_id: str, user_context: str = "", is_premium: bool = False):
    """الحصول على رد من المساعد الذكي مع الحفظ والدعم الكامل للتاريخ والتحليلات"""
    
    print(f"📝 Chat request for user: {user_id}")
    print(f"❓ Question: {question[:100]}...")
    
    # التحقق من تفعيل المساعد
    settings = get_chat_settings()
    if not settings['enabled']:
        return {
            'success': False,
            'answer': '⏸️ المساعد الذكي غير متاح حالياً. سيتم تفعيله قريباً.'
        }
    
    if not CHAT_GEMINI_API_KEY:
        return {
            'success': False,
            'answer': '❌ مفتاح Gemini API غير موجود.'
        }
    
    # الحالة الفعلية للمستخدم
    user_subscription = get_user_subscription_status(user_id)
    actual_is_premium = user_subscription['is_premium']
    
    # التحقق من الحد اليومي
    can_ask, used, limit = check_daily_limit(user_id, actual_is_premium)
    if not can_ask:
        return {
            'success': False,
            'answer': f'⚠️ لقد وصلت للحد اليومي ({used}/{limit}).\n\n💡 يمكنك المحاولة غداً أو ترقية حسابك للمميز.'
        }
    
    # جلب السياق التاريخي للمستخدم من قاعدة البيانات
    history_context = get_user_history_context(user_id)
    
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # برومبت النظام المطور والمُحسّن باحترافية كاملة
        system_instruction = """
        أنت "مستشار النمو الرقمي والذكاء الاصطناعي الذكي" لمنصة Social Analyzer AI. 
        مهمتك الأساسية هي تقديم تحليلات، نصائح، حلول، وإجابات استشارية فائقة الجودة لمساعدة صناع المحتوى والمسوقين على تحسين أدائهم الرقمي وزيادة نسبة التفاعل والوصول على منصات التواصل الاجتماعي (خاصة يوتيوب والمنصات الأخرى).

        إرشادات الأسلوب والهوية:
        1. شخصيتك: ودود، عملي، دقيق جداً، مفعم بالحماس والطاقة الإيجابية الملهمة، وتتحدث بلغة عربية سلسلة واحترافية مدعمة بالإيموجي التوضيحية المناسبة.
        2. التعامل مع البيانات: إذا تم توفير بيانات تحليلية سابقة أو توصيات سابقة للمستخدم، اعتمد عليها فوراً للإشارة إلى أرقامه وقناته الفعلية (مثال: "بناءً على آخر تحليل لقناتك (اسم القناة)..." أو "لقد اقترحنا عليك سابقاً... هل قمت بتطبيق هذا؟").
        3. الإيجاز والفعالية: تجنب الحشو والإنشاء الطويل والممل. قدم الإجابات على شكل نقاط واضحة وقابلة للتنفيذ المباشر (Actionable Steps).
        4. خصوصية البوت: أنت تمثل تطبيق Social Analyzer AI وتطوير المهندس المبدع @Alshabany_Ai، فخر الصناعة والبرمجة اليمنية. حافظ على فخرك واعتزازك بهذه الهوية عند سؤالك عن من قام ببرمجتك أو تطويرك.
        """
        
        prompt = f"""
        {system_instruction}

        === البيانات الفنية الحالية لمكالمة الـ API ===
        سياق واجهة المستخدم المباشر: {user_context}
        حالة اشتراك المستخدم الحالية: {'⭐ مستخدم مميز (Premium)' if actual_is_premium else '🎁 مستخدم مجاني (Free)'}

        {history_context}

        === سؤال المستخدم الحالي ===
        ❓ {question}

        الرجاء صياغة ردك الاستشاري الآن بناءً على الإرشادات أعلاه بطريقة منسقة ورائعة:
        """
        
        response = model.generate_content(prompt)
        
        if response and response.text:
            answer = response.text.strip()
            
            # حفظ المحادثة والإحصائيات
            save_to_chat_history(user_id, question, answer, source='gemini')
            tokens_used = len(answer.split()) + len(question.split())
            save_to_usage_stats(user_id, tokens_used=tokens_used, gemini_call=True)
            
            remaining = limit - used - 1
            
            return {
                'success': True,
                'source': 'gemini',
                'answer': answer,
                'remaining': remaining,
                'daily_limit': limit,
                'user_plan': 'premium' if actual_is_premium else 'free'
            }
        else:
            return {
                'success': False,
                'answer': 'عذراً، لم أستطع معالجة طلبك حالياً.'
            }
            
    except Exception as e:
        print(f"❌ Gemini error: {e}")
        return {
            'success': False,
            'answer': f'🤖 خطأ تقني في الاتصال بـ Gemini: {str(e)[:120]}'
        }


def get_user_chat_stats(user_id: str) -> dict:
    """إحصائيات استخدام المستخدم للدردشة الذكية"""
    if not supabase:
        return {'total_questions': 0, 'today_usage': 0, 'daily_limit': 20}
    
    try:
        user_subscription = get_user_subscription_status(user_id)
        settings = get_chat_settings()
        daily_limit = settings['daily_limit_premium'] if user_subscription['is_premium'] else settings['daily_limit_free']
        
        total_result = supabase.table('chat_usage_stats')\
            .select('questions_count')\
            .eq('user_id', str(user_id))\
            .execute()
        
        total_questions = sum(item.get('questions_count', 0) for item in total_result.data) if total_result.data else 0
        
        today = date.today().isoformat()
        today_result = supabase.table('chat_usage_stats')\
            .select('questions_count')\
            .eq('user_id', str(user_id))\
            .eq('usage_date', today)\
            .execute()
        
        today_usage = today_result.data[0].get('questions_count', 0) if today_result.data else 0
        
        return {
            'total_questions': total_questions,
            'today_usage': today_usage,
            'daily_limit': daily_limit,
            'remaining': daily_limit - today_usage,
            'is_premium': user_subscription['is_premium']
        }
    except Exception as e:
        print(f"Error getting stats: {e}")
        return {'total_questions': 0, 'today_usage': 0, 'daily_limit': 20, 'remaining': 20}
