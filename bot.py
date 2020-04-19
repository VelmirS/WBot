# -*- coding: utf-8 -*-
import re
import requests
import telebot
import logging
import settings

from bs4 import BeautifulSoup as bs

bot = telebot.TeleBot(settings.API_KEY)

logging.basicConfig(format ='%(asctime)s - %(levelname)s - %(message)s',
	level = logging.INFO, filename = 'bot.log')

main_message = 'Привет. Это бот для поиска по Википедии или Лурку. Нажимай на кнопку и вводи свой поиск!'
ask_for_text = 'Напиши, что ты ищешь:'
unknown_command = 'Команда не распознана. Вернись назад или нажми /start'

# юрлы
search_wiki_url = 'https://ru.wikipedia.org/w/index.php?search={query}'
search_lurk_url = 'https://lurkmore.to/index.php?search={query}'
search_yandex_url = 'https://yandex.ru/search/?text={query}&lr=193'
advanced_search_wiki_url = 'https://ru.wikipedia.org/w/index.php?sort=relevance&search={query}&profile=advanced&fulltext=1&ns0=1'
api_wiki_url = 'https://ru.wikipedia.org/w/api.php?action=opensearch&format=json&formatversion=2&search={query}&namespace=0&limit=10'
api_wiki_url_2 = 'https://ru.wikipedia.org/api/rest_v1/page/summary/{query}'
api_lurk_url = 'https://lurkmore.to/api.php?action=opensearch&format=json&formatversion=2&search={query}&namespace=0&limit=10'
wiki_url_template = 'https://ru.wikipedia.org{link_part}'
wiki_message_template = '<b>{title}</b>\n<a href="{link}">{link_text}</a>\n{text}'

def check_search_system(key, system='wiki'):
	"""
	функция для проверки находит ли та или иная система (вики или лурк)
	хотя бы одну статью по данному запросу
	"""
	# смотрим, что за система и создаем ссылку для поиска
	url = search_wiki_url if system == 'wiki' else search_lurk_url
	url = url.format(query=re.sub(' +', '%20', key))

	# получаем страницу с результатами
	soup = bs(requests.get(url).content, 'lxml')

	# если на поисковой странице есть подсказка, то есть система считает,
	# что мы опечатались
	didyoumean = soup.find('div', {'class': 'searchdidyoumean'})
	if didyoumean:
		# ищем подсказку через апи
		apiurl = api_wiki_url if system == 'wiki' else api_lurk_url
		apiurl = apiurl.format(query=key)
		response = requests.get(apiurl).json()[1]

		# если подсказок нету - возвращаем False
		if len(response) == 0:
			return False, url
		return response[0], url

	else:
		# если на странице поиска есть блок, в котором сказано, что ничего не
		# найдено и нету подсказок - возвращаем False
		soup = soup.find('p', {'class': 'mw-search-nonefound'})
		if soup:
			return False, url
	return 'ok', url

def get_first_search_result_wiki(key):
	""" Получаем первый результат с страницы поиска """
	url = advanced_search_wiki_url.format(query=key)
	soup = bs(requests.get(url).content, 'lxml')
	first_result = soup.find('li', {'class': 'mw-search-result'})

	# получаем название статьи, ссылку на нее и блок с текстом
	a = first_result.find('a', href=True)
	article_url = wiki_url_template.format(link_part=a['href'])
	title = a.text
	text_alternative = first_result.find('div', {'class': 'searchresult'}).text

	text = requests.get(api_wiki_url_2.format(query=key)).json().get('extract')
	if not text:
		text = text_alternative

	# получаем картинку
	soup = bs(requests.get(article_url).content, 'lxml')
	image_block = soup.find('td', {'class': 'infobox-image'})

	# проверяем, есть ли изображение у статьи
	if image_block:
		image = 'https:' + image_block.find('img')['src']
		image = requests.get(image).content
	else:
		# если нету - image = False
		image = False

	text = wiki_message_template.format(title=title, link=article_url,
		link_text='ссылка', text=text)
	return text, image

def get_kb(*args, row_width=1, resize_keyboard=True):
	"""
	Функция для создания клавиатуры для бота
	Принимает на вход: список args - список кнопок, row_width - высота одной
	линии и resize_keyboard - будет ли телеграм изменять размер клавиатуры под
	оптимальный
	Возвращает объект telebot.types.ReplyKeyboardMarkup - клавиатуру
	"""
	kb = telebot.types.ReplyKeyboardMarkup(
		row_width=row_width,
		resize_keyboard=resize_keyboard)

	for argument in args:
		kb.add(argument)
	return kb


@bot.message_handler(commands=['start'])
def start(message_object):
	""" обрабатываем команду /start """
	kb = get_kb('Википедия', 'Лурк')
	msg = bot.send_message(message_object.chat.id, main_message, reply_markup=kb)
	bot.register_next_step_handler(msg, choose_search_system)

def choose_search_system(message_object):
	""" выбираем поисковую систему """
	if message_object.text in ['Википедия', 'Лурк']:
		kb = get_kb('Назад')
		msg = bot.send_message(message_object.chat.id, ask_for_text, reply_markup=kb)

		if message_object.text == 'Яндекс':
			bot.register_next_step_handler(msg, search_yandex)
		elif message_object.text == 'Лурк':
			bot.register_next_step_handler(msg, search_lurk)
		else:
			bot.register_next_step_handler(msg, search_wiki)

	elif 'Назад' in message_object.text:
		start(message_object)

	else:
		msg = bot.send_message(message_object.chat.id, unknown_command)
		bot.register_next_step_handler(msg, start)


def search_in(message_object):
	search = {
		'яндекс': search_yandex,
		'википедия': search_wiki,
		'лурк': search_lurk
	}

	for key in search.keys():
		if key in message_object.text.lower():
			search[key](message_object)
	else:
		start(message_object)

def search_wiki(message_object):
	""" функция для поиска на википедии """
	text = message_object.text.split('«')[-1].split('»')[0]

	if text == 'Назад':
		start(message_object)
	else:
		searchdidyoumean, url = check_search_system(text)

		if searchdidyoumean == 'ok':
			kb = get_kb('Назад')

			text, image = get_first_search_result_wiki(text)
			msg = bot.send_message(message_object.chat.id, text, reply_markup=kb,
				parse_mode='html', disable_web_page_preview=True)

			if image:
				bot.send_photo(message_object.chat.id, image)

			bot.register_next_step_handler(msg, choose_search_system)

		elif not searchdidyoumean:
			kb = get_kb(
				'Искать в яндексе «{query}»'.format(query=text[:10]),
				'Искать в лурке «{query}»'.format(query=text[:10]),
				'Назад')

			msg = bot.send_message(message_object.chat.id, 'Ничего не найдено', reply_markup=kb)
			bot.register_next_step_handler(msg, search_in)

		else:
			kb = get_kb(
				'Искать в википедии «{text}»'.format(text=searchdidyoumean[:10]),
				'Искать в яндексе «{text}»'.format(text=text[:10]),
				'Искать в лурке «{text}»'.format(text=text[:10]),
				'Назад')

			message = 'Возможно, вы имели в виду «{text}».'.format(text=searchdidyoumean)
			msg = bot.send_message(message_object.chat.id, message, reply_markup=kb)
			bot.register_next_step_handler(msg, search_in)

def search_yandex(message_object):
	""" функция для поиска на яндексе """
	text = message_object.text.split('«')[-1].split('»')[0]

	if text == 'Назад':
		start(message_object)
	else:
		kb = get_kb('Назад')
		url = search_yandex_url.format(query=re.sub(' +', '%20', text))
		msg = bot.send_message(message_object.chat.id, url, reply_markup=kb)
		bot.register_next_step_handler(msg, choose_search_system)

def search_lurk(message_object):
	""" функция для поиска на лурке """
	text = message_object.text.split('«')[-1].split('»')[0]

	if text == 'Назад':
		start(message_object)
	else:
		searchdidyoumean, url = check_search_system(text, system='lurk')

		if searchdidyoumean == 'ok':
			kb = get_kb('Назад')
			msg = bot.send_message(message_object.chat.id, url, reply_markup=kb)
			bot.register_next_step_handler(msg, choose_search_system)

		elif not searchdidyoumean:
			kb = get_kb(
				'Искать в яндексе «{text}»'.format(text=text[:10]),
				'Искать в википедии «{text}»'.format(text=text[:10]),
				'Назад')

			msg = bot.send_message(message_object.chat.id, 'Ничего не найдено', reply_markup=kb)
			bot.register_next_step_handler(msg, search_in)

		else:
			kb = get_kb(
				'Искать в википедии «{text}»'.format(text=searchdidyoumean[:10]),
				'Искать в яндексе «{text}»'.format(text=text[:10]),
				'Искать в лурке «{text}»'.format(text=text[:10]),
				'Назад')

			message = 'Возможно, вы имели в виду «{text}».'.format(searchdidyoumean)
			msg = bot.send_message(message_object.chat.id, message, reply_markup=kb)
			bot.register_next_step_handler(msg, search_in)

if __name__ == '__main__':
	bot.polling()
