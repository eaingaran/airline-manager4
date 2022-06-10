import json
import os
import requests

from flask import Flask

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import logging
from logging.config import fileConfig

fileConfig('logger.cfg')
LOGGER = logging.getLogger()

if 'LOG_LEVEL' in os.environ:
    log_levels = {'NOTSET': 0, 'DEBUG': 10, 'INFO': 20, 'WARN': 30, 'ERROR': 40, 'CRITICAL': 50}
    if os.environ.get('LOG_LEVEL') in log_levels:
        LOGGER.setLevel(log_levels[os.environ.get('LOG_LEVEL')])
    else:
        LOGGER.error(f'LOG_LEVEL {os.environ.get("LOG_LEVEL")} is not a valid level. using {LOGGER.level}')
else:
    LOGGER.warning(f'LOG_LEVEL not set. current log level is {LOGGER.level}')


app_name = 'Airline Manager Automation'

app = Flask(app_name)

username = os.environ.get('USERNAME')
password = os.environ.get('PASSWORD')
fuel_price_threshold = os.environ.get('MAX_BUY_FUEL_PRICE', 400)
low_fuel_level = os.environ.get('LOW_FUEL_LEVEL', 10000000)
low_fuel_price_threshold = os.environ.get('MAX_BUY_LOW_FUEL_PRICE', 800)
co2_price_threshold = os.environ.get('MAX_BUY_CO2_PRICE', 111)
low_co2_level = os.environ.get('LOW_CO2_LEVEL', 10000000)
low_co2_price_threshold = os.environ.get('MAX_BUY_LOW_CO2_PRICE', 140)

LOGGER.info(f'fuel tank will be filled if the price is less than ${fuel_price_threshold}')
LOGGER.info(f'if the fuel tank has less than {low_fuel_level} lbs, difference will be purchased if the fuel price is '
            f'below ${low_fuel_price_threshold}')
LOGGER.info(f'co2 quota will be filled if the price is less than ${co2_price_threshold}')
LOGGER.info(f'if the co2 quota is less than {low_co2_level} lbs, difference will be purchased if the co2 quota price '
            f'is below ${low_co2_price_threshold}')

w_driver = None


def get_driver():
    global w_driver
    if w_driver is None:
        options = Options()
        options.headless = True
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        w_driver = webdriver.Chrome(options=options)
        w_driver.maximize_window()
        return w_driver
    return w_driver


def login(u_name, p_word):
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/')
    m_login_btn = driver.find_element(By.CSS_SELECTOR, "button.btn.btn-success[data-toggle='modal'][data-target$='loginModal']")
    if m_login_btn is not None and m_login_btn.is_displayed():
        m_login_btn.click()
        email_field = driver.find_element(By.ID, 'lEmail')
        email_field.send_keys(u_name)
        pass_field = driver.find_element(By.ID, 'lPass')
        pass_field.send_keys(p_word)
        login_btn = driver.find_element(By.ID, 'btnLogin')
        login_btn.click()
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, 'flightInfoToggleIcon')))


def logout():
    global w_driver
    if w_driver is not None:
        w_driver.get('https://www.airlinemanager.com/weblogin/logout.php')
        w_driver.quit()
        w_driver = None


def get_fuel_stats():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/fuel.php')
    price = driver.find_element(By.XPATH, '/html/body/div/div/div[1]/span[2]/b').text
    capacity = driver.find_element(By.ID, 'remCapacity').text
    holding = driver.find_element(By.ID, 'holding').text
    LOGGER.info(f'Holding {holding} and capacity Remaining is {capacity} and current fuel price is {price}')
    return price, capacity, holding


def get_co2_stats():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/co2.php')
    price = driver.find_element(By.XPATH, '/html/body/div/div/div[2]/span[2]/b').text
    capacity = driver.find_element(By.ID, 'remCapacity').text
    holding = driver.find_element(By.ID, 'holding').text
    LOGGER.info(f'Holding {holding} and capacity Remaining is {capacity} and current co2 price is {price}')
    return price, capacity, holding


def depart_planes():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/route_depart.php?mode=all&ids=x')
    LOGGER.info('all planes departed')


def get_balance():
    driver = get_driver()
    driver.get('https://www.airlinemanager.com/')
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, 'headerAccount')))
    balance = driver.find_element(By.ID, 'headerAccount').text
    LOGGER.info(f'Account balance is {balance}')
    return int(balance.replace(',', ''))


def buy_fuel(quantity):
    driver = get_driver()
    driver.get(f'https://www.airlinemanager.com/fuel.php?mode=do&amount={quantity}')
    LOGGER.info(f'bought {quantity} fuel')


def buy_co2(quantity):
    driver = get_driver()
    driver.get(f'https://www.airlinemanager.com/co2.php?mode=do&amount={quantity}')
    LOGGER.info(f'bought {quantity} co2 quota')


def perform_routine_ops():
    # depart planes
    depart_planes()
    # depart planes again, in case there were more than 20 planes to be departed
    depart_planes()

    # fuel checks
    fuel_price, fuel_capacity, fuel_holding = get_fuel_stats()
    fuel_price_num = int(fuel_price.replace('$', '').replace(',', '').replace(' ', ''))
    fuel_capacity_num = int(fuel_capacity.replace(',', '').replace(' ', ''))
    fuel_holding_num = int(fuel_holding.replace(',', '').replace(' ', ''))
    if fuel_price_num < int(fuel_price_threshold):
        balance = get_balance()
        if (fuel_capacity_num * fuel_price_num)/1000 < balance:
            buy_fuel(fuel_capacity_num)
        else:
            purchase_qty = (balance * 1000) / fuel_price_num
            buy_fuel(purchase_qty)
    elif fuel_holding_num < int(low_fuel_level) and fuel_price_num < int(low_fuel_price_threshold):
        balance = get_balance()
        if ((int(low_fuel_level) - fuel_holding_num) * fuel_price_num) / 1000 < balance:
            buy_fuel(int(low_fuel_level) - fuel_holding_num)
        else:
            purchase_qty = (balance * 1000) / fuel_price_num
            buy_fuel(purchase_qty)
    else:
        LOGGER.info(f'fuel price is too high to buy...')

    # co2 checks
    co2_price, co2_capacity, co2_holding = get_co2_stats()
    co2_price_num = int(co2_price.replace('$', '').replace(',', '').replace(' ', ''))
    co2_capacity_num = int(co2_capacity.replace(',', '').replace(' ', ''))
    co2_holding_num = int(co2_holding.replace(',', '').replace(' ', ''))
    if co2_price_num < (111 if co2_price_threshold is None else int(co2_price_threshold)):
        balance = get_balance()
        if (co2_capacity_num * co2_price_num)/1000 < balance:
            buy_co2(co2_capacity_num)
            pass
        else:
            purchase_qty = (balance * 1000)/co2_price_num
            buy_co2(purchase_qty)
    elif co2_holding_num < int(low_co2_level) and co2_price_num < int(low_co2_price_threshold):
        balance = get_balance()
        if ((int(low_co2_level) - co2_holding_num) * co2_price_num) / 1000 < balance:
            buy_co2(int(low_co2_level) - co2_holding_num)
        else:
            purchase_qty = (balance * 1000) / co2_price_num
            buy_co2(purchase_qty)
    else:
        LOGGER.info(f'co2 price is too high to buy...')


def set_ticket_price(route_id, e, b, f):
    driver = get_driver()
    driver.get(f'https://www.airlinemanager.com/set_ticket_prices.php?e={e}&b={b}&f={f}&id={route_id}')


def get_routes():
    route_list = []
    driver = get_driver()
    start = 0
    while True:
        driver.get(f'https://www.airlinemanager.com/routes.php?start={start}')
        routes_container = driver.find_element(By.ID, 'routesContainer')
        elements = routes_container.find_elements(by=By.CLASS_NAME, value='m-text')
        for element in elements:
            route_id = element.get_property('id').replace('routeMainList', '')
            route_desc = element.find_element(By.XPATH, f'//*[@id="routeMainList{route_id}"]/div[1]/div/div[2]/span').text
            ticket_price = get_route_details(route_desc.split(' - ')[0], route_desc.split(' - ')[1])[1]['realism']
            route_list.append({'route_id': route_id, 'route_desc': route_desc, 'ticket_price': ticket_price})
        if len(elements) == 20:
            start += 20
        else:
            break

    return route_list


def get_route_details(departure, arrival):
    response = requests.get(f'https://am4tools.com/route/ticket?type=pax&mode=normal&departure={departure}&arrival={arrival}')
    if response.status_code == 200:
        route_details = json.loads(response.text)
    else:
        route_details = None
    return route_details['routes'][0], route_details['ticket']


@app.route('/update_ticket_price')
def update_ticket_price():
    login(username, password)
    route_list = get_routes()
    for route in route_list:
        set_ticket_price(route['route_id'], route['ticket_price']['ticketY'],
                         route['ticket_price']['ticketJ'], route['ticket_price']['ticketF'])
    logout()
    return 'ticket prices updated', 200


def create_route():
    pass


def buy_aircraft(plane_id, hub_id, engine_id, plane_name, economy, business, first):
    driver = get_driver()
    driver.get(f'https://www.airlinemanager.com/ac_order_do.php?id={plane_id}&hub={hub_id}&e={economy}&b={business}&'
               f'f={first}&r={plane_name}&engine={engine_id}&amount=1&fbSig=false')
    LOGGER.info(f'bought plane {plane_name}')


@app.route('/')
def run_app():
    login(username, password)
    perform_routine_ops()
    logout()
    return 'All Done!', 200


if __name__ == '__main__':
    from waitress import serve

    serve(app, host='0.0.0.0', port=8080)
