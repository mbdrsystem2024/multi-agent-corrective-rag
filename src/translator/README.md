## Переводчик документов

переводит с английского на русский через API Gemini

### Установка requirements
```
pip install -r src/translator/requirements.txt
```
Скопируйте `.env.example` в `.env` и впишите ключ Google AI Studio.

### Запуск
```
python src/translator/main_translator.py
```
изменить пути ф самом файле:
Читает `data/raw/manifest.csv`, 
пишет переводы в `data/translated_raw/`.
путь к промту: `prompts/translator_llm_prompt/prompt.txt`.

### Если что-то не перевелось
Файлы, не прошедшие проверку или упавшие по ошибке API, попадают в
`not_processed.csv` рядом с манифестом. Его можно подать как манифест
для повторного прогона. Отклонённые ответы модели лежат в `_rejected/`.