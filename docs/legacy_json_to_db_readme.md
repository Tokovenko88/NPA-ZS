# NPA Importer

Программа для импорта НПА из JSON в базу данных MySQL (структура описана в `doc/Описание БД.md`).

## Требования
- Python 3.8+
- MySQL 5.7+ (или MariaDB)

## Установка
1. Клонируйте репозиторий
2. Создайте виртуальное окружение: `python -m venv venv`
3. Активируйте: `source venv/bin/activate` (Linux/Mac) или `venv\Scripts\activate` (Windows)
4. Установите зависимости: `pip install -r requirements.txt`
5. Скопируйте `.env.example` в `.env` и заполните параметры подключения к БД.

## Запуск
```bash
python src/main.py