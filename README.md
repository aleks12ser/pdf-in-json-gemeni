# PDF to JSON Converter (Gemini API)

A Python script that processes PDF documents and converts their content into structured JSON format using Google Gemini.

## English Setup Guide

### 1. Get Gemini API Key
To use this project, you need an API key from Google AI Studio:
1. Go to [Google AI Studio](https://google.com).
2. Log in with your Google account.
3. Click **"Get API key"** and create a new key.

### 2. Configuration (.env)
Create a file named `.env` in the root directory of the project and add your key:
```env
GEMINI_API_KEY=your_actual_api_key_here
```

### 3. Installation & Run
1. Activate your virtual environment.
2. Install required packages (e.g., `google-genai`, `PyMuPDF`).
3. Run the script:
   ```bash
   python pdf_in_json.py
   ```

---

## Руководство по настройке (Русский)

Конвертер PDF в JSON с использованием Google Gemini для извлечения структурированных данных из документов.

### 1. Получение API-ключа Gemini
Для работы скрипта необходим токен доступа:
1. Перейдите в [Google AI Studio](https://google.com).
2. Авторизуйтесь под своим Google-аккаунтом.
3. Нажмите кнопку **"Get API key"** и сгенерируйте новый ключ.

### 2. Настройка окружения (.env)
Создайте файл с именем `.env` в корневой папке вашего проекта и вставьте туда полученный ключ:
```env
GEMINI_API_KEY=ваш_реальный_ключ_api
```

### 3. Установка и запуск
1. Активируйте ваше виртуальное окружение.
2. Установите необходимые библиотеки (например, `google-genai`, `PyMuPDF`).
3. Запустите скрипт:
   ```bash
   python pdf_in_json.py
   ```
