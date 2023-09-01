import os
import re
import csv
import glob
import time
import json
import shutil
import requests
from lxml import html
from pydub import AudioSegment
from fake_useragent import UserAgent

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

videos_file = 'videos.csv'
videos_successfully_downloaded_file = 'downloaded_successfully.csv'
videos_that_may_have_failed_file = 'videos_that_may_have_failed.csv'


# Functions ############################################################################################################
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
            write_to_csv(file_path=videos_file, list=[json.dumps(data)])

    return links


def get_all_content(driver):
    items_xpath = '//table[@class="directory-listing-table"]//tr//a'  # always skip first

    finished = []
    if os.path.exists(videos_successfully_downloaded_file):
        with open(file=videos_successfully_downloaded_file, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                value = json.loads(row[0])
                finished.append(value)

    with open(file=videos_file, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        #next(reader)  # Skip the header row
        for row in reader:
            error = False
            value = json.loads(row[0])
            if value in finished:
                print(f'Skipping - {value["title"]} - ( Downloaded already )')
                continue
            else:
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
                    if download_file_wait(driver, folder_name=f'content/{clean_title(title)}', file=file, base_url=files, max_retries=5, retry_delay=2):
                        print(f'Downloaded - {file}')
                    else:
                        print('Download failed.')
                        error = True

                if not error:
                    write_to_csv(file_path=videos_successfully_downloaded_file, list=[json.dumps(value)])
                else:
                    write_to_csv(file_path=videos_that_may_have_failed_file, list=[json.dumps(value)])

    quit_driver(driver)


def find_largest_video_files_in_folders():
    # FIND THE LARGEST VIDEO FILE IN EACH FOLDER
    largest_video_files = []
    # Traverse the '\content' directory for subdirectories
    for foldername in os.listdir('content'):
        folder_path = os.path.join('content', foldername)

        if os.path.isdir(folder_path):
            # For each subdirectory, find all video files
            video_files = glob.glob(f"{folder_path}/*.[mM][pP]4")  # + glob.glob(f"{folder_path}/*.[aA][vV][iI]") + glob.glob(f"{folder_path}/*.[mM][kK][vV]")  # Add more if needed

            if video_files:  # Make sure there is at least 1 video file
                largest_file = max(video_files, key=os.path.getsize)
                largest_video_files.append(largest_file)

    return largest_video_files


def convert_mp4_to_wav(input_file):
    print(f'Converting {input_file} to audio')
    # Replace the path below with the path to your input MP4 file
    input_mp4_file = input_file
    # Replace the path below with the path to your output WAV file
    output_wav_file = f"{input_file[:-4]}.wav"
    # Read the MP4 audio file
    audio = AudioSegment.from_file(input_mp4_file, format="mp4")
    # Export the audio to a WAV file
    audio.export(output_wav_file, format="wav")
    print(f'FINISHED - {output_wav_file}')
    return output_wav_file


def use_whisper(audio_file, model='medium', keep_txt=True, keep_srt=True, keep_wav=True, keep_vtt=True, keep_tsv=True, keep_json=True):
    print(f'Converting {audio_file} to text')

    #  NOTE TO FUTURE EMPLOYERS: I know this is a stupid way to do it.
    # I had already written it to work this way for something different months ago, and I'm not rewriting it right now.
    command = f'whisper "{audio_file}" --model {model} --language English'  #base is good enough. large for pro

    # Execute the command
    os.system(command)
    audio_file_name = audio_file[:-4]
    created_text_file = audio_file_name + '.txt'
    if not keep_json: os.remove(audio_file_name + '.json')
    if not keep_tsv: os.remove(audio_file_name + '.tsv')
    if not keep_vtt: os.remove(audio_file_name + '.vtt')
    if not keep_wav: os.remove(audio_file)
    if not keep_srt: os.remove(audio_file_name + '.srt')
    with open(file=created_text_file, mode='r', encoding='utf-8') as f:
        text = f.read()
    if not keep_txt: os.remove(audio_file_name + '.txt')
    print(text)
    return text


def transcribe_all_with_whisper():
    largest_video_files = find_largest_video_files_in_folders()

    # Make audio files and transcribe each video
    for video in largest_video_files:
        print(video)
        audio_file = convert_mp4_to_wav(input_file=video)
        use_whisper(audio_file=audio_file, model='base')
        pass


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


# START PROGRAM ########################################################################################################
show_logo()

print('What would you like to do?')
print(f'( 1. ) - Create "{videos_file}" from an input channel link (a spreadsheet of ALL video links and titles uploaded by the channel)')
print(f'( 2. ) - Download all video content listed in the "{videos_file}" file')
print('( 3. ) - Transcribe all downloaded video content. Creates text transcription, subtitles with time codes, audio file, etc.\n')

user_entered = ''
while True:
    try:
        user_entered = int(input('Type either 1, 2, or 3 and then press enter:  '))
        if user_entered > 0 and user_entered < 4:
            break
    except:
        pass
    print('Invalid entry. Enter either 1, 2, or 3')

print('\n')
if user_entered == 1:
    print(f'To create "{videos_file}", you must paste an altcensored channel link like this:\n')
    print('https://altcensored.com/channel/UCC3L8QaxqEGUiBC252GHy3w\n')
    channel_link = input('Paste the link to the channel that you would like to download:\n\n')
    print('...working\n')
    get_all_links_from_channel(channel_link=channel_link)
    print(f'Done creating "{videos_file}". You can now restart this program and run step 2.')

elif user_entered == 2:
    print('Downloading all video content.\n')
    driver = setup_driver()
    get_all_content(driver=driver)
    print('Done!')

elif user_entered == 3:
    print('Please note, this will not work unless you have already done the following: ')
    print('''
    Step 1: Install pytorch by running this command in the terminal

        pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
    
    
    Step 2: Install chocolatey by running this command in powershell as admin
    
        Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))


    Step 3: Install ffmpeg by running this command in powershell
    
        choco install ffmpeg
        
        
    Step 4: Install Whisper AI by running this command in the terminal: 
    
        pip install -U openai-whisper 
    
    ''')
    input('Once you have done all this, press enter.\n\n')

    print('Transcribing all video content with Whisper AI.\n')
    transcribe_all_with_whisper()
    print('Done!')

else:
    pass
