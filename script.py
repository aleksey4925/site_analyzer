import os
import shutil
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
import pandas as pd

# Используем заголовок 'User-Agent', чтобы имитировать запросы от браузера
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Функция для проверки валидности URL
def is_valid_url(url):
    parsed = urlparse(url)
    return bool(parsed.scheme) and bool(parsed.netloc)

# Функция для получения всех внутренних и внешних ссылок на странице
def get_links(url):
    print(f"Сканирование страницы: {url} ...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code != 200:
            print(f"Ошибка при сканировании страницы {url}, статус код: {response.status_code}")
            return set(), set()

        soup = BeautifulSoup(response.text, "html.parser")
        internal_links = set()
        external_links = set()

        for link in soup.find_all("a", href=True):
            href = urljoin(url, link["href"])
            parsed_href = urlparse(href)

            # Пропускать якорные ссылки (пример: href="#")
            if not parsed_href.scheme or not parsed_href.netloc:
                continue

            # Проверка, является ли ссылка внутренней
            if urlparse(url).netloc in parsed_href.netloc:
                internal_links.add(href.split("#")[0].rstrip("/"))
            else:
                external_links.add((url.split("#")[0].rstrip("/"), href))

        return internal_links, external_links
    except requests.RequestException as e:
        print(f"Ошибка при сканировании страницы {url}: {e}")
        return set(), set()


# Функция для проверки статуса ссылки(при статусе 301 возвращается так же ссылка для дальнейшего перенаправления)
def check_link(url):
    try:
        response = requests.head(url, headers=HEADERS, allow_redirects=False, timeout=5)
        if response.status_code == 301:
            return 301, response.headers.get("Location", None)
        else:
            return response.status_code, None
    except requests.RequestException as e:
        print(f"Ошибка при проверке ссылки {url}: {e}")
        return None, None


# Функция для сохранения данных в Excel файл
def save_to_excel(data, filename, columns):
    df = pd.DataFrame(data, columns=columns)
    df.to_excel(filename, index=False)


# Функция сортировки по страницам и добавления индексов к данным(начиная с первого и попорядку для хорошего отображения в таблицах)
def add_indexes(data):
    data = sorted(list(data), key=lambda pair: pair[0])
    return [(i + 1, *item) for i, item in enumerate(data)]


# Функция для обхода сайта и сбора нужной информации в зависимости от выбранного режима
def crawl_website(base_url, mode):
    visited = set()  # Множество посещенных ссылок
    to_visit = {base_url}  # Множество ссылок для посещения
    external_links = set()  # Множество внешних ссылок
    broken_links = (
        set()
    )  # Множество битых ссылок(как отличных от 200 и 301 статуса, так и неответивших в течение 5 секунд)
    redirected_links = set()  # Множество перенаправленных ссылок
    checked_external_links = (
        dict()
    )  # Словарь для проверенных внешних ссылок (запоминает статус коды, оптимизация)

    while to_visit:
        url = to_visit.pop()
        if url in visited:
            continue
        visited.add(url)

        internal_links, page_external_links = get_links(url)

        if mode == 1:
            external_links.update(page_external_links)
        else:
            for page, link in page_external_links:
                if link in checked_external_links:  # Проверка наличия ссылки в словаре
                    status_code, redirected_url = checked_external_links[link]
                else:
                    status_code, redirected_url = check_link(link)
                    checked_external_links[link] = (status_code, redirected_url)

                if status_code is None:
                    continue

                if mode == 2 and status_code not in [200, 301]:
                    broken_links.add((page, link))
                if mode == 3 and status_code == 301:
                    redirected_links.add((page, link, redirected_url))

        to_visit.update(internal_links - visited)

    if mode == 1:
        return add_indexes(external_links), ["№", "Страница", "Адрес ссылки"]
    elif mode == 2:
        return add_indexes(broken_links), ["№", "Страница", "Адрес ссылки"]
    elif mode == 3:
        return add_indexes(redirected_links), [
            "№",
            "Страница",
            "Адрес ссылки",
            "Перенаправлено на",
        ]


# Функция для настройки выходной папки (создание/удаление)
def setup_output_folder(folder_name):
    if os.path.exists(folder_name):
        shutil.rmtree(folder_name)
    os.makedirs(folder_name)


def main():
    folder_name = "output"
    setup_output_folder(folder_name)  # Настройка выходной папки

    website_url = input("Введите адрес сайта: ").split("#")[0].rstrip("/")
    
    while not is_valid_url(website_url):
        print("Неверный URL. Пожалуйста, введите корректный адрес сайта, формата: http://example.com")
        website_url = input("Введите адрес сайта: ").split("#")[0].rstrip("/")
    
    print("Выберите режим работы:")
    print("1: Только все внешние ссылки на всех внутренних страницах")
    print("2: Битые ссылки (отличные от 200 и 301)")
    print("3: Склеенные страницы (отдают 301)")
    mode = int(input("Введите номер режима: "))

    data, columns = crawl_website(
        website_url, mode
    )  # Сбор данных в зависимости от режима

    if mode == 1:
        file_path = os.path.join(
            folder_name, "external_links.xlsx"
        )  # Путь к файлу с внешними ссылками
        save_to_excel(data, file_path, columns)
        print(
            "Таблица с внешними ссылками сохранена в файл 'output/external_links.xlsx'"
        )
    elif mode == 2:
        file_path = os.path.join(
            folder_name, "broken_links.xlsx"
        )  # Путь к файлу с битыми ссылками
        save_to_excel(data, file_path, columns)
        print("Таблица с битыми ссылками сохранена в файл 'output/broken_links.xlsx'")
    elif mode == 3:
        file_path = os.path.join(
            folder_name, "redirected_links.xlsx"
        )  # Путь к файлу с перенаправленными ссылками
        save_to_excel(data, file_path, columns)
        print(
            "Таблица с склеенными ссылками сохранена в файл 'output/redirected_links.xlsx'"
        )


if __name__ == "__main__":
    main()
