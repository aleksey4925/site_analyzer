import os
from urllib.parse import urlparse, urljoin
import msvcrt
import datetime

import requests
from bs4 import BeautifulSoup
import pandas as pd

# Используем заголовок 'User-Agent', чтобы имитировать запросы от браузера
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Глобальный список для хранения ошибок
errors = []


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
            errors.append(
                f"Ошибка при сканировании страницы {url}, статус код: {response.status_code}"
            )
            return set(), set()

        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            errors.append(f"Страница {url} не является HTML-документом (Content-Type: {content_type})")
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
        errors.append(f"Ошибка при сканировании страницы {url}: {e}")
        return set(), set()


# Функция для проверки статуса ссылки(при статусе 301 возвращается так же ссылка для дальнейшего перенаправления)
def check_link(url):
    try:
        print(f'\tПереход по ссылке: {url} ...')
        # Получаем изначальный статус код и новый URL после первого редиректа
        response = requests.get(url, headers=HEADERS, allow_redirects=False, timeout=5)
        initial_status_code = response.status_code
        if initial_status_code == 301:
            # Теперь определяем конечный URL после всех перенаправлений
            response = requests.get(url, headers=HEADERS, allow_redirects=True)
            final_url = response.url
            return initial_status_code, final_url
        else:
            return initial_status_code, None
    except requests.RequestException as e:
        errors.append(f"Ошибка при проверке ссылки {url}: {e}")
        return None, None


# Функция для сохранения данных в Excel файл
def save_to_excel(data, output_folder_name, url_folder_name, mode_folder_name, columns):
    try:
        setup_folder(output_folder_name)
        setup_folder(os.path.join(output_folder_name, url_folder_name))
        setup_folder(os.path.join(output_folder_name, url_folder_name, mode_folder_name))
        # Генерируем имя файла в формате ГГГГ-ММ-ДД-время.xlsx
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        filename = f"{timestamp}.xlsx"
        filename_path = os.path.join(output_folder_name, url_folder_name, mode_folder_name, filename)

        if os.path.exists(filename_path):
            print(f"\n\tФайл '{filename_path}' уже существует. Запись отклонена.")
            return False
        else:
            df = pd.DataFrame(data, columns=columns)
            df.to_excel(filename_path, index=False)
            print(f"\n\tФайл '{filename}' успешно сохранен. Найдено {len(data)} ссылок.")
            return True
    except Exception as e:
        print(f"\n\tОшибка при сохранении файла '{filename_path}': {e}")
        return False

# Функция удаления дубликатов страниц
def remove_duplicates(data):
    no_protocols_page_data = set()
    for pair in data:
        page_link = pair[0]
        no_protocol_page_link = urlparse(page_link).netloc + urlparse(page_link).path
        no_protocols_page_data.add((no_protocol_page_link, *pair[1:]))
    return no_protocols_page_data

# Функция сортировки по страницам
def sort_links(data):
    return sorted(list(data), key=lambda pair: pair[0])

# Функция для добавления индексов к данным
def add_indexes(data):
    return [(i + 1, *item) for i, item in enumerate(data)]


# Функция для обхода сайта и сбора нужной информации в зависимости от выбранного режима
def crawl_website(base_url, mode):
    visited = set()  # Множество посещенных ссылок
    to_visit = {base_url}  # Множество ссылок для посещения
    external_links = set()  # Множество внешних ссылок
    broken_links = set() # Множество битых ссылок(как отличных от 200 и 301 статуса, так и неответивших в течение 5 секунд)
    redirected_links = set()  # Множество перенаправленных ссылок
    checked_external_links = dict() # Словарь для проверенных внешних ссылок (запоминает статус коды, оптимизация)

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
        return add_indexes(sort_links(remove_duplicates(external_links))), ["№", "Страница", "Адрес ссылки"]
    elif mode == 2:
        return add_indexes(sort_links(remove_duplicates(broken_links))), ["№", "Страница", "Адрес ссылки"]
    elif mode == 3:
        return add_indexes(sort_links(remove_duplicates(redirected_links))), ["№", "Страница", "Адрес ссылки", "Конечное перенаправление"]


# Функция для настройки выходной папки (создание/удаление)
def setup_folder(folder_name):
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)


def main():
    program_name = "АНАЛИЗАТОР САЙТА"
    output_folder_name = "output"

    while True:
        print(f"\n{"="*len(program_name)}\n{program_name}\n{"="*len(program_name)}")
        print("\n\tПожалуйста, введите адрес сайта, формата: http://example.com")
        website_url = input("\nВведите адрес сайта: ").split("#")[0].rstrip("/")

        while not is_valid_url(website_url):
            print(
                "\n\tНеверный URL. Пожалуйста, введите корректный адрес сайта, формата: http://example.com"
            )
            website_url = input("\nВведите адрес сайта: ").split("#")[0].rstrip("/")

        url_folder_name = website_url.split("//")[-1].replace("/", "-")

        print("\nВыберите режим работы:")
        print("\t1: Только все внешние ссылки на всех внутренних страницах")
        print("\t2: Битые ссылки (отличные от 200 и 301)")
        print("\t3: Склеенные страницы (отдают 301)")
        mode = int(input("Введите номер режима: "))

        while mode not in [1, 2, 3]:
            print("\nНеверный режим. Пожалуйста, выберите правильный режим работы:")
            print("\t1: Только все внешние ссылки на всех внутренних страницах")
            print("\t2: Битые ссылки (отличные от 200 и 301)")
            print("\t3: Склеенные страницы (отдают 301)")
            mode = int(input("Введите номер режима: "))
        print()
        
        data, columns = crawl_website(
            website_url, mode
        )  # Сбор данных в зависимости от режима

        # Вывод ошибок, если они есть
        if errors:
            print("\nОшибки, возникшие во время выполнения:")
            for error in errors:
                print(f'\t{error}')
            print()

        if len(data) == 0:
            print("\n\tНе найдено ни одной ссылки. Файл не будет сгенерирован.")
        else:
            if mode == 1:
                external_links_folder_name = "external_links"
                if save_to_excel(data, output_folder_name, url_folder_name, external_links_folder_name, columns):
                    print(f"\tТаблица с внешними ссылками сохранена в папку '{os.path.join(output_folder_name, url_folder_name, external_links_folder_name)}'")               
            elif mode == 2:
                broken_links_folder_name = "broken_links"
                if save_to_excel(data, output_folder_name, url_folder_name, broken_links_folder_name, columns):
                    print(f"\tТаблица с битыми ссылками сохранена в папку '{os.path.join(output_folder_name, url_folder_name, broken_links_folder_name)}'")
            elif mode == 3:
                redirected_links_folder_name = "redirected_links"
                if save_to_excel(data, output_folder_name, url_folder_name, redirected_links_folder_name, columns):
                    print(f"\tТаблица с перенаправленными ссылками сохранена в папку '{os.path.join(output_folder_name, url_folder_name, redirected_links_folder_name)}'")

        print("\nНажмите 'Enter', чтобы сканировать другой сайт или 'Esc' для выхода.")

        # Ожидание ввода пользователя
        while True:
            key = msvcrt.getch()
            if key == b'\x1b':  # ESC
                return
            elif key == b'\r':  # Enter
                break
            else:
                print("\nНажмите 'Enter', чтобы сканировать другой сайт или 'Esc' для выхода:")


if __name__ == "__main__":
    main()
