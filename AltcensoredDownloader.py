import requests
from lxml import html
from fake_useragent import UserAgent
import csv
import time
import json
import os
import shutil
import re
import subprocess

# SELENIUM
from selenium import webdriver
import undetected_chromedriver  #as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains


# VARIABLES ############################################################################################################
user_agent = None
selenium_temp_dir = os.path.join(os.getcwd(), 'temp')
max_workers = 5
headless = True


# Functions ############################################################################################################
def get_all_links_from_channel(channel_link='https://altcensored.com/channel/UCC3L8QaxqEGUiBC252GHy3w'):
    links = []  # list of dictionaries
    number_of_pages_xpath = '(//div[@class="pagination"]//a)[1]' # Only works from page 1
    video_xpath = '//div[@class="pure-g"]//div[@class="pure-g"]//div[@class="h-box"]/p/a'
    thumbnail_info_xpath = '//div[@class="pure-g"]//div[@class="pure-g"]//div[@class="h-box"]//img[@class="thumbnail"]'

    # Visit the channel page
    tree, driver = get_link_with_selenium(channel_link, session=None, user_agent=None, proxy=None, scroll_to_bottom_num=0)

    # Get number of pages
    number_of_pages = tree.xpath(number_of_pages_xpath)[0].text
    number_of_pages = int(number_of_pages.strip().replace(',', ''))
    print(f'Scraping {str(number_of_pages)} page(s).')

    # get it for each page
    for i in range(number_of_pages):
        i = i + 1

        url = channel_link + f'/page/{i}'
        # append this for as many times as needed
        tree, driver = get_link_with_selenium(url, session=driver, user_agent=None, proxy=None, scroll_to_bottom_num=0)

        results_on_page = tree.xpath(video_xpath)
        thumbs = tree.xpath(thumbnail_info_xpath)

        for i, vid in enumerate(results_on_page):
            link = "https://altcensored.com" + vid.get('href')
            title = vid.text.strip()
            thumbnail_info = thumbs[i].get('src')
            # https://altcensored.com/ip/180x102/https://archive.org/download/youtube-a4zi4KVlNP0/__ia_thumb.jpg
            thumbnail_info = thumbnail_info.split('__ia_thumb')[0]
            thumbnail_info = thumbnail_info.split('https://')[-1]
            files = f"https://{thumbnail_info}"
            print(f'{title} | {link} | {files}')
            data = {"link": link, "title": title, "files": files}
            links.append(data)
            write_to_csv(file_path='videos.csv', list=[json.dumps(data)])

    return links


def download_file_wait(driver, folder_name, file, base_url, max_retries=3, retry_delay=2):
    # Create the folder if it doesn't exist
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    # Construct complete file URL
    file_url = f"{base_url}{file}"
    #print(file_url)

    # Initialize retry counter and success flag
    retries = 0
    download_successful = False

    # File path
    file_path = os.path.join(folder_name, file)

    while retries < max_retries and not download_successful:
        try:
            # Download the file
            r = requests.get(file_url)

            # Save the file, overwriting if it already exists
            with open(file_path, 'wb') as f:
                f.write(r.content)

            # Wait until the file exists
            while not os.path.exists(file_path):
                time.sleep(1)

            # Ensure the file is completely downloaded
            temp_size = -1
            while temp_size != os.path.getsize(file_path):
                temp_size = os.path.getsize(file_path)
                time.sleep(1)

            download_successful = True

        except Exception as e:
            print(f"Download failed. Retrying... ({retries + 1}/{max_retries})")
            retries += 1
            time.sleep(retry_delay)

    return download_successful


def clean_title(input_str):
    # Only allow alphanumeric, space, hyphen, underscore, and period
    allowed_chars = re.compile('[^a-zA-Z0-9-_. ]+')
    sanitized_str = re.sub(allowed_chars, '', input_str)
    return sanitized_str


def get_all_content(driver):
    items_xpath = '//table[@class="directory-listing-table"]//tr//a'  # always skip first

    with open(file='videos.csv', mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        #next(reader)  # Skip the header row
        for row in reader:
            value = json.loads(row[0])
            #print(value["title"])
            title = value["title"]
            link = value["link"]
            files = value["files"]

            tree, driver = get_link_with_selenium(files, session=driver)

            items = tree.xpath(items_xpath)
            items.pop(0)
            items.pop(0)
            for file in items:
                file = file.get("href")
                #print(file)
                if download_file_wait(driver, folder_name=f'content/{clean_title(title)}', file=file, base_url=files, max_retries=3, retry_delay=2):
                    print(f'Downloaded - {file}')
                else:
                    print('Download failed.')

    quit_driver(driver)


def show_logo():
    print('''
        _   _ _    ___                             _   ___                  _              _         
       /_\ | | |_ / __|___ _ _  ___ ___ _ _ ___ __| | |   \ _____ __ ___ _ | |___  __ _ __| |___ _ _ 
      / _ \| |  _| (__/ -_) ' \(_-</ _ \ '_/ -_) _` | | |) / _ \ V  V / ' \| / _ \/ _` / _` / -_) '_|
     /_/ \_\_|\__|\___\___|_||_/__/\___/_| \___\__,_| |___/\___/\_/\_/|_||_|_\___/\__,_\__,_\___|_|  
     
     ===============================================================================================
                     A tool for bulk-downloading video content from Altcensored.com
         (a site that archives YouTube channels that upload potentially controversial content.)
    ''')


# GENERAL FUNCTIONS ####################################################################################################
def set_chrome_options(user_agent=None, proxy=None):
    options = webdriver.ChromeOptions()

    if headless:
        options.add_argument("--headless=new")

    # disable Chrome popups
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-save-password-bubble")
    options.add_argument(f"--user-data-dir={selenium_temp_dir}")  # Set custom user data directory

    if user_agent:
        options.add_argument(f'user-agent={user_agent}')

    if proxy:
        options.add_argument(f'proxy-server={proxy}')

    return options


def setup_driver(user_agent=None, proxy=None):
    options = set_chrome_options(user_agent, proxy)
    driver = undetected_chromedriver.Chrome(options=options)
    driver.set_page_load_timeout(60)  # wait 60 second before error
    return driver


def quit_driver(driver):
    try:
        if driver is not None:
            driver.quit()
            shutil.rmtree(selenium_temp_dir, ignore_errors=True)  # Delete the temporary directory
    except:
        pass


def get_link(url, session=None, user_agent=None, proxy=None):
    """
    Fetches the HTML content from the provided URL.
    Returns a parsed lxml HTML tree that can be used with XPath.
    """
    ua = UserAgent()
    headers = {
        'Content-Type': '',
        'Sec-CH-UA': '"Not/A)Brand";v="99", "Brave";v="115", "Chromium";v="115"',
        'Sec-CH-UA-Mobile': '?0',
        'Sec-CH-UA-Platform': '"Windows"',
        'Sec-CH-UA-Platform-Version': '"10.0.0"',
        'Sec-CH-UA-Model': '""',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': ua['chrome'] if not user_agent else user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Sec-GPC': '1',
        'Accept-Language': 'en-US,en;q=0.5',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-User': '?1',
        'Sec-Fetch-Dest': 'document',
        'Referer': 'https://www.whatismybrowser.com/',
        'Accept-Encoding': 'gzip, deflate, br'
    }

    proxies = {'http': proxy, 'https': proxy} if proxy else {}

    if session is None:
        session = requests.Session()

    response = session.get(url, headers=headers, proxies=proxies)
    tree = html.fromstring(response.content)

    return tree, session


def get_link_with_selenium(url, session=None, user_agent=None, proxy=None, scroll_to_bottom_num=0):
    # keeping the name for driver "session" so this can be a replacement function without having to change names
    # pass through scroll to bottom num which will be unique to each task. 999 = all the way
    if not url:
        return ''

    driver = session
    if driver is None:
        driver = setup_driver(user_agent, proxy)

    if 'http' not in url:
        url = 'http://' + url

    #print('we are here')
    #print(url)
    driver.get(url)
    #print('we visited the url')

    # Send the "END" key to scroll to the bottom
    if scroll_to_bottom_num == 999:
        driver.find_element(By.TAG_NAME, 'html').send_keys(Keys.END)  # or body
        time.sleep(1)

    elif scroll_to_bottom_num == 0:
        pass

    elif scroll_to_bottom_num:
        for _ in range(scroll_to_bottom_num):
            driver.find_element(By.TAG_NAME, 'html').send_keys(Keys.SPACE)  # or body
            time.sleep(0.50)
        time.sleep(1)

    # ------------------------------------------

    tree = html.fromstring(driver.page_source)

    return tree, driver


def load_from_csv(file_path):
    # Load things from a one-column CSV file.
    loaded = []
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        loaded = [row[0] for row in reader]
    print('Loaded csv')
    return loaded


def write_to_csv(file_path, list):
    # Wrtie a list to a one-column csv file
    with open(file_path, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for row in list:
            writer.writerow([row])
    #print(f'Saved to {file_path}')


def download_and_save_image(url, filename):
    try:
        # Send an HTTP request to get the image data
        response = requests.get(url)

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            # Save the image to the current directory with the specified filename
            with open(filename, 'wb') as file:
                file.write(response.content)
            print("Image downloaded and saved successfully.")
        else:
            print(f"Failed to download the image. Status code: {response.status_code}")

    except requests.exceptions.RequestException as e:
        print(f"Error occurred while downloading the image: {e}")


# START PROGRAM ########################################################################################################
show_logo()

print('What would you like to do?')
print('( 1. ) - Create "videos.csv" from an input channel link (a spreadsheet of ALL video links and titles uploaded by the channel)')
print('( 2. ) - Download all video content listed in the videos.csv file\n')

user_entered = ''
while True:
    try:
        user_entered = int(input('Type either 1 or 2, and then press enter:  '))
        if user_entered == 1 or user_entered == 2:
            break
    except:
        pass
    print('Invalid entry. Enter either 1 or 2.')

print('\n')
if user_entered == 1:
    print('To create "videos.csv", you must paste an altcensored channel link like this:\n')
    print('https://altcensored.com/channel/UCC3L8QaxqEGUiBC252GHy3w\n')
    channel_link = input('Paste the link to the channel that you would like to download:\n\n')
    print('...working\n')
    get_all_links_from_channel(channel_link=channel_link)
    print('Done creating "videos.csv". You can now restart this program and run step 2.')

elif user_entered == 2:
    print('Downloading all video content.\n')
    driver = setup_driver()
    get_all_content(driver=driver)
    print('Done!')

else:
    pass
