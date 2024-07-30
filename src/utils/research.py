from astropy.coordinates import SkyCoord, get_constellation
import matplotlib.pyplot as plt
from astropy.wcs import WCS
from astroquery.skyview import SkyView
from io import BytesIO
import astropy.units as u
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
import random
from bs4 import BeautifulSoup
import math
from src.utils import text


FILE = 'resources/data/news.txt'
SOLAR_TEFF = 5778
UG_CONST = 6.67e-11
EARTH_MASS = 5.9722e24
SOLAR_MASS = 1.989e30
EARTH_RAD = 6371e3
ALBEDO = 0.3
C = 3e8


def fetch_news(keyword='exoplanets news'):
    url = f'https://www.google.com/search?q={keyword}'
    options = Options()
    options.add_argument('--headless')
    service = Service('/snap/bin/geckodriver')
    driver = webdriver.Firefox(service=service, options=options)
    driver.get(url)

    driver.implicitly_wait(20)
    driver.find_element(By.XPATH, '//div[text()=\'Accetta tutto\']').click()
    driver.find_element(By.XPATH, '//div[text()=\'Notizie\']').click()

    page = driver.page_source
    driver.quit()

    soup = BeautifulSoup(page, 'html.parser')
    a = soup.find_all('a', class_='WlydOe')

    return ','.join([link.get('href') for link in a]) if len(a) > 0 else ''


def get_rand_news():
    with open(FILE, 'r') as file:
        links = file.read().strip().split(',')

    return random.choice(links)


def get_constellation_from_coordinates(coord, convert_to_sky_coord=False):
    if not convert_to_sky_coord:
        return get_constellation(coord)
    sky_coord = SkyCoord(ra=coord[0], dec=coord[1], unit=(u.hourangle, u.deg))
    return get_constellation(sky_coord)


def fetch_sky_image(pair):
    coord = SkyCoord(ra=pair[0], dec=pair[1], unit=(u.hourangle, u.deg))
    image_list = SkyView.get_images(position=coord, survey=['DSS'], pixels=750)
    data = image_list[0][0].data
    wcs = WCS(image_list[0][0].header)

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection=wcs)
    ax.imshow(data, origin='lower', cmap='gray')
    ax.plot(coord.ra.deg, coord.dec.deg, 'ro', transform=ax.get_transform('world'))
    plt.xlabel('RA (degrees)')
    plt.ylabel('Dec (degrees)')
    plt.grid(color='white', linestyle='--', linewidth=0.5)
    plt.title(f'Constellation: {get_constellation_from_coordinates(coord, convert_to_sky_coord=False)}')

    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    plt.close(fig)
    return buffer


def calculate_luminosity(st_rad, st_teff):
    return (st_rad ** 2) * ((st_teff / SOLAR_TEFF) ** 4)


def calculate_habitable_zone_edges(luminosity):
    hab_zone_inner = round(math.sqrt(luminosity / 1.1), 2)
    hab_zone_outer = round(math.sqrt(luminosity / 0.53), 2)
    return hab_zone_inner, hab_zone_outer


def calculate_habitability(data, multiple):
    if not multiple:
        return _calculate_habitability_index(data, multiple)

    summaries = []
    for planet in data:
        summary = _calculate_habitability_index(planet, multiple)
        summaries.append(summary)

    return summaries


def _calculate_habitability_index(data, multiple, threshold=0.5):
    def pl_gravity(mass, rad):
        return UG_CONST * (mass / rad ** 2)

    conditions = {
        'inner_zone_condition': False,
        'outer_zone_condition': False,
        'gravity_condition': False,
        'temperature_condition': False,
        'insolation_flux_condition': False,
        'temp_habitability': False,
        'spectral_type_condition': False
    }

    luminosity = None
    if data['st_rad'] is not None and data['st_teff'] is not None:
        luminosity = calculate_luminosity(data['st_rad'], data['st_teff'])

    equilibrium_temperature = data['pl_eqt']
    if equilibrium_temperature is None and luminosity is not None and data['pl_orbsmax'] is not None:
        equilibrium_temperature = ((luminosity * (1 - ALBEDO)) / (16 * math.pi * (data['pl_orbsmax'] ** 2) * 5.670374419e-8)) ** 0.25

    if luminosity is not None:
        hab_zone_inner, hab_zone_outer = calculate_habitable_zone_edges(luminosity)
        if data['pl_orbsmax'] is not None and data['pl_orbeccen'] is not None:
            peri = data['pl_orbsmax'] * (1 - data['pl_orbeccen'])
            apo = data['pl_orbsmax'] * (1 + data['pl_orbeccen'])
            conditions['inner_zone_condition'] = hab_zone_inner <= peri <= hab_zone_outer
            conditions['outer_zone_condition'] = hab_zone_inner <= apo <= hab_zone_outer

    if data['pl_bmasse'] is not None and data['pl_rade'] is not None:
        gravity = pl_gravity(data['pl_bmasse'] * EARTH_MASS, data['pl_rade'] * EARTH_RAD)
        conditions['gravity_condition'] = 0.9 <= round(gravity, 1) / 9.8 <= 1.3

    if data['st_teff'] is not None:
        conditions['temperature_condition'] = 3900 <= data['st_teff'] <= 7100

    if data['pl_insol'] is not None:
        conditions['insolation_flux_condition'] = 0.35 <= data['pl_insol'] <= 1.75

    if equilibrium_temperature is not None:
        conditions['temp_habitability'] = 273 <= equilibrium_temperature <= 373

    if data['st_spectype'] is not None:
        conditions['spectral_type_condition'] = 'G' in data['st_spectype'] or 'K' in data['st_spectype']

    valid_conditions = {k: v for k, v in conditions.items() if v is not None}
    habitability_index = sum(valid_conditions.values()) / len(valid_conditions)

    is_habitable = habitability_index >= threshold

    research_group = ''
    if multiple:
        match = text.get_href_match(data['pl_refname'])
        if match:
            research_group = f"The following summary is based on the data observed by [{match.group(2)}]({match.group(1)})\n\n"
        else:
            research_group = "Could not retrieve the research group.\n\n"

    summary = (
        research_group +
        f"The planet has a habitability index of *{habitability_index:.2f}*. "
        f"It {'meets' if is_habitable else 'does not meet'} the minimum habitability threshold of {threshold:.2f}. "
        f"The conditions evaluated include: \n"
        f"- *Inner Habitable Zone*: {'Met' if conditions['inner_zone_condition'] else 'Not Met'}\n"
        f"- *Outer Habitable Zone*: {'Met' if conditions['outer_zone_condition'] else 'Not Met'}\n"
        f"- *Gravity Condition*: {'Met' if conditions['gravity_condition'] else 'Not Met'}\n"
        f"- *Stellar Temperature Condition*: {'Met' if conditions['temperature_condition'] else 'Not Met'}\n"
        f"- *Insolation Flux Condition*: {'Met' if conditions['insolation_flux_condition'] else 'Not Met'}\n"
        f"- *Equilibrium Temperature Condition*: {'Met' if conditions['temp_habitability'] else 'Not Met'}\n"
        f"- *Spectral Type Condition*: {'Met' if conditions['spectral_type_condition'] else 'Not Met'}\n\n"
        f"{'Here are the reasons why the planet does not meet the habitability criteria:' if not is_habitable else ''}\n"
        f"{'' if conditions['inner_zone_condition'] else '- The planet\'s orbit does not fall within the inner habitable zone.\n'}"
        f"{'' if conditions['outer_zone_condition'] else '- The planet\'s orbit does not fall within the outer habitable zone.\n'}"
        f"{'' if conditions['gravity_condition'] else '- The planet\'s gravity is not within the acceptable range for habitability.\n'}"
        f"{'' if conditions['temperature_condition'] else '- The star\'s temperature is not within the suitable range for habitability.\n'}"
        f"{'' if conditions['insolation_flux_condition'] else '- The planet receives insolation flux outside the habitable range.\n'}"
        f"{'' if conditions['temp_habitability'] else '- The planet\'s equilibrium temperature is not within the habitable range.\n'}"
        f"{'' if conditions['spectral_type_condition'] else '- The star\'s spectral type is not suitable for habitability.'}"
    )

    return summary


def calculate_schwarzschild_radius(mass, is_planet):
    radius = (2 * UG_CONST / C ** 2) * (mass * EARTH_MASS if is_planet else mass * SOLAR_MASS)
    return round(radius, 3)
