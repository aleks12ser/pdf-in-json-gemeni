import os
import json
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import fitz  # PyMuPDF

# Import PyQt6 components
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QFileDialog, QTextEdit, QLabel, QProgressBar)
from PyQt6.QtCore import QThread, pyqtSignal

# ==========================================
# 1. Gemini & Pydantic Setup
# ==========================================
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")


class PageData(BaseModel):
    has_formulas: bool = Field(
        description="Whether the page contains mathematical or chemical formulas"
    )

    formulas: list[str] = Field(
        description="List of all formulas found on the page converted to LaTeX format (e.g. $E=mc^2$)"
    )

    has_images: bool = Field(
        description="Whether the page contains illustrations, charts, photos, or diagrams (excluding formulas)"
    )

    images_description: list[str] = Field(
        description="Detailed description of each image/chart/diagram on the page. Empty list if there are no images"
    )

    full_text: str = Field(
        description="Full structured text of the page, including text recognized from images. Formulas inside the text should also be in LaTeX format"
    )


# ==========================================
# 2. WORKER THREAD (Prevents GUI from freezing)
# ==========================================
class PDFProcessingThread(QThread):
    # Signals for updating the interface from another thread
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
            "Analyze this PDF page. Extract all text. "
            "If the page contains mathematical, physical, or chemical formulas, "
            "convert them into LaTeX format. "
            "If the page contains images (charts, diagrams, drawings), "
            "describe them in detail."
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
            self.status_changed.emit("Error: GEMINI_API_KEY was not found in .env")
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
            self.status_changed.emit(
                f"Processing page {page_num + 1} of {total_pages}..."
            )

            # Method 1: Extract regular text
            raw_text = page.get_text().strip()

            if len(raw_text) < 10:
                self.status_changed.emit(
                    f"Page {page_num + 1}: No text found. Rendering JPEG and sending to Gemini..."
                )

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
                        "text": f"[ERROR: {str(e)}]"
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

            # Calculate progress percentage
            progress = int(((page_num + 1) / total_pages) * 100)
            self.progress_changed.emit(progress)

        doc.close()

        # Generate output filename
        output_filename = self.pdf_path.replace(".pdf", "_output.json")

        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(final_result, f, ensure_ascii=False, indent=4)

        self.processing_finished.emit(final_result, output_filename)


# ==========================================
# 3. GRAPHICAL INTERFACE (PyQt6 Window)
# ==========================================
class PDFConverterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        # Window setup
        self.setWindowTitle('Smart PDF to JSON Converter (Hybrid & Gemini)')
        self.setGeometry(300, 300, 600, 450)

        # UI elements
        self.btn_open = QPushButton('Select PDF File', self)
        self.btn_open.clicked.connect(self.showDialog)

        self.lbl_file = QLabel('No file selected', self)
        self.lbl_status = QLabel('Status: Waiting', self)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)

        self.text_preview = QTextEdit(self)
        self.text_preview.setReadOnly(True)
        self.text_preview.setPlaceholderText(
            "Logs and JSON preview will be displayed here..."
        )

        # Layout
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
        # File selection dialog
        fname, _ = QFileDialog.getOpenFileName(
            self,
            'Open PDF File',
            '',
            'PDF Files (*.pdf)'
        )

        if fname:
            self.lbl_file.setText(os.path.basename(fname))
            self.text_preview.clear()
            self.progress_bar.setValue(0)

            # Start background processing thread
            self.thread = PDFProcessingThread(fname)
            self.thread.status_changed.connect(self.update_status)
            self.thread.progress_changed.connect(self.update_progress)
            self.thread.processing_finished.connect(self.on_finished)

            self.btn_open.setEnabled(False)
            self.thread.start()

    def update_status(self, text):
        self.lbl_status.setText(f"Status: {text}")
        self.text_preview.append(text)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def on_finished(self, result_dict, output_path):
        self.btn_open.setEnabled(True)
        self.lbl_status.setText("Status: Completed!")
        self.text_preview.append(
            f"\n🎉 Processing completed!\nFile saved to: {output_path}\n"
        )

        # Display formatted JSON preview
        self.text_preview.append(
            json.dumps(result_dict, ensure_ascii=False, indent=2)
        )


if __name__ == '__main__':
    # Check PyQt6 before launch
    try:
        app = QApplication(sys.argv)
        ex = PDFConverterApp()
        ex.show()

        # In PyQt6 exec_() was renamed to exec()
        sys.exit(app.exec())

    except ModuleNotFoundError:
        print("Error: Install PyQt6 with: pip install PyQt6")

