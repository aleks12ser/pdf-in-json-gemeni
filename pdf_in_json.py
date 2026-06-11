import os
import json
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import fitz  # PyMuPDF

# Импортируем компоненты PyQt6
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QFileDialog, QTextEdit, QLabel, QProgressBar)
from PyQt6.QtCore import QThread, pyqtSignal
# ==========================================
# 1. НАСТРОЙКА Gemini & Pydantic
# ==========================================
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")


class PageData(BaseModel):
    has_formulas: bool = Field(description="Есть ли математические или химические формулы на странице")
    formulas: list[str] = Field(
        description="Список всех найденных формул на странице, переведенных в формат LaTeX (например, $E=mc^2$)")
    has_images: bool = Field(description="Есть ли на странице иллюстрации, графики, фотографии или схемы (не формулы)")
    images_description: list[str] = Field(
        description="Подробное описание каждого изображения/графика/схемы на странице. Если изображений нет - пустой список")
    full_text: str = Field(
        description="Полный структурированный текст страницы, включая распознанный текст с картинок, если он там есть. Формулы внутри текста тоже должны быть в формате LaTeX")


# ==========================================
# 2. ПОТОК ДЛЯ ВЫЧИСЛЕНИЙ (Чтобы GUI не зависал)
# ==========================================
class PDFProcessingThread(QThread):
    # Сигналы для обновления интерфейса из другого потока
    progress_changed = pyqtSignal(int)
    status_changed = pyqtSignal(str)
    processing_finished = pyqtSignal(dict, str)

    def __init__(self, pdf_path):
        super().__init__()
        self.pdf_path = pdf_path

    def process_page_with_gemini(self, client, page) -> PageData:
        zoom = 2
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        image_bytes = pix.tobytes("jpeg")

        prompt = (
            "Проанализируй этот лист из PDF-документа. Тебе нужно извлечь весь текст. "
            "Если на странице есть математические, физические или химические формулы, обязательно "
            "переведи их в формат LaTeX. Если на странице есть изображения (графики, схемы, рисунки), "
            "детально опиши, что на них изображено."
        )

        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PageData,
                temperature=0.1
            ),
        )
        return PageData.model_validate_json(response.text)

    def run(self):
        if not api_key:
            self.status_changed.emit("Ошибка: GEMINI_API_KEY не найден в .env")
            return

        client = genai.Client(api_key=api_key)
        doc = fitz.open(self.pdf_path)
        total_pages = len(doc)

        final_result = {
            "document_name": os.path.basename(self.pdf_path),
            "total_pages": total_pages,
            "pages": []
        }

        for page_num in range(total_pages):
            page = doc.load_page(page_num)
            self.status_changed.emit(f"Обработка страницы {page_num + 1} из {total_pages}...")

            # Способ 1: Извлекаем обычный текст
            raw_text = page.get_text().strip()

            if len(raw_text) < 10:
                self.status_changed.emit(
                    f"Страница {page_num + 1}: Текст не найден. Рендерим JPEG и отправляем в Gemini...")
                try:
                    gemini_data = self.process_page_with_gemini(client, page)
                    page_json = {
                        "page_number": page_num + 1,
                        "extraction_method": "gemini_vision_ocr",
                        "has_formulas": gemini_data.has_formulas,
                        "formulas": gemini_data.formulas,
                        "has_images": gemini_data.has_images,
                        "images_description": gemini_data.images_description,
                        "text": gemini_data.full_text
                    }
                except Exception as e:
                    page_json = {
                        "page_number": page_num + 1,
                        "extraction_method": "failed",
                        "text": f"[ОШИБКА: {str(e)}]"
                    }
            else:
                page_json = {
                    "page_number": page_num + 1,
                    "extraction_method": "traditional_text_layer",
                    "has_formulas": False,
                    "formulas": [],
                    "has_images": False,
                    "images_description": [],
                    "text": raw_text
                }

            final_result["pages"].append(page_json)

            # Считаем процент прогресса
            progress = int(((page_num + 1) / total_pages) * 100)
            self.progress_changed.emit(progress)

        doc.close()

        # Генерируем имя выходного файла
        output_filename = self.pdf_path.replace(".pdf", "_output.json")
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(final_result, f, ensure_ascii=False, indent=4)

        self.processing_finished.emit(final_result, output_filename)


# ==========================================
# 3. ГРАФИЧЕСКИЙ ИНТЕРФЕЙС (PyQt5 Window)
# ==========================================
class PDFConverterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        # Настройка окна
        self.setWindowTitle('Умный PDF в JSON Конвертер (Hybrid & Gemini)')
        self.setGeometry(300, 300, 600, 450)

        # Элементы интерфейса
        self.btn_open = QPushButton('Выбрать PDF файл', self)
        self.btn_open.clicked.connect(self.showDialog)

        self.lbl_file = QLabel('Файл не выбран', self)
        self.lbl_status = QLabel('Статус: Ожидание', self)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)

        self.text_preview = QTextEdit(self)
        self.text_preview.setReadOnly(True)
        self.text_preview.setPlaceholderText("Здесь будет отображаться лог и превью JSON...")

        # Разметка (Layout)
        vbox = QVBoxLayout()

        hbox_file = QHBoxLayout()
        hbox_file.addWidget(self.btn_open)
        hbox_file.addWidget(self.lbl_file)

        vbox.addLayout(hbox_file)
        vbox.addWidget(self.lbl_status)
        vbox.addWidget(self.progress_bar)
        vbox.addWidget(self.text_preview)

        self.setLayout(vbox)

    def showDialog(self):
        # Диалоговое окно выбора файла
        fname, _ = QFileDialog.getOpenFileName(self, 'Открыть PDF файл', '', 'PDF Files (*.pdf)')

        if fname:
            self.lbl_file.setText(os.path.basename(fname))
            self.text_preview.clear()
            self.progress_bar.setValue(0)

            # Запускаем фоновый поток обработки
            self.thread = PDFProcessingThread(fname)
            self.thread.status_changed.connect(self.update_status)
            self.thread.progress_changed.connect(self.update_progress)
            self.thread.processing_finished.connect(self.on_finished)

            self.btn_open.setEnabled(False)  # Блокируем кнопку на время работы
            self.thread.start()

    def update_status(self, text):
        self.lbl_status.setText(f"Статус: {text}")
        self.text_preview.append(text)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def on_finished(self, result_dict, output_path):
        self.btn_open.setEnabled(True)
        self.lbl_status.setText("Статус: Готово!")
        self.text_preview.append(f"\n🎉 Обработка завершена!\nФайл сохранен в: {output_path}\n")
        # Выводим красивое превью получившегося JSON в текстовое поле
        self.text_preview.append(json.dumps(result_dict, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    # Проверяем PyQt5 перед запуском
    try:
        app = QApplication(sys.argv)
        ex = PDFConverterApp()
        ex.show()
        # Вместо sys.exit(app.exec_()) пишем:
        sys.exit(app.exec())  # в PyQt6 убрали нижнее подчеркивание у exec_
    except ModuleNotFoundError:
        print("Ошибка: Установите PyQt5 командой: pip install PyQt5")