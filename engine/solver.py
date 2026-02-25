"""
Modulo de resolucao de tarefas com Claude API.
Inclui deteccao de formato e criacao de arquivos.
"""

import base64
import json
import os
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path

import anthropic
from docx import Document
from docx.shared import Pt
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from pptx import Presentation
from pptx.util import Pt as PptxPt
from loguru import logger

CLAUDE_MAX_RETRIES = 3
FORMATOS_CODIGO = ["py", "js", "ts", "java", "c", "cpp", "css", "sql"]
FORMATOS_ARQUIVO = ["html", "docx", "xlsx", "pptx", "zip"] + FORMATOS_CODIGO
TODOS_FORMATOS = FORMATOS_ARQUIVO + ["txt", "texto"]


def detectar_formato_resposta(content: str) -> str:
    """Detecta o formato esperado baseado nas instrucoes da pagina."""
    content_lower = content.lower()

    if any(x in content_lower for x in [".html", "arquivo html", "html file", "pagina html", "codigo html"]):
        return "html"
    if any(x in content_lower for x in [".docx", ".doc", "word", "documento word", "arquivo word"]):
        return "docx"
    if any(x in content_lower for x in [".xlsx", ".xls", "excel", "planilha", "spreadsheet"]):
        return "xlsx"
    if any(x in content_lower for x in [".pptx", ".ppt", "powerpoint", "apresentacao", "slides"]):
        return "pptx"
    if any(x in content_lower for x in [".py", "python", "codigo python", "script python"]):
        return "py"
    if any(x in content_lower for x in [".js", "javascript"]):
        return "js"
    if any(x in content_lower for x in [".ts", "typescript"]):
        return "ts"
    if any(x in content_lower for x in [".java", "codigo java", "programa java"]):
        return "java"
    if any(x in content_lower for x in ["linguagem c ", "codigo em c ", "programa em c ", "arquivo .c"]):
        return "c"
    if any(x in content_lower for x in [".cpp", "c++", "codigo c++", "programa c++"]):
        return "cpp"
    if any(x in content_lower for x in [".css", "arquivo css", "folha de estilo"]):
        return "css"
    if any(x in content_lower for x in [".sql", "script sql", "consulta sql", "query sql"]):
        return "sql"
    if any(x in content_lower for x in [".zip", "arquivo zip", "compactado"]):
        return "zip"

    return "texto"


def detectar_formato_da_resposta(resposta: str) -> str | None:
    """Detecta o formato da resposta do Claude."""
    resposta_lower = resposta.lower()

    formatos_validos = "|".join(TODOS_FORMATOS)
    match = re.search(rf'\[formato:\s*({formatos_validos})\]', resposta_lower)
    if match:
        return match.group(1)

    if any(tag in resposta_lower for tag in ["<!doctype html", "<html", "<head>", "<body>"]):
        return "html"
    if "```html" in resposta_lower:
        return "html"
    if "```python" in resposta_lower or "```py" in resposta_lower:
        return "py"
    if "```javascript" in resposta_lower or "```js" in resposta_lower:
        return "js"
    if "```typescript" in resposta_lower or "```ts" in resposta_lower:
        return "ts"
    if "```java" in resposta_lower:
        return "java"
    if "```cpp" in resposta_lower or "```c++" in resposta_lower:
        return "cpp"
    if "```c\n" in resposta_lower:
        return "c"
    if "```css" in resposta_lower:
        return "css"
    if "```sql" in resposta_lower:
        return "sql"

    return None


def remover_marcador_formato(resposta: str) -> str:
    return re.sub(r'\[FORMATO:\s*\w+\]\s*\n?', '', resposta, count=1, flags=re.IGNORECASE).strip()


# ============================================================
# CRIACAO DE ARQUIVOS
# ============================================================

def criar_arquivo_html(conteudo: str, nome_arquivo: str, data_dir: Path) -> str:
    if "<html" in conteudo.lower() or "<!doctype" in conteudo.lower():
        html_content = conteudo
    else:
        html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{nome_arquivo}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        h1, h2, h3 {{ color: #333; }}
    </style>
</head>
<body>
{conteudo}
</body>
</html>"""

    filepath = data_dir / f"{nome_arquivo}.html"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return str(filepath)


def criar_arquivo_docx(conteudo: str, nome_arquivo: str, data_dir: Path) -> str:
    doc = Document()
    doc.add_heading(nome_arquivo, 0)

    for linha in conteudo.split('\n'):
        linha_stripped = linha.strip()
        if not linha_stripped:
            doc.add_paragraph("")
            continue
        if linha_stripped.startswith('# '):
            doc.add_heading(linha_stripped[2:], level=1)
        elif linha_stripped.startswith('## '):
            doc.add_heading(linha_stripped[3:], level=2)
        elif linha_stripped.startswith('### '):
            doc.add_heading(linha_stripped[4:], level=3)
        elif linha_stripped.startswith('- ') or linha_stripped.startswith('* '):
            doc.add_paragraph(linha_stripped[2:], style='List Bullet')
        elif re.match(r'^\d+\.\s', linha_stripped):
            texto = re.sub(r'^\d+\.\s', '', linha_stripped)
            doc.add_paragraph(texto, style='List Number')
        else:
            p = doc.add_paragraph(linha_stripped)
            p.style.font.size = Pt(11)

    filepath = data_dir / f"{nome_arquivo}.docx"
    doc.save(str(filepath))
    return str(filepath)


def criar_arquivo_xlsx(conteudo: str, nome_arquivo: str, data_dir: Path) -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = nome_arquivo[:31]

    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font_white = Font(bold=True, size=11, color="FFFFFF")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    linhas = conteudo.strip().split('\n')
    is_first_data_row = True

    for linha in linhas:
        linha = linha.strip()
        if not linha or re.match(r'^[\|\-\s:]+$', linha):
            continue

        if '|' in linha:
            cells = [c.strip() for c in linha.split('|') if c.strip()]
            for j, cell in enumerate(cells):
                c = ws.cell(row=ws.max_row + (0 if is_first_data_row else 1), column=j + 1, value=cell)
                c.border = thin_border
                if is_first_data_row:
                    c.font = header_font_white
                    c.fill = header_fill
                    c.alignment = Alignment(horizontal='center')
            is_first_data_row = False
        else:
            ws.cell(row=ws.max_row + 1, column=1, value=linha)

    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_length + 4, 50)

    filepath = data_dir / f"{nome_arquivo}.xlsx"
    wb.save(str(filepath))
    return str(filepath)


def criar_arquivo_pptx(conteudo: str, nome_arquivo: str, data_dir: Path) -> str:
    prs = Presentation()

    slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = nome_arquivo
    slide.placeholders[1].text = datetime.now().strftime("%d/%m/%Y")

    slides_content = []
    current_slide = {"titulo": "", "conteudo": []}

    for linha in conteudo.split('\n'):
        linha = linha.strip()
        if linha.startswith('# ') or linha.startswith('## '):
            if current_slide["titulo"] or current_slide["conteudo"]:
                slides_content.append(current_slide)
            titulo = re.sub(r'^#+\s*', '', linha)
            current_slide = {"titulo": titulo, "conteudo": []}
        elif linha:
            current_slide["conteudo"].append(linha)

    if current_slide["titulo"] or current_slide["conteudo"]:
        slides_content.append(current_slide)

    for sc in slides_content:
        slide_layout = prs.slide_layouts[1]
        slide = prs.slides.add_slide(slide_layout)
        slide.shapes.title.text = sc["titulo"]
        body = slide.placeholders[1]
        tf = body.text_frame
        tf.clear()
        for i, linha in enumerate(sc["conteudo"]):
            if i == 0:
                tf.text = linha
            else:
                p = tf.add_paragraph()
                p.text = linha
                p.font.size = PptxPt(16)

    filepath = data_dir / f"{nome_arquivo}.pptx"
    prs.save(str(filepath))
    return str(filepath)


def criar_arquivo_codigo(conteudo: str, nome_arquivo: str, extensao: str, data_dir: Path) -> str:
    conteudo = re.sub(r'^```\w*\n?', '', conteudo)
    conteudo = re.sub(r'\n?```$', '', conteudo)

    filepath = data_dir / f"{nome_arquivo}.{extensao}"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return str(filepath)


def criar_arquivo_zip(arquivos: list, nome_arquivo: str, data_dir: Path) -> str:
    filepath = data_dir / f"{nome_arquivo}.zip"
    with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
        for arq in arquivos:
            zf.write(arq, os.path.basename(arq))
    return str(filepath)


def criar_arquivo_resposta(conteudo: str, nome_tarefa: str, formato: str, data_dir: Path) -> str:
    nome_limpo = re.sub(r'[^\w\s-]', '', nome_tarefa)[:50].strip().replace(' ', '_')

    if formato == "html":
        return criar_arquivo_html(conteudo, nome_limpo, data_dir)
    elif formato == "docx":
        return criar_arquivo_docx(conteudo, nome_limpo, data_dir)
    elif formato == "xlsx":
        return criar_arquivo_xlsx(conteudo, nome_limpo, data_dir)
    elif formato == "pptx":
        return criar_arquivo_pptx(conteudo, nome_limpo, data_dir)
    elif formato in FORMATOS_CODIGO:
        return criar_arquivo_codigo(conteudo, nome_limpo, formato, data_dir)
    else:
        filepath = data_dir / f"{nome_limpo}.txt"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(conteudo)
        return str(filepath)


def extrair_multiplos_arquivos(resposta: str, formato: str, nome_tarefa: str, data_dir: Path) -> list:
    """Extrai multiplos arquivos da resposta do Claude."""
    arquivos = []
    nome_limpo = re.sub(r'[^\w\s-]', '', nome_tarefa)[:50].strip().replace(' ', '_')

    if formato == "html":
        blocos_html = re.findall(r'```html\s*\n(.*?)```', resposta, re.DOTALL)
        if not blocos_html:
            blocos_html = re.findall(r'(<!DOCTYPE html>.*?</html>)', resposta, re.DOTALL | re.IGNORECASE)
        if not blocos_html:
            blocos_html = [resposta]

        for i, bloco in enumerate(blocos_html):
            bloco = bloco.strip()
            if not bloco:
                continue
            if "<html" not in bloco.lower():
                bloco = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>{nome_tarefa} - Exercicio {i+1}</title></head>
<body>{bloco}</body>
</html>"""
            sufixo = f"_{i+1}" if len(blocos_html) > 1 else ""
            filepath = data_dir / f"{nome_limpo}{sufixo}.html"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(bloco)
            arquivos.append(str(filepath))

    elif formato in FORMATOS_CODIGO:
        lang_map = {
            "py": ["python", "py"], "js": ["javascript", "js"],
            "ts": ["typescript", "ts"], "java": ["java"], "c": ["c"],
            "cpp": ["cpp", "c\\+\\+"], "css": ["css"], "sql": ["sql"],
        }
        langs = lang_map.get(formato, [formato])
        pattern = r'```(?:' + '|'.join(langs) + r')\s*\n(.*?)```'
        blocos = re.findall(pattern, resposta, re.DOTALL)

        if not blocos:
            cleaned = re.sub(r'^```\w*\n?', '', resposta)
            cleaned = re.sub(r'\n?```$', '', cleaned)
            blocos = [cleaned]

        for i, bloco in enumerate(blocos):
            bloco = bloco.strip()
            if not bloco:
                continue
            sufixo = f"_{i+1}" if len(blocos) > 1 else ""
            filepath = data_dir / f"{nome_limpo}{sufixo}.{formato}"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(bloco)
            arquivos.append(str(filepath))

    return arquivos


def extrair_projeto_multi_arquivo(resposta: str, nome_tarefa: str, data_dir: Path) -> list:
    """Extrai projeto multi-arquivo e zipa."""
    arquivos = []
    nome_limpo = re.sub(r'[^\w\s-]', '', nome_tarefa)[:50].strip().replace(' ', '_')

    blocos = re.findall(r'```(\w+)\s*\n(.*?)```', resposta, re.DOTALL)
    ext_map = {
        "html": "html", "css": "css", "javascript": "js", "js": "js",
        "typescript": "ts", "ts": "ts", "python": "py", "py": "py",
        "java": "java", "c": "c", "cpp": "cpp", "sql": "sql",
    }

    contadores = {}
    for lang, conteudo in blocos:
        ext = ext_map.get(lang.lower(), lang.lower())
        conteudo = conteudo.strip()
        if not conteudo:
            continue
        contadores[ext] = contadores.get(ext, 0) + 1
        sufixo = f"_{contadores[ext]}" if contadores[ext] > 1 else ""
        filepath = data_dir / f"{nome_limpo}{sufixo}.{ext}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(conteudo)
        arquivos.append(str(filepath))

    if arquivos:
        tipos = set(os.path.splitext(a)[1] for a in arquivos)
        if len(tipos) > 1:
            zip_path = criar_arquivo_zip(arquivos, nome_limpo, data_dir)
            return [zip_path]

    return arquivos


# ============================================================
# CLAUDE API
# ============================================================

def resolver_com_claude(tarefa: dict, api_key: str) -> str | None:
    """Resolve tarefa usando Claude API com retry."""
    client = anthropic.Anthropic(api_key=api_key)

    formatos_str = ", ".join(TODOS_FORMATOS)

    prompt = f"""Voce e um assistente que resolve tarefas academicas.

TAREFA: {tarefa.get('nome', 'Sem nome')}

INSTRUCOES DA TAREFA: {tarefa.get('instrucoes', 'Nao especificadas')}

Analise as imagens (se houver) e forneca uma solucao completa e profissional.

REGRA OBRIGATORIA - PRIMEIRA LINHA:
A primeira linha da sua resposta DEVE ser EXATAMENTE no formato:
[FORMATO: xxx]
Onde xxx e um dos seguintes: {formatos_str}
Escolha o formato baseado no que a tarefa pede como entrega.
Exemplos:
- Se pede pagina(s) HTML -> [FORMATO: html]
- Se pede documento/trabalho/pesquisa/relatorio Word -> [FORMATO: docx]
- Se pede planilha/tabela Excel -> [FORMATO: xlsx]
- Se pede apresentacao/slides PowerPoint -> [FORMATO: pptx]
- Se pede codigo Python -> [FORMATO: py]
- Se pede codigo JavaScript -> [FORMATO: js]
- Se pede codigo TypeScript -> [FORMATO: ts]
- Se pede codigo Java -> [FORMATO: java]
- Se pede codigo C -> [FORMATO: c]
- Se pede codigo C++ -> [FORMATO: cpp]
- Se pede CSS/folha de estilo -> [FORMATO: css]
- Se pede SQL/consultas banco de dados -> [FORMATO: sql]
- Se pede multiplos arquivos (ex: HTML+CSS+JS) -> [FORMATO: zip]
- Se pede resposta em texto simples na caixa -> [FORMATO: texto]

REGRAS DA RESPOSTA:
1. Se for HTML, gere codigo HTML completo para CADA exercicio
2. Se houver MULTIPLOS exercicios do mesmo tipo, separe cada um com um bloco de codigo distinto
3. Se for MULTIPLOS tipos de arquivo, coloque cada um em seu bloco correspondente
4. Se for DOCX, gere texto bem estruturado com # para headers
5. Se for XLSX, formate como tabela usando | para colunas
6. Se for PPTX, use # para titulo de cada slide
7. Se for codigo, deve ser funcional, completo e bem comentado
8. Responda APENAS com o conteudo solicitado
9. Seja detalhado, completo e profissional"""

    content = [{"type": "text", "text": prompt}]

    for screenshot_path in tarefa.get("screenshots", [])[:10]:
        try:
            with open(screenshot_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_data
                }
            })
        except Exception:
            pass

    # Lista de modelos para tentar (fallback)
    modelos = [
        ("claude-sonnet-4-20250514", "Sonnet 4"),
        ("claude-3-5-haiku-20241022", "Haiku 3.5"),
    ]

    for modelo_id, modelo_nome in modelos:
        logger.info(f"Tentando com {modelo_nome}...")

        for tentativa in range(1, CLAUDE_MAX_RETRIES + 1):
            try:
                response = client.messages.create(
                    model=modelo_id,
                    max_tokens=8096,
                    messages=[{"role": "user", "content": content}]
                )
                logger.info(f"Sucesso com {modelo_nome}!")
                return response.content[0].text
            except Exception as e:
                logger.error(f"Erro na API {modelo_nome} (tentativa {tentativa}/{CLAUDE_MAX_RETRIES}): {e}")
                if tentativa < CLAUDE_MAX_RETRIES:
                    time.sleep(tentativa * 5)

        # Se chegou aqui, falhou todas as tentativas com este modelo
        logger.warning(f"{modelo_nome} falhou, tentando proximo modelo...")

    # Todos os modelos falharam
    logger.error("Todos os modelos falharam!")
    return None
