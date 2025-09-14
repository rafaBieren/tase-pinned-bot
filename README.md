# TASE Pinned Bot

בוט טלגרם שמביא נתונים מהבורסה הישראלית ומפרסם עדכונים על מדדי ת״א.

## תכונות

- **עדכון מדדים מרובים**: ת״א-35, ת״א-125, ת״א-90 ועוד
- **הודעות HTML מסודרות**: פורמט יפה עם שינויי אחוזים וחצים
- **טיפול בשגיאות**: fallback לנתונים דמה במקרה של בעיות מקור נתונים
- **תמיכה בהודעות מוצמדות**: אפשרות לעדכן הודעה אחת במקום לשלוח חדשות

## התקנה

1. **התקן תלויות**:
   ```bash
   pip install -r requirements.txt
   ```

2. **צור קובץ `.env`**:
   ```bash
   # Telegram Bot Configuration
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT=your_chat_id_here
   
   # Timezone
   TIMEZONE=Asia/Jerusalem
   
   # Indices Configuration (name=symbol pairs, comma-separated)
   INDICES=TA-35=^TA35,TA-125=^TA125,TA-90=^TA90
   
   # Update intervals (in seconds)
   UPDATE_INTERVAL_SEC=60
   OFF_HOURS_INTERVAL_SEC=300
   
   # State file path
   STATE_PATH=state.json
   ```

3. **הגדר בוט טלגרם**:
   - צור בוט חדש עם @BotFather
   - העתק את הטוקן לקובץ `.env`
   - הוסף את הבוט לערוץ/קבוצה שלך
   - העתק את מזהה הערוץ/הקבוצה לקובץ `.env`

## שימוש

### שליחת עדכון חד-פעמי
```bash
python -m src.main
```

### בדיקת חיבור
```bash
python -m src.smoke
```

## מבנה הפרויקט

- `src/main.py` - נקודת כניסה ראשית
- `src/indices.py` - הבאת נתונים ממקורות שונים
- `src/formatter.py` - עיצוב הודעות HTML
- `src/telegram_client.py` - ממשק לטלגרם
- `src/settings.py` - קונפיגורציה
- `src/state.py` - שמירת מצב (הודעות מוצמדות)

## פתרון בעיות

### שגיאת curl_cffi
אם אתה מקבל שגיאות `curl_cffi.requests has no attribute 'exceptions'`, הקוד כבר מטפל בזה אוטומטית על ידי הגדרת `YF_USE_CURL_CFFI=false`.

### Rate Limiting מ-Yahoo Finance
אם אתה מקבל שגיאות `Too Many Requests`, הקוד יעבור לנתונים דמה אוטומטית. לפתרון קבוע, חכה כמה דקות או השתמש במקור נתונים אחר.

## פיתוח

הפרויקט מוכן להרחבה:
- הוספת מקורות נתונים נוספים
- יישום לופ עדכון מחזורי
- הוספת מדדים נוספים
- שיפור עיצוב ההודעות

## רישיון

MIT
