"""Очистка Markdown-страниц GitLab Handbook до простого текста.

Что делается:
- служебный блок в начале (front matter между ---) убирается, заголовок страницы
  (title) ставится первой строкой;
- блоки кода удаляются целиком, у `inline-кода` убираются только кавычки;
- ссылки [текст](url) превращаются в «текст», картинки удаляются;
- снимаются маркеры заголовков, списков, цитат, жирного и курсива;
- таблицы превращаются в строки с ячейками через табуляцию;
- шорткоды Hugo ({{< ... >}}, {{% ... %}}) и HTML-теги убираются, текст внутри остаётся.

Можно запустить и отдельно, на уже скачанной папке с .md:
    python clean_markdown.py downloads/
"""

import html
import re
import sys
from pathlib import Path

FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
FENCE = re.compile(r"^\s*(```|~~~)")
# Теги, после которых в HTML начинается новая строка
BLOCK_TAGS = re.compile(r"</?(p|div|br|li|ul|ol|tr|table|h[1-6]|details|summary|blockquote|hr)\b[^>]*>", re.I)
CELL_TAGS = re.compile(r"</t[dh]\s*>", re.I)


def _front_matter_title(front):
    match = re.search(r"^title:\s*(.+)$", front, re.M)
    return match.group(1).strip().strip("\"'") if match else None


def _strip_inline(text):
    """Убирает разметку внутри одной строки."""
    text = re.sub(r"!\[[^\]]*\]\((?:[^()]|\([^()]*\))*\)", "", text)  # картинки
    text = re.sub(r"\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)", r"\1", text)  # [текст](url)
    text = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", text)  # [текст][ссылка]
    text = re.sub(r"\[\^[^\]]+\]", "", text)  # сноски [^1]
    text = re.sub(r"<(https?://[^>\s]+)>", r"\1", text)  # <https://...>
    text = re.sub(r"\{\{[<%].*?[%>]\}\}", "", text)  # шорткоды Hugo
    text = re.sub(r"\{[:#][^}]*\}", "", text)  # {#якорь}, {: .класс}
    text = re.sub(r"`([^`]*)`", r"\1", text)  # `код`
    text = re.sub(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", r"\2", text)  # **жирный**
    text = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"\1", text)  # *курсив*
    text = re.sub(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", r"\1", text)  # _курсив_
    text = re.sub(r"~~(.+?)~~", r"\1", text)  # ~~зачёркнутый~~
    return text


def _strip_html(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<(script|style)\b.*?</\1>", "", text, flags=re.S | re.I)
    text = CELL_TAGS.sub("\t", text)
    text = BLOCK_TAGS.sub("\n", text)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    return html.unescape(text)


def clean_markdown(md):
    title = None
    match = FRONT_MATTER.match(md)
    if match:
        title = _front_matter_title(match.group(1))
        md = md[match.end():]

    lines, in_code = [], False
    for line in md.splitlines():
        if FENCE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        stripped = line.strip()
        if re.fullmatch(r"\|?[\s:|-]*-{3,}[\s:|-]*\|?", stripped):  # разделитель таблицы |---|---|
            continue
        if re.fullmatch(r"([-*_]\s*){3,}", stripped):  # горизонтальная линия
            continue
        if re.match(r"^\s*\[[^\]^]+\]:\s*\S+", line):  # определение ссылки [x]: url
            continue
        line = re.sub(r"^\s*(>\s*)+", "", line)  # цитаты
        line = re.sub(r"^\s*#{1,6}\s+", "", line)  # заголовки
        line = re.sub(r"^\s*[-*+]\s+(\[[ xX]\]\s+)?", "", line)  # маркированные списки и чекбоксы
        line = re.sub(r"^\s+(?=\d+[.)]\s)", "", line)  # отступ у нумерованных списков
        if stripped.startswith("|"):  # строка таблицы
            line = "\t".join(cell.strip() for cell in stripped.strip("|").split("|"))
        lines.append(_strip_inline(line))

    text = _strip_html("\n".join(lines))
    # Добираем то, что не видно построчно: жирный текст на несколько строк
    # и маркеры списков, оказавшиеся в начале строки после удаления картинок и HTML
    text = re.sub(r"\*\*((?:(?!\n\s*\n).)+?)\*\*", r"\1", text, flags=re.S)
    text = re.sub(r"^[ \t]*[-*+][ \t]+", "", text, flags=re.M)
    text = re.sub(r"[ \t]+\n", "\n", text)  # хвостовые пробелы
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if title:
        text = f"{title}\n\n{text}"
    return text + "\n"


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        sys.exit("Использование: python clean_markdown.py <папка с .md файлами>")
    for md_path in Path(sys.argv[1]).rglob("*.md"):
        txt_path = md_path.with_suffix(".txt")
        txt_path.write_text(clean_markdown(md_path.read_text(encoding="utf-8")), encoding="utf-8")
        print(txt_path)
