import re

LIST_ITEM = re.compile(r"^\s*(\d+\.|[-•*–])\s")


def split_paragraphs(text):
    """Абзацы = блоки строк между пустыми строками."""
    paragraphs, current = [], []
    for line in text.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    return paragraphs


def check_translation(src, dst):
    """None — перевод в порядке, иначе строка с описанием проблемы."""
    if dst.strip() == src.strip():
        return "перевод совпадает с оригиналом"
    if len(dst) < len(src) * 0.5:
        return "подозрительно короткий перевод"

    src_par = split_paragraphs(src)
    dst_par = split_paragraphs(dst)
    if len(src_par) != len(dst_par):
        return f"число абзацев не совпало: {len(src_par)} -> {len(dst_par)}"

    for i, (a, b) in enumerate(zip(src_par, dst_par), start=1):
        a_text, b_text = "\n".join(a), "\n".join(b)
        if a_text.count("\t") != b_text.count("\t"):
            return f"табуляции не совпали в абзаце {i}"
        a_items = sum(1 for line in a if LIST_ITEM.match(line))
        b_items = sum(1 for line in b if LIST_ITEM.match(line))
        if a_items != b_items:
            return f"пункты списка не совпали в абзаце {i}: {a_items} -> {b_items}"
        if len(a_text) >= 80 and len(b_text) < len(a_text) * 0.6:
            return f"абзац {i} подозрительно короткий: {len(a_text)} -> {len(b_text)} символов"
        if len(a_text) >= 80 and len(b_text) > len(a_text) * 2:
            return f"абзац {i} подозрительно длинный: {len(a_text)} -> {len(b_text)} символов"
    return None