import os
import pytesseract
from PIL import Image
from googlesearch import search
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from concurrent.futures import ThreadPoolExecutor
import threading
import nest_asyncio
import requests
import json
import subprocess
import concurrent
import weave



weave.init("answer_engine")

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Set default download folder for screenshots
videos_folder = r"./download"

# Clear the download folder
if os.path.exists(videos_folder):
    for file in os.listdir(videos_folder):
        file_path = os.path.join(videos_folder, file)
        if os.path.isfile(file_path) or os.path.islink(file_path):
            os.unlink(file_path)
else:
    os.makedirs(videos_folder)

# Global stop event
stop_flag = threading.Event()

class Search:
        
    @staticmethod
    def get_search_results(query, num_results=5):
        return [url for url in search(query, num_results=num_results)]
    @staticmethod
    async def download_screenshot(url, delay, index):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            file_name = f'{videos_folder}/Screenshot_{index}.png'
            try:
                await asyncio.wait_for(page.goto(url), timeout=5)
                await page.set_viewport_size({"width": 1920, "height": 1080})
                await page.wait_for_timeout(delay * 1000)
                await page.screenshot(path=file_name, full_page=True)
                print(f"Screenshot saved as {file_name}!")
            except (PlaywrightTimeoutError, asyncio.TimeoutError):
                print(f"Timeout occurred while loading {url}")
                file_name = None
            except Exception as e:
                print(f"Unexpected error occurred: {e}")
                file_name = None
            finally:
                await browser.close()
            return file_name

    @staticmethod
    def process_urls(urls, delay):
        if os.path.exists(videos_folder):
            for file in os.listdir(videos_folder):
                file_path = os.path.join(videos_folder, file)
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    os.rmdir(file_path)
        async def _process_urls():
            tasks = [Search.download_screenshot(url, delay, index) for index, url in enumerate(urls)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(_process_urls())
        return results

    @staticmethod
    def perform_ocr(image_path):
        if image_path is None:
            return None
        img = Image.open(image_path)
        tesseract_text = pytesseract.image_to_string(img)
        print(f"Tesseract OCR text for {image_path}:")
        print(tesseract_text)
        return tesseract_text

    @staticmethod
    def ocr_results_from_screenshots(screenshots):
        ocr_results = []
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(Search.perform_ocr, screenshot) for screenshot in screenshots]
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    ocr_results.append(result)
                except Exception as e:
                    print(f"An error occurred during OCR processing: {e}")
        return ocr_results

    @staticmethod
    def get_context_from_ocr_results():
        screenshots = [os.path.join(videos_folder, f) for f in os.listdir(videos_folder) if os.path.isfile(os.path.join(videos_folder, f))]

        if not screenshots:
            print("No valid screenshots to process.")
            return None

        # Perform OCR on downloaded screenshots and prepare the context
        ocr_results = Search.ocr_results_from_screenshots(screenshots)
        ocr_results = [val[:1000] for val in ocr_results if isinstance(val, str)]
        context = " ".join(ocr_results)[:3000]
        return context


    @staticmethod
    def decide_search(query):
        # Instantiate the model to decide if a web search is needed
        model = Model(endpoint="us-central1-aiplatform.googleapis.com", region="us-central1", project_id="dsports-6ab79")
        context = ""
        res = model.query_model_for_search_decision(query)
        return res


class Model:
    def __init__(self, endpoint, region, project_id):
        self.endpoint = endpoint
        self.region = region
        self.project_id = project_id

    def get_access_token(self):
        return subprocess.check_output("gcloud auth print-access-token", shell=True).decode('utf-8').strip()

    def query_model(self, query, context):
        if context != "":
            q = "Answer the question {}. You can use this as help: {}".format(query, context)
        else: 
            q = query
        access_token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "meta/llama3-405b-instruct-maas",
            "stream": True,
            "messages": [
                {
                    "role": "user",
                    "content": q
                }
            ]
        }
        url = f"https://{self.endpoint}/v1beta1/projects/{self.project_id}/locations/{self.region}/endpoints/openapi/chat/completions"
        response = requests.post(url, headers=headers, json=data, stream=True)

        with open("response.txt", "w") as f:
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        try:
                            data = line.decode('utf-8').strip()
                            if data.startswith("data: "):
                                data_json = json.loads(data[6:])
                                if "choices" in data_json and len(data_json["choices"]) > 0:
                                    delta_content = data_json["choices"][0]["delta"].get("content", "")
                                    if delta_content:
                                        f.write(delta_content + "\n")
                        except json.JSONDecodeError:
                            continue
            else:
                f.write(f"Error: {response.status_code}\n")
                f.write(response.text + "\n")



    @weave.op()
    def query_model_non_stream(self, query, context):
        if context != "":
            q = "Answer the question {}. You can use this as help: {}".format(query, context)
        else: 
            q = query

        access_token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "meta/llama3-405b-instruct-maas",
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": q
                }
            ]
        }
        url = f"https://{self.endpoint}/v1beta1/projects/{self.project_id}/locations/{self.region}/endpoints/openapi/chat/completions"
        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 200:
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                res = data["choices"][0]["message"]["content"]
                return res
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return ""


    @weave.op()
    def query_model_for_search_decision(self, query):
        access_token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "meta/llama3-405b-instruct-maas",
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": f"Do we need a web search to answer the question: {query}? usually questions that are asking about time related details or new inforamtion that might be in you initial training set will require a web search. Also information that could be subject to change is also a good to double check with search. Respond with 'yes' or 'no'."
                }
            ]
        }
        url = f"https://{self.endpoint}/v1beta1/projects/{self.project_id}/locations/{self.region}/endpoints/openapi/chat/completions"
        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 200:
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                decision = data["choices"][0]["message"]["content"].strip().lower()
                return 'yes' in decision
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return False 