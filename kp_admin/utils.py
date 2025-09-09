
import os, io
from flask import current_app
from slugify import slugify
from xhtml2pdf import pisa

def allowed_file(filename: str) -> bool:
    exts = current_app.config.get("ALLOWED_EXTENSIONS", {"pdf", "html"})
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts

def ensure_uploads_folder():
    folder = os.path.join(current_app.instance_path, current_app.config.get("UPLOAD_FOLDER", "uploads/kp"))
    os.makedirs(folder, exist_ok=True)
    return folder

def save_html_as_pdf(html: str, out_path: str) -> bool:
    """
    Simple HTML -> PDF using xhtml2pdf. Returns True/False.
    """
    with open(out_path, "wb") as f:
        result = pisa.CreatePDF(io.StringIO(html), dest=f)
    return not result.err

def render_kp_html(lead, blocks: dict) -> str:
    """
    Render simple KP HTML from lead data + selected blocks.
    """
    title = f"КП для {lead.company or lead.contact_name or 'клиента'}"
    items_html = "".join([f"<li><strong>{k}:</strong> {v}</li>" for k, v in blocks.items()])
    body = f"""
    <!doctype html>
    <html lang="ru">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>{title}</title>
        <style>
          body{{font-family: Arial, sans-serif; margin: 24px;}}
          header, footer{{border-top: 4px solid #22c55e; padding: 12px 0;}}
          h1{{margin: 0 0 8px;}}
          .meta{{color:#555; font-size:14px; margin-bottom:16px;}}
          .section{{margin:16px 0; padding:12px; border:1px solid #eee; border-radius:8px;}}
          ul{{margin:0; padding-left:20px;}}
        </style>
      </head>
      <body>
        <header>
          <h1>{title}</h1>
          <div class="meta">Email: {lead.email or '-'} • Тел: {lead.phone or '-'}</div>
        </header>
        <div class="section">
          <h3>Параметры проекта</h3>
          <ul>
            <li>Тип сайта: {lead.site_type or '-'}</li>
            <li>Цель: {lead.goal or '-'}</li>
            <li>Аудитория: {lead.audience or '-'}</li>
            <li>Бюджет: {lead.budget or '-'}</li>
            <li>Срок: {lead.deadline or '-'}</li>
          </ul>
        </div>
        <div class="section">
          <h3>Выбранные блоки</h3>
          <ul>{items_html}</ul>
        </div>
        <footer>
          <small>Сформировано админ‑панелью • {slugify(title)}</small>
        </footer>
      </body>
    </html>
    """
    return body
