import os
import sys
import time
import getpass

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Reconfigure stdout/stderr to UTF-8 so Arabic and emojis never fail on Windows consoles
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core.config import get_keychain_passphrase, IPATOOL_DIR
from core.apple_api import (
    validate_email_format,
    InteractiveLoginSession,
    check_auth_status
)

def print_banner():
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 64)
    print("   🔐 معالج تسجيل الدخول التفاعلي الذكي لحساب أبل (Apple ID)   ")
    print("=" * 64)
    print(" يسير هذا المعالج معك خطوة بخطوة ولا يطلب كل شيء دفعة واحدة:")
    print("   [1] إدخال البريد الإلكتروني والتحقق من صحته")
    print("   [2] إدخال كلمة المرور والتأكد من صحتها لدى خوادم أبل")
    print("   [3] انتظار وصول كود التحقق (2FA) وإدخاله والتأكد من صحته")
    print("   [4] إدخال الرمز المؤقت للحافظة وتأكيد نجاح تسجيل الدخول")
    print("=" * 64)
    print()

def read_password_interactive(prompt_text):
    """قراءة كلمة المرور مع دعم الإخفاء أو الإدخال المباشر واللصق."""
    try:
        pwd = getpass.getpass(prompt_text).strip()
        if pwd:
            return pwd
    except Exception:
        pass
    return input("   (اكتب كلمة المرور أو الصقها هنا ثم اضغط Enter): ").strip()

def main():
    # تفعيل دعم الألوان والـ UTF-8 في ويندوز
    if os.name == "nt":
        os.system("chcp 65001 >nul")
        os.system("title تسجيل الدخول التفاعلي خطوة بخطوة - Apple ID")

    print_banner()

    # فحص سريع إذا كان هناك حساب مسجل حالياً
    current_pass = get_keychain_passphrase()
    info = check_auth_status(current_pass)
    if info.get("logged_in"):
        print(f"ℹ️  ملاحظة: يوجد حساب مسجل الدخول حالياً:")
        print(f"   👤 الاسم  : {info['name']}")
        print(f"   📧 البريد : {info['email']}")
        print("-" * 64)
        ans = input("هل تريد تسجيل الدخول بحساب جديد أو تجديد الجلسة؟ (اضغط Enter للمتابعة أو N للخروج): ").strip()
        if ans.upper() == "N":
            return
        print()

    # ---------------------------------------------------------
    # الخطوة 1: إدخال البريد الإلكتروني والتحقق من صحته
    # ---------------------------------------------------------
    print("━" * 64)
    print("📌 الخطوة 1 من 4 : إدخال البريد الإلكتروني (Apple ID)")
    print("━" * 64)
    while True:
        email = input("👈 أدخل بريد أبل الإلكتروني: ").strip()
        ok, msg = validate_email_format(email)
        if ok:
            print(f"   {msg}")
            break
        else:
            print(f"   ❌ {msg}\n")

    # ---------------------------------------------------------
    # الخطوة 2: إدخال كلمة المرور والتحقق من تسجيل الدخول لدى أبل
    # ---------------------------------------------------------
    print("\n" + "━" * 64)
    print("📌 الخطوة 2 من 4 : إدخال كلمة المرور والتحقق من الحساب")
    print("━" * 64)
    session = None
    while True:
        pwd = read_password_interactive("👈 أدخل كلمة المرور (أو اضغط Enter للكتابة المرئية/اللصق): ")
        if not pwd:
            print("   ❌ لم يتم إدخال كلمة المرور، يرجى كتابتها.")
            continue

        print("\n⏳ جاري الاتصال بخوادم أبل للتحقق من البريد وكلمة المرور...")
        print("   (يرجى الانتظار، قد يستغرق التحقق من 10 إلى 40 ثانية...)")

        def log_cb(line):
            # طباعة رسائل التقدم المهمة فقط بشكل نظيف
            if line.startswith("⏳") or line.startswith("🔐") or line.startswith("📱"):
                print(f"   {line}")

        session = InteractiveLoginSession(email, pwd, temp_passphrase=current_pass, log_callback=log_cb)
        status, msg, data = session.verify_credentials_and_wait_2fa()

        if status == "ERROR":
            print(f"\n   ❌ فشل التحقق من الحساب: {msg}")
            print("   يرجى التأكد من كلمة المرور أو البريد الإلكتروني والمحاولة مرة أخرى.\n")
            choice = input("   اضغط Enter لإعادة كتابة كلمة المرور، أو اكتب E لتغيير الإيميل: ").strip()
            if choice.upper() == "E":
                while True:
                    email = input("\n👈 أدخل بريد أبل الإلكتروني الصحيح: ").strip()
                    ok_e, msg_e = validate_email_format(email)
                    if ok_e:
                        print(f"   {msg_e}")
                        break
                    print(f"   ❌ {msg_e}")
            continue
        elif status == "SUCCESS":
            print(f"\n   ✅ {msg}")
            break
        elif status == "NEEDS_2FA":
            print(f"\n   ✅ {msg}")
            break

    # ---------------------------------------------------------
    # الخطوة 3: انتظار وإدخال كود التحقق (2FA) والتأكد من صحته
    # ---------------------------------------------------------
    if status == "NEEDS_2FA":
        print("\n" + "━" * 64)
        print("📌 الخطوة 3 من 4 : إدخال كود التحقق بخطوتين (2FA)")
        print("━" * 64)
        print("📱 تم إرسال رمز التحقق المكون من 6 أرقام إلى أجهزتك الموثوقة (أيفون / أيباد / ماك).")
        print("⏳ الجلسة مفتوحة الآن وتنتظرك — حتى لو تأخر وصول الكود، خذ وقتك ولا تغلق النافذة.")
        print("💡 إذا تأخر الكود كثيراً ولم يصل، اكتب حرف R واضغط Enter لإعادة طلب الكود.\n")

        while True:
            code_in = input("👈 أدخل كود التحقق (6 أرقام) [أو R لإعادة الإرسال]: ").strip()
            if code_in.upper() == "R":
                print("\n⏳ جاري إعادة الاتصال بخوادم أبل لطلب إرسال كود تحقق جديد...")
                st2, msg2, _ = session.verify_credentials_and_wait_2fa()
                if st2 == "NEEDS_2FA":
                    print("   📱 تم إرسال طلب كود جديد بنجاح! تفقد جهازك الآن.\n")
                elif st2 == "SUCCESS":
                    print("   ✅ تم تسجيل الدخول بنجاح دون الحاجة لكود إضافي!")
                    break
                else:
                    print(f"   ❌ حدث خطأ أثناء إعادة الطلب: {msg2}\n")
                continue

            clean_code = code_in.replace(" ", "").replace("-", "")
            if not (clean_code.isdigit() and len(clean_code) == 6):
                print("   ❌ الكود يجب أن يتكون من 6 أرقام فقط! يرجى المحاولة مرة أخرى.\n")
                continue

            print("\n⏳ جاري التحقق من صحة كود التحقق (2FA) مع خوادم أبل...")
            ok_2fa, msg_2fa, _ = session.submit_2fa_code(clean_code)
            if ok_2fa:
                print(f"   {msg_2fa}")
                break
            else:
                print(f"   ❌ فشل التحقق من الكود: {msg_2fa}")
                print("   🔄 جاري إعادة فتح جلسة انتظار كود جديدة لتتمكن من المحاولة...")
                st_retry, msg_retry, _ = session.verify_credentials_and_wait_2fa()
                if st_retry == "NEEDS_2FA":
                    print("   📱 تم تجهيز الجلسة وإرسال طلب كود جديد، يرجى إدخال الكود الصحيح:\n")
                elif st_retry == "SUCCESS":
                    print("   ✅ تم تسجيل الدخول بنجاح!")
                    break
                else:
                    print(f"   ❌ تعذر إعادة الطلب: {msg_retry}")
                    return

    # ---------------------------------------------------------
    # الخطوة 4: طلب الرمز المؤقت للحافظة وتأكيد حالة الحساب النهائية
    # ---------------------------------------------------------
    print("\n" + "━" * 64)
    print("📌 الخطوة 4 من 4 : الرمز المؤقت للحافظة (Keychain Passcode)")
    print("━" * 64)
    print("🔐 يُستخدم هذا الرمز المؤقت لحفظ وتشفير جلسة حسابك محلياً لكي لا تضطر")
    print("   لإدخال الإيميل والباسورد في كل مرة تقوم فيها بتحميل تطبيق.")
    kp = input(f"👈 أدخل الرمز المؤقت للحافظة (اضغط Enter لاعتماد الرمز [{current_pass}]): ").strip()
    if not kp:
        kp = current_pass

    print("\n⏳ جاري حفظ الجلسة والتأكد النهائي من حالة تسجيل الدخول...")
    ok_final, msg_final, acc_info = session.finalize_keychain_passphrase(kp)
    session.close()

    print("\n" + "=" * 64)
    if acc_info.get("logged_in"):
        print("🎉✅ تم تسجيل الدخول وتوثيق الحساب بنجاح تام! ✅🎉")
        print("-" * 64)
        print(f"   👤 اسم صاحب الحساب : {acc_info.get('name', 'غير معروف')}")
        print(f"   📧 البريد الإلكتروني: {acc_info.get('email', email)}")
        print(f"   🔑 الرمز المؤقت     : {kp}")
        print(f"   📁 مسار حفظ الجلسة  : {IPATOOL_DIR}")
        print("-" * 64)
        print("✨ يمكنك الآن إغلاق هذه النافذة والعودة للبرنامج لتحميل التطبيقات.")
    else:
        print("⚠️ تعذر التأكد النهائي من الجلسة:")
        print(f"   {msg_final}")
    print("=" * 64)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ تم إلغاء العملية من قِبل المستخدم.")
    except Exception as e:
        print(f"\n❌ حدث خطأ غير متوقع: {e}")
    print()
    input("اضغط Enter لإغلاق النافذة...")
