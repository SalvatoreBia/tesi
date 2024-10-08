import logging
import asyncio
import os
import threading
import uuid
import re
import queue
import matplotlib.pyplot as plt
from datetime import datetime
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InlineQueryResultArticle, InputTextMessageContent
)
from telegram.ext import (
    ContextTypes, ApplicationBuilder, CommandHandler, MessageHandler,
    filters, CallbackContext, CallbackQueryHandler, InlineQueryHandler
)
from src.datamanagement.database import DbManager as db
from src.utils import text, mythreads, research, img3d

# _____________________________LOGGING________________________________________

report_logger = logging.getLogger('report_logger')
report_logger.setLevel(logging.INFO)

log_handler = RotatingFileHandler(
    'logs/bot.log',
    maxBytes=5*1024*1024,
    backupCount=3
)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(formatter)
report_logger.addHandler(log_handler)
logging.basicConfig(level=logging.INFO)

# _____________________________VARIABLES______________________________________

MIN_YEAR = 1900

TOKEN_PATH = 'resources/config/token.txt'
FIELDS_PATH = 'resources/config/fields.txt'
SUB_PATH = 'resources/data/subscribers.txt'
DEF_PATH = 'resources/config/definitions.txt'
INFO_PATH = 'resources/config/commands_info.txt'
IMG_DIR = 'resources/img/'
search_data = {}
SEARCH_LIMIT = 25
fields_ = {}
definitions = {}
comm_infos = {}
plot_supported = {
    'emass': 'pl_bmasse',
    'jmass': 'pl_bmassj',
    'erad': 'pl_rade',
    'jrad': 'pl_radj',
    'sgrav': 'st_logg',
    'srad': 'st_rad',
    'smass': 'st_mass'
}

htmlLock = asyncio.Lock()
pngLock = asyncio.Lock()
subLock = threading.RLock()
newsLock = threading.RLock()
state_lock = threading.RLock()
updater_ids_lock = threading.RLock()
executor = ThreadPoolExecutor(max_workers=10)
updater = mythreads.ArchiveUpdater()

MAX_SUBPROCESSES = 5
subprocess_queue = queue.Queue(maxsize=MAX_SUBPROCESSES)

# _____________________________FUNCTIONS______________________________________

def reset_search(id):
    search_data[id] = {
        'start': 0,
        'end': SEARCH_LIMIT,
        'last': None,
        'searched': None
    }


def read_subs():
    with subLock:
        try:
            with open(SUB_PATH, 'r') as file:
                return file.readlines()
        except IOError as e:
            print(f'Error reading subscription file: {e}')
            return None


def write_subs(subs: list):
    with subLock:
        try:
            with open(SUB_PATH, 'w') as file:
                file.writelines(subs)
                return True
        except IOError as e:
            print(f'Error reading subscription file: {e}')
            return False


def current_state() -> bool:
    with state_lock:
        return updater.is_sleeping()


async def register_user(chat_id):
    if chat_id not in search_data:
        reset_search(chat_id)
        await asyncio.get_event_loop().run_in_executor(executor, updater.add_id, chat_id)


async def send(update: Update, context: ContextTypes.DEFAULT_TYPE, msg: str, parsing: bool) -> None:
    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=msg,
        parse_mode='Markdown' if parsing else None
    )

async def send_internal_server_error_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text="*Oops!* Something went wrong on our end. We'll work to fix it. Please try again later.",
        parse_mode='Markdown'
    )

async def notify_user_if_updating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    sleeping = await asyncio.get_event_loop().run_in_executor(executor, current_state)
    if not sleeping:
        msg = 'We\'re currently updating the database, all commands are unavailable. We\'ll be back in a moment.'
        await send(update, context, msg, False)
        return True
    return False

# ____________________________ACTUAL COMMANDS_________________________________

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    msg = (
        '🌌 *Welcome to LEXArchive!* 🚀\n\n'
        f'Hello, *{update.effective_chat.effective_name}*. '
        'Right here you can easily navigate the NASA Exoplanet Archive *Planetary Systems* and *Planetary Systems Composite Data*'
        ' tables , and I am here to provide easy access to them with my functionalities. '
        '\n\nTo get started, you can use /help to look up the available commands. Running "/info info" command'
        ' is also recommended to gain better understading on how to know more details about other commands.\n\n'
        'If you\'re new and you don\'t know what kind of data is being managed, you can use /fields to display all of the '
        'info each record has, also you can make an inline query about these fields if you don\'t know what do they mean.'
        '\n\nIf you experience any problems using the bot, please let us know using /report command.'
    )
    await send(update, context, msg, True)


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    msg = (
        "General Commands:\n"
        "/info <command_name(s)> - Get details about one or more commands and how to use them\n"
        "/report <message> - Submit a message to report any problem using the bot\n\n"
        "LEXArchive Commands:\n"
        "/count - Count total records in the database\n"
        "/pcount - Count total discovered exoplanets\n"
        "/discin <year> - Count exoplanets discovered in a specific year\n"
        "/search <keyword> - Search for exoplanets by keyword\n"
        "/table <planet_name> - Get detailed table of a specific planet\n"
        "/plot <field> - Plot distribution of a specific field\n"
        "/fields - List all available fields\n"
        "/cst <name> - Get constellation of where a celestial body resides"
        "/locate <planet_name> - Get photo pointing where the planet is located\n"
        "/show <name> <option> - Get 3D image representing a celestial body\n"
        "/random - Test your luck\n"
        "/near - Get the nearest planets to earth\n"
        "/far - Get the farthest planets to earth\n"
        "/hab <planet_name> <option> - Get an habitability index of a specific planet.\n"
        "/habzone <star_name> - Get infos about a star\'s habitable zone\n"
        "/sub <HH:MM> - Subscribe for daily updates at a specific time (UTC)\n"
        "/unsub - Unsubscribe from daily updates\n"
    )
    await send(update, context, msg, False)


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if len(context.args) == 0:
        await send(update, context, '*Invalid Syntax*: You need to search for one or more commands.', True)

    for comm in context.args:
        if comm in comm_infos:
            await send(update, context, f'*{comm}*' + '\n\n' + comm_infos[comm], True)
        else:
            await send(update, context, f'*Error*: Command \'{comm}\' not found. Check if the name is correct, if so, it means that there are no more infos about it.', True)


# count how many planets were discovered
async def count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) != 0:
        await send(update, context, '*Invalid Syntax:* this command doesn\'t need arguments to run.', True)
        return

    is_total_count = True if update.message.text == '/count' else False
    if is_total_count:
        rows = db.count('ps')
    else:
        rows = db.count('pscomppars')

    if rows is None:
        await send_internal_server_error_message(update, context)
        return
    elif rows != -1:
        msg = f'The archive counts *{rows}* different exoplanets discovered.' if not is_total_count else f'The archive counts *{rows}* records.'
        await send(update, context, msg, True)


# count how many planets were discovered in a certain year
async def disc_in(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) != 1:
        await send(update, context, '*Invalid Syntax:* You need to specify a year.', True)
        return

    try:
        year = int(context.args[0])
        curr_year = datetime.now().year
        if year < MIN_YEAR or year > curr_year:
            await send(update, context, f'*Value Error:* You should insert a year between _{MIN_YEAR}_ and _{curr_year}_.', True)
            return
    except ValueError:
        await send(update, context, '*Invalid Syntax:* You need to specify a valid year.', True)
        return

    rows = db.disc_in(year)
    if rows is None:
        await send_internal_server_error_message(update, context)
        return
    elif rows != -1:
        msg = f'The archive counts *{rows}* different exoplanets discovered in {year}.'
        await send(update, context, msg, True)


# returns a list of planet with buttons to iterate it
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    keyword = None if len(context.args) == 0 else (''.join(context.args)).lower()
    chat = update.effective_user.id
    if chat in search_data and search_data[chat]['last'] is not None:
        await context.bot.delete_message(
            chat_id=chat,
            message_id=search_data[chat]['last']
        )
    reset_search(chat)

    st, end = search_data[chat]['start'], search_data[chat]['end']
    rows = db.search_pl(st, end, keyword)
    if rows is None:
        await send_internal_server_error_message(update, context)
        return
    elif not rows:
        await send(update, context, 'No planet has been found.', False)
        return

    string = ''
    index = st + 1
    for row in rows:
        string += f'{index}.   {row}\n'
        index += 1

    keyboard = [
        [
            InlineKeyboardButton("< Previous Page", callback_data='prev_page_btn'),
            InlineKeyboardButton("Next Page >", callback_data='next_page_btn')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = await context.bot.send_message(
        chat_id=chat,
        text='Available Planets:\n\n' + string,
        reply_markup=reply_markup
    )
    search_data[chat]['last'] = message.message_id
    search_data[chat]['searched'] = keyword


# button listener for the search command
async def button_listener(update: Update, context: CallbackContext) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    query = update.callback_query

    chat = query.message.chat.id
    keyword = search_data[chat]['searched']
    st, end = search_data[chat]['start'], search_data[chat]['end']
    rows = db.count_like(keyword)

    if query.data == 'next_page_btn' and end < rows:
        st, end = st + SEARCH_LIMIT, min(end + SEARCH_LIMIT, rows)
    elif query.data == 'prev_page_btn' and st > 0:
        st, end = st - SEARCH_LIMIT, st
    else:
        return

    search_data[chat]['start'] = st
    search_data[chat]['end'] = end

    rows = db.search_pl(st, end, keyword)

    string = ''
    index = st + 1
    for row in rows:
        string += f'{index}.   {row}\n'
        index += 1

    await query.answer()
    await query.message.edit_text(
        text='Available Planets\n\n' + string,
        reply_markup=query.message.reply_markup
    )


# returns an html table retrieving some records of a specific planet
async def table(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) == 0:
        await send(update, context, '*Invalid Syntax:* You need to specify at least one search string.', True)
        return

    keyword = ''.join(context.args).lower()
    rows, exceeds = db.get_pl_by_name(keyword)

    if rows is None:
        await send_internal_server_error_message(update, context)
        return
    elif not rows:
        await send(update, context, 'No record has been found.', False)
        return

    for i in range(len(rows)):
        rows[i] = rows[i][1:-1]

    string = text.htable_format([fields_[key] for key in fields_], rows, exceeds)
    filename = f'table-{keyword}.html'
    async with htmlLock:
        with open(filename, 'w') as file:
            file.write(string)

        await context.bot.send_document(
            chat_id=update.effective_user.id,
            document=filename
        )
        os.remove(filename)


# plot how a field is distributed
async def plot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) != 1:
        await send(update, context, '*Invalid Syntax:* you need to specify a criteria.', True)
        return

    criteria = context.args[0]
    if criteria not in plot_supported:
        await send(update, context, '*Value Error:* you need to specify a supported criteria (use /info plot to check them).', True)
        return

    values = sorted(db.get_field_values(plot_supported[criteria]))
    if values is None:
        await send_internal_server_error_message(update, context)
        return
    elif not values:
        await send(update, context, 'There\'s not enough data to plot.', False)
        return

    async with pngLock:
        file = 'plot.png'
        plt.plot(values)
        plt.ylabel(criteria)
        plt.savefig(file)
        plt.close()

        await context.bot.send_photo(
            chat_id=update.effective_user.id,
            photo=open(file, 'rb')
        )

        os.remove(file)


# returns the list of fields
async def fields(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    string = ''
    for key in fields_:
        temp = fields_[key] if fields_[key][-1] != '~' else fields_[key][:-1]
        string += f'_{temp}_\n'

    await send(update, context, string, True)


async def locate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) == 0:
        await send(update, context, '*Invalid Syntax:* you need to specify a planet name.', True)
        return

    planet = ''.join(context.args).lower()
    coord = db.get_coordinates(planet)
    constellation_ = db.get_constellation_by_celestial_body_name(planet)
    if coord is None:
        await send(update, context, 'No planet has been found.', False)
        return
    elif coord == -1 or constellation_ == -1:
        await send_internal_server_error_message(update, context)
        return
    else:
        rastr, decstr = coord
        if rastr is None or decstr is None or constellation_ is None:
            await send(update, context, 'There\'s not enough data to locate it.', False)
            return

    buffer = await research.fetch_sky_image(coord, constellation_[0])
    buffer.seek(0)
    await context.bot.send_photo(
        chat_id=update.effective_user.id,
        photo=buffer.read(),
        caption=f'*Right ascension:* {rastr}, *Declination:* {decstr}',
        parse_mode='Markdown'
    )


async def constellation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) == 0:
        await send(update, context, '*Invalid Syntax:* you need to specify a celestial body name.', True)
        return

    name = ''.join(context.args).lower()
    cst = db.get_constellation_by_celestial_body_name(name)
    if cst == -1:
        await send_internal_server_error_message(update, context)
        return
    elif cst is None:
        await send(update, context, 'Celestial body not found.', False)
        return
    elif cst[0] is None:
        await send(update, context, f'Celestial body was found, but currently unable to locate it.', False)
        return

    await send(update, context, f'The celestial body is located in *{cst[0]}* Constellation.', True)


async def rand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) != 0:
        await send(update, context, '*Invalid Syntax:* this command doesn\'t need arguments to run.', True)
        return

    planet = db.get_random_planet()
    if planet is None:
        await send_internal_server_error_message(update, context)
        return
    elif not planet:
        await send(update, context, 'Couldn\'t randomize :(', False)
        return

    keys = (
        fields_['pl_name'],
        fields_['pl_eqt'],
        fields_['pl_insol'],
        fields_['pl_bmasse'],
        fields_['pl_orbper'],
        fields_['pl_orbeccen'],
        fields_['st_teff'],
        fields_['pl_refname']
    )
    data = dict(zip(keys, planet))
    msg = text.planet_spec_format(data)
    await send(update, context, msg, True)


async def distance_endpoint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) != 0:
        await send(update, context, '*Invalid Syntax:* this command doesn\'t need arguments to run.', True)
        return

    command_called = update.message.text
    if command_called == '/near':
        top3 = db.get_nearest_planets()
    else:
        top3 = db.get_farthest_planets()

    if top3 is None:
        await send_internal_server_error_message(update, context)
        return
    elif not top3:
        await send(update, context, 'We\'re currently unable to get the data needed. Please try again later.', False)
        return

    msg = f'*According to the data, the {'nearest' if command_called == '/near' else 'farthest'} planets are:*\n\n'
    index = 1
    for p in top3:
        msg += f'*{index}.* {p[0]}, ~{p[1]} parsecs distant.\n'
        index += 1

    await send(update, context, msg, True)


# function that returns an image representing the planetary system
async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) == 0:
        await send(update, context, '*Invalid Syntax:* you need to specify a celestial body name.', True)
        return
    elif '-s' in context.args and (context.args.index('-s') != len(context.args) - 1 or context.args.count('-s') > 1):
        await send(update, context, '*Invalid Syntax:* the option should be passed as the last argument.', True)
        return

    is_planet = False if context.args[-1] == '-s' else True
    if not is_planet:
        is_planet = False
        args = context.args[:-1]
    else:
        args = context.args
    name = ''.join(args).lower()

    celestial_body = db.get_celestial_body_info(name, is_planet)
    if celestial_body is not None:
        await asyncio.get_event_loop().run_in_executor(
            executor, subprocess_queue.put, update.effective_user.id
        )
        if is_planet:
            await img3d.run_blender_planet_script(update.effective_user.id, celestial_body)
        else:
            await img3d.run_blender_star_script(update.effective_user.id, celestial_body)
    elif celestial_body == -1:
        await send_internal_server_error_message(update, context)
        return
    else:
        await send(update, context, 'Celestial body not found or unable to currently retrieve the data needed.', False)
        return

    await asyncio.get_event_loop().run_in_executor(executor, subprocess_queue.get)

    await context.bot.send_photo(
        chat_id=update.effective_user.id,
        photo=open(f'{IMG_DIR}{update.effective_user.id}.png', 'rb'),
        caption=f'3d representation for the {"planet" if is_planet else "star"} \"{' '.join(context.args)}\".'
    )

    await asyncio.get_event_loop().run_in_executor(executor, img3d.delete_render_png, update.effective_user.id)


async def hab(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) == 0:
        await send(update, context, '*Invalid Syntax:* you need to specify a planet name.', True)
        return
    elif '-m' in context.args and (context.args.index('-m') != len(context.args) - 1 or context.args.count('-m') > 1):
        return

    multiple = True if context.args[-1] == '-m' else False
    if multiple:
        args = context.args[:-1]
    else:
        args = context.args

    planet = ''.join(args).lower()
    h_info = db.get_habitability_info(planet, multiple)
    if h_info is None:
        await send(update, context, 'Planet not found or currently unable to retrieve the data needed.', False)
        return
    elif h_info == -1:
        await send_internal_server_error_message(update, context)
        return

    msg = research.calculate_habitability(h_info, multiple)
    if not multiple:
        msg_chunks = [msg[i:i+4096] for i in range(0, len(msg), 4096)]
        for chunk in msg_chunks:
            await send(update, context, chunk, True)
        return

    for m in msg:
        await send(update, context, m, True)


async def hab_zone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) == 0:
        await send(update, context, '*Invalid Syntax*: You need to specify a star name.', True)
        return

    name = ' '.join(context.args).lower()
    data = db.get_habitable_zone_data(''.join(context.args).lower())
    if data is None:
        await send(update, context, f'Star not found or currently unable to retrieve the data needed.', True)
        return
    if data == -1:
        await send_internal_server_error_message(update, context)
        return

    rad, teff = data
    luminosity = research.calculate_luminosity(rad, teff)
    if luminosity is None:
        await send(update, context, f'Star not found or currently unable to retrieve the data needed.', True)
        return

    inner, outer = research.calculate_habitable_zone_edges(luminosity)
    await send(update, context, f'The habitable zone for the star \'*{name}*\' falls approximately between *{inner}* and *{outer}*, measured in Astronomical Units.', True)


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if len(context.args) < 5:
        await send(update, context, '*Invalid Syntax:* you need to write a message at least 5 words long.', True)
        return

    report_text = ' '.join(context.args)
    report_logger.info(f"Report received from {update.effective_user.username} (user_id={update.effective_user.id}): {report_text}")
    msg = 'Thanks for the report! it will help us fix the bot and provide a better experience to all users.'
    await send(update, context, msg, False)


# inline query to retrieve information about database fields meaning
async def inline_query(update: Update, context: CallbackContext) -> None:
    await register_user(update.effective_user.id)

    query = update.inline_query.query
    if not query:
        return

    matches = [val for val in definitions if query.lower() in val.lower()]

    results = [
        InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title=key,
            input_message_content=InputTextMessageContent(definitions[key])
        ) for key in matches
    ]
    await update.inline_query.answer(results)


# lets user subscribe to receive news
async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    id = update.effective_user.id
    if len(context.args) != 1:
        await send(update, context, '*Invalid Syntax:* you need to specify a time.', True)
        return

    time = context.args[0]
    regex = r'^([0-9]{2})\:([0-9]{2})$'
    match = re.match(regex, time)
    if not (match and (0 <= int(match.group(1)) < 24) and (0 <= int(match.group(2)) < 60)):
        await send(update, context, '*Value Error:* specified time doesn\'t match the required format.', True)
        return

    subs = await asyncio.get_event_loop().run_in_executor(executor, read_subs)
    if subs is None:
        await send_internal_server_error_message(update, context)
        return

    already_sub = False
    for i in range(len(subs)):
        if subs[i].strip().split('-')[0] == str(id):
            subs[i] = f'{id}-{time}\n'
            already_sub = True
            break

    if not already_sub:
        subs.append(f'{id}-{time}')

    write = await asyncio.get_event_loop().run_in_executor(executor, write_subs, subs)
    if not write:
        await send_internal_server_error_message(update, context)
        return

    msg = 'Your subscription was processed correctly.'
    await send(update, context, msg, False)


# lets user unsubscribe
async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)

    if await notify_user_if_updating(update, context):
        return

    if len(context.args) != 0:
        await send(update, context, '*Invalid Syntax:* this command doesn\'t need arguments to run.', True)
        return

    id = update.effective_user.id
    subs = await asyncio.get_event_loop().run_in_executor(executor, read_subs)
    if subs is None:
        await send_internal_server_error_message(update, context)
        return

    orig_len = len(subs)
    filtered = [sub for sub in subs if sub.strip().split('-')[0] != str(id)]

    write = await asyncio.get_event_loop().run_in_executor(executor, write_subs, filtered)
    if not write:
        await send_internal_server_error_message(update, context)
        return

    msg = 'Your unsubscription was processed correctly.'
    if len(filtered) == orig_len:
        msg = 'You\'re not subscribed.'

    await send(update, context, msg, False)


# stock message for unknown commands
async def unknown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await register_user(update.effective_user.id)
    print(update.effective_chat.id)
    print(update.effective_user.id)
    await update.message.reply_text('Command not found.')

# __________________________COMMAND HANDLERS__________________________________

# I put these handlers in order to let the user run a command while he executed
# one of these, since they're the ones that takes a bit much to return a result.
# asyncio.create_task seems the only solutions to make it possible.

'''
async def locate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    asyncio.create_task(locate(update, context))

async def show_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    asyncio.create_task(show(update, context))

async def table_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    asyncio.create_task(table(update, context))

async def plot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    asyncio.create_task(plot(update, context))
'''

# _______________________________BOT SETUP____________________________________

def _read_token() -> str:
    with open(TOKEN_PATH, 'r') as file:
        return file.readline().strip()


def _load_fields():
    with open(FIELDS_PATH, 'r') as file:
        for line in file:
            pair = line.strip().split(':')
            fields_[pair[0]] = pair[1]


def _load_definitions():
    with open(DEF_PATH, 'r') as file:
        for line in file:
            pair = line.strip().split(':')
            definitions[pair[0]] = pair[1]


def _load_infos():
    with open(INFO_PATH, 'r') as file:
        for line in file:
            pair = line.strip().split(':', maxsplit=1)
            comm_infos[pair[0]] = pair[1]


def run() -> None:
    global updater

    _load_fields()
    _load_definitions()
    _load_infos()

    token = _read_token()
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help))
    application.add_handler(CommandHandler('info', info))
    application.add_handler(CommandHandler('count', count))
    application.add_handler(CommandHandler('pcount', count))
    application.add_handler(CommandHandler('discin', disc_in))
    application.add_handler(CommandHandler('search', search))
    application.add_handler(CommandHandler('table', table))
    application.add_handler(CommandHandler('plot', plot))
    application.add_handler(CommandHandler('fields', fields))
    application.add_handler(CommandHandler('cst', constellation))
    application.add_handler(CommandHandler('locate', locate))
    application.add_handler(CommandHandler('random', rand))
    application.add_handler(CommandHandler('near', distance_endpoint))
    application.add_handler(CommandHandler('far', distance_endpoint))
    application.add_handler(CommandHandler('show', show))
    application.add_handler(CommandHandler('hab', hab))
    application.add_handler(CommandHandler('habzone', hab_zone))
    application.add_handler(CommandHandler('report', report))
    application.add_handler(CommandHandler('sub', subscribe))
    application.add_handler(CommandHandler('unsub', unsubscribe))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_cmd))
    application.add_handler(CallbackQueryHandler(button_listener))
    application.add_handler(InlineQueryHandler(inline_query))

    updater.set_bot(application.bot)
    updater.set_ids(list(search_data.keys()))
    updater.set_sleep_lock(state_lock)
    updater.set_ids_lock(updater_ids_lock)
    news_scheduler = mythreads.NewsScheduler(application.bot, subLock, newsLock)
    news_fetcher = mythreads.NewsFetcher(newsLock)
    updater.daemon = True
    news_fetcher.daemon = True
    news_scheduler.daemon = True
    updater.start()
    news_scheduler.start()
    news_fetcher.start()

    application.run_polling()
