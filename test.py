import airline_manager4 as am4
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


if __name__ == '__main__':
    am4.username = ''
    am4.password = ''
    am4.fuel_price_threshold = '100'
    am4.co2_price_threshold = '100'

    options = Options()
    options.headless = False
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    w_driver = webdriver.Chrome(options=options,
                                executable_path='drivers/chromedriver')
    w_driver.maximize_window()

    am4.w_driver = w_driver

    # am4.login(am4.username, am4.password)

    # test whatever you want here....

    am4.update_ticket_price()

    # am4.logout()
