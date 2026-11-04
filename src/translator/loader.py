import pandas as pd
from pathlib import Path


class DataReader:
    def __init__(self, csv_path, save_path):
        # на вход csv_path - файл с путями, целевая папка должна находиться в том же месте
        self.save_path = save_path
        df = pd.read_csv(csv_path, dtype=str)
        names = df["file"].dropna().tolist()
        self.is_processed = {}
        self.base_path = Path(csv_path).parent

        for i in names:
            self.is_processed[self.base_path/i] = 0

        self.iterator = self.dict_iterator(self.is_processed)

    def dict_iterator(self, dictionary):
        '''итератор по словарю'''
        for key, value in dictionary.items():
            yield key, value

    def export_not_processed(self):
        '''записываем имена тех файлов которые не обработали'''
        not_processed = []
        for i in self.is_processed:
            if  self.is_processed[i] == 0:
                not_processed.append(i.relative_to(self.base_path))
        df = pd.DataFrame({
            "file": not_processed,
        })
        df.to_csv( Path(self.base_path) / "not_processed.csv", index=False, encoding="utf-8-sig")

    def load_next(self):
        '''
        загружаем и возвращаем следующий файл
        :return path, text
        возвращает путь к файлу и его содержимое
        '''
        item = next(self.iterator, None)
        if item is None:
            return None
        path, _ = item
        with open(path, encoding="utf-8") as file:
            return path, file.read()

    def mark_as_processed(self, path):
        '''отмечаем обработанным значение'''
        self.is_processed[path] = 1

    def save(self, path, text):
        '''сохраняем переведенный файл'''
        out_path = Path(self.save_path) / path.relative_to(self.base_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")

        self.mark_as_processed(path)
