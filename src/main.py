import logging
import re
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging
from constants import BASE_DIR, MAIN_DOC_URL, PEP_DOC_URL, EXPECTED_STATUS
from outputs import control_output
from utils import get_response, find_tag


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    response = get_response(session, whats_new_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    main_div = find_tag(soup, 'section', {'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div, 'div', {'class': 'toctree-wrapper'})
    sections_by_python = div_with_ul.find_all(
        'li',
        attrs={'class': 'toctree-l1'}
    )
    results = [('Ссылка на статью', 'Заголовок', 'Редактор, Автор')]
    for section in tqdm(sections_by_python):
        version_a_tag = find_tag(section, 'a')
        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)
        response = get_response(session, version_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, features='lxml')
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        results.append((version_link, h1.text, dl.text))
    return results


def latest_versions(session):
    request = get_response(session, MAIN_DOC_URL)
    if request is None:
        return
    soup = BeautifulSoup(request.text, 'lxml')
    sidebar = find_tag(soup, 'div', {'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')
    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
        else:
            raise Exception('Not found')
    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern=pattern, string=a_tag.text)
        if text_match is not None:
            version, status = text_match.group('version', 'status')
        else:
            version, status = a_tag.text, ''
        results.append((link, version, status))
    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    request = get_response(session, downloads_url)
    if request is None:
        return
    soup = BeautifulSoup(request.text, features='lxml')
    table = find_tag(soup, 'table', {'class': 'docutils'})
    pdf_a4_tag = find_tag(table, 'a', {'href': re.compile(r'.+pdf-a4\.zip$')})
    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)
    file_name = archive_url.split('/')[-1]
    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / file_name
    response = session.get(archive_url)
    with open(archive_path, 'wb') as download_file:
        download_file.write(response.content)
    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    response = get_response(session, PEP_DOC_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    section = find_tag(soup, 'section', attrs={'id': 'numerical-index'})
    table_pep = find_tag(section, 'tbody')
    rows_pep = table_pep.find_all('tr')
    status_counts = {}
    for row in tqdm(rows_pep, desc='Обработка строк'):
        stat_on_table = find_tag(row, 'td').text[1:]
        link = urljoin(PEP_DOC_URL, find_tag(row, 'a')['href'])
        response = get_response(session, link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, features='lxml')
        section = find_tag(soup, 'section', attrs={'id': 'pep-content'})
        table_info = find_tag(section, 'dl')
        status_header_tag = find_tag(table_info, 'dt', string='Status')
        status_on_page = status_header_tag.find_next_sibling().text
        if status_counts.get(status_on_page, 0) == 0:
            status_counts[status_on_page] = 1
        else:
            status_counts[status_on_page] += 1
        if status_on_page not in EXPECTED_STATUS[stat_on_table]:
            logging.info(
                (f'Несовпадение статуса:\n'
                 f'{link}\n'
                 f'Статус в карточке: {status_on_page}\n'
                 f'Ожидаемые статусы: {EXPECTED_STATUS[stat_on_table]}')
            )
    results = list(status_counts.items())
    results.insert(0, ('Статус', 'Количество'))
    total_amount = sum(status_counts.values())
    results.append(('Total', total_amount))
    return results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')
    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')
    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()
    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)
    if results is not None:
        control_output(results=results, cli_args=args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
