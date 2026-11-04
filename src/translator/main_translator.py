from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from dotenv import load_dotenv
import os
from pathlib import Path
from datetime import datetime

from loader import DataReader
from translate_checks import check_translation

MAX_ATTEMPTS = 3 # количество попыток на неудачном переводе


#указывайте относительный путь
ROOT = Path(__file__).resolve().parent.parent.parent
csv_path = ROOT / "data" / "raw" / "manifest.csv"
save_path = ROOT / "data" / "translated_raw"
promt_path = ROOT / "prompts" / "translator_llm_prompt" / "prompt.txt"




def main():
    with open(promt_path, encoding="utf-8") as file:
        promt_text = file.read()

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         promt_text),
        ("human", "{text}"),
    ])


    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    model = ChatGoogleGenerativeAI(model='gemini-3.1-flash-lite', api_key = api_key, max_retries=6)
    chain = prompt | model | StrOutputParser()



    data_loader = DataReader(csv_path, save_path)



    print("основной цикл пошел")
    try:
        while True:
            try:
                item = data_loader.load_next()
            except Exception as e:
                print(f"не удалось прочитать файл: {e}")
                continue

            if item is None:
                break
            path, text = item
            try:
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    result = chain.invoke({
                        "source": "английского",
                        "target": "русский",
                        "text": text,
                    })
                    problem = check_translation(text, result)
                    if problem is None:
                        break
                    print(f"{path}: попытка {attempt}: {problem}")

                if problem:
                    print(f"{path}: {problem}")
                    rejected = Path(save_path) / "_rejected" / path.relative_to(data_loader.base_path)
                    rejected.parent.mkdir(parents=True, exist_ok=True)
                    rejected.write_text(result, encoding="utf-8")
                    continue

                data_loader.save(path, result)
                print(f"время: {datetime.now()} сохранено {path}")
            except Exception as e:
                print(f"ошибка на {path}, возможно ошибка API: {e}")

    finally:
        data_loader.export_not_processed()

if __name__ == "__main__":
    main()