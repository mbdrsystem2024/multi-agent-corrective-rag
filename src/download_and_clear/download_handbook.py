"""Скачивает раздел GitLab Handbook в виде текстовых файлов (на английском).

Пример:
    python download_handbook.py https://handbook.gitlab.com/handbook/people-policies/

Скрипт берёт ссылку на страницу сайта handbook.gitlab.com, находит
соответствующие файлы в репозитории gitlab-com/content-sites/handbook
и скачивает эту страницу вместе со всеми подстраницами, сохраняя структуру папок.
По умолчанию разметка Markdown вычищается и сохраняются .txt (см. clean_markdown.py),
с флагом --raw сохраняются исходные .md.
Рядом кладётся manifest.csv: какой файл какой странице сайта соответствует.
"""

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from clean_markdown import clean_markdown

SITE_HOST = "handbook.gitlab.com"
PROJECT = "gitlab-com/content-sites/handbook"
API = f"https://gitlab.com/api/v4/projects/{quote(PROJECT, safe='')}/repository"
RAW = f"https://gitlab.com/{PROJECT}/-/raw"
CONTENT_DIR = "content"
USER_AGENT = "handbook-downloader (student project)"
MAX_RETRIES = 5


def http_get(url, token=None, method="GET"):
    """GET-запрос с повторами при 429 (лимит запросов) и 5xx. Возвращает (тело, заголовки, итоговый url)."""
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["PRIVATE-TOKEN"] = token
    for attempt in range(MAX_RETRIES):
        try:
            with urlopen(Request(url, headers=headers, method=method), timeout=60) as resp:
                return resp.read(), resp.headers, resp.geturl()
        except HTTPError as e:
            if e.code == 429 or e.code >= 500:
                wait = int(e.headers.get("Retry-After") or 2 ** attempt)
                print(f"  ! {e.code}, жду {wait} с и повторяю...", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Не удалось скачать {url} после {MAX_RETRIES} попыток")


def url_to_page_path(url):
    """https://handbook.gitlab.com/handbook/values/#anchor -> 'handbook/values'.

    Сначала идём по ссылке, чтобы учесть редиректы сайта
    (например, /job-families/ -> /job-description-library/).
    """
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.netloc != SITE_HOST:
        sys.exit(f"Ожидается ссылка на {SITE_HOST}, а получено: {parsed.netloc}")
    try:
        _, _, final_url = http_get(f"https://{SITE_HOST}{parsed.path}", method="HEAD")
        parsed = urlparse(final_url)
    except HTTPError as e:
        print(f"  ! Сайт ответил {e.code} на эту ссылку, пробую как есть", file=sys.stderr)
    return parsed.path.strip("/")


def list_tree(repo_path, ref, token):
    """Рекурсивный список файлов в папке репозитория (с учётом постраничной выдачи API)."""
    files, page = [], "1"
    while page:
        url = (f"{API}/tree?path={quote(repo_path)}&ref={quote(ref)}"
               f"&recursive=true&per_page=100&page={page}")
        try:
            body, headers, _ = http_get(url, token)
        except HTTPError as e:
            if e.code == 404:
                return []
            raise
        files += [item["path"] for item in json.loads(body) if item["type"] == "blob"]
        page = headers.get("X-Next-Page")
    return files


def file_exists(repo_path, ref, token):
    url = f"{API}/files/{quote(repo_path, safe='')}?ref={quote(ref)}"
    try:
        http_get(url, token, method="HEAD")
        return True
    except HTTPError as e:
        if e.code == 404:
            return False
        raise


def find_md_files(page_path, ref, token):
    """Находит .md файлы для страницы: либо целая папка-раздел, либо одна страница."""
    base = f"{CONTENT_DIR}/{page_path}".rstrip("/")
    md_files = [p for p in list_tree(base, ref, token) if p.endswith(".md")]
    if md_files:
        return sorted(md_files)
    # Не папка — значит, отдельная страница (Hugo: name.md или name/index.md)
    for candidate in (f"{base}.md", f"{base}/index.md"):
        if file_exists(candidate, ref, token):
            return [candidate]
    return []


def repo_path_to_site_url(repo_path):
    """content/handbook/a/b/_index.md или content/handbook/a/b.md -> https://handbook.gitlab.com/handbook/a/b/"""
    rel = repo_path[len(CONTENT_DIR) + 1:-len(".md")]
    for suffix in ("/_index", "/index"):
        if rel.endswith(suffix):
            rel = rel[: -len(suffix)]
    return f"https://{SITE_HOST}/{rel}/"


def download_one(repo_path, out_dir, ref, token, raw):
    body, _, _ = http_get(f"{RAW}/{quote(ref)}/{quote(repo_path)}", token)
    target = out_dir / repo_path[len(CONTENT_DIR) + 1:]
    target.parent.mkdir(parents=True, exist_ok=True)
    if raw:
        target.write_bytes(body)
    else:
        target = target.with_suffix(".txt")
        target.write_text(clean_markdown(body.decode("utf-8")), encoding="utf-8")
    return target


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Скачать раздел GitLab Handbook в виде .md файлов")
    parser.add_argument("url", help="ссылка на страницу или раздел handbook.gitlab.com")
    parser.add_argument("-o", "--output", default="downloads", help="папка для результата (по умолчанию downloads)")
    parser.add_argument("--ref", default="main", help="ветка или коммит репозитория (по умолчанию main)")
    parser.add_argument("--limit", type=int, help="скачать не больше N файлов (для пробы)")
    parser.add_argument("--workers", type=int, default=8, help="число параллельных загрузок (по умолчанию 8)")
    parser.add_argument("--raw", action="store_true", help="сохранить исходные .md без очистки от разметки")
    args = parser.parse_args()

    token = os.environ.get("GITLAB_TOKEN")  # необязателен, лишь поднимает лимит запросов
    out_dir = Path(args.output)

    page_path = url_to_page_path(args.url)
    print(f"Раздел: /{page_path}/")
    md_files = find_md_files(page_path, args.ref, token)
    if not md_files:
        sys.exit(f"Не нашёл файлов для /{page_path}/ в репозитории {PROJECT}. Проверьте ссылку.")
    if args.limit:
        md_files = md_files[: args.limit]
    print(f"Найдено файлов: {len(md_files)}. Скачиваю в {out_dir.resolve()}")

    rows, failed = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_one, p, out_dir, args.ref, token, args.raw): p for p in md_files}
        for i, future in enumerate(as_completed(futures), 1):
            repo_path = futures[future]
            try:
                target = future.result()
            except Exception as e:
                failed.append(repo_path)
                print(f"  [{i}/{len(md_files)}] ОШИБКА {repo_path}: {e}", file=sys.stderr)
                continue
            rows.append({
                "file": target.relative_to(out_dir).as_posix(),
                "page_url": repo_path_to_site_url(repo_path),
                "source_url": f"https://gitlab.com/{PROJECT}/-/blob/{args.ref}/{repo_path}",
            })
            print(f"  [{i}/{len(md_files)}] {repo_path}")

    write_manifest(out_dir / "manifest.csv", rows)
    print(f"Готово: {len(rows)} файлов, ошибок: {len(failed)}. Список файлов: {out_dir / 'manifest.csv'}")
    if failed:
        sys.exit(1)


def write_manifest(path, rows):
    """Дописывает в manifest.csv новые строки, не дублируя уже скачанные файлы."""
    existing = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            existing = {row["file"]: row for row in csv.DictReader(f)}
    existing.update({row["file"]: row for row in rows})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "page_url", "source_url"])
        writer.writeheader()
        writer.writerows(sorted(existing.values(), key=lambda r: r["file"]))


if __name__ == "__main__":
    main()
