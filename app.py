
import os
import threading
import nest_asyncio
import asyncio
from flask import Flask, request, render_template, jsonify
from logic import Search, Model

# Project configuration
PROJECT_ID = "your poject id"
API_ENDPOINT = "us-central1-aiplatform.googleapis.com"
REGION = "us-central1"

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

# Global variable for response storage
response_storage = ""

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    global response_storage
    query = request.form.get('query')
    delay = 1

    # Clear the stop flag before running the function
    stop_flag.clear()

    asyncio.run(run_search_and_ocr(query, delay))
    return jsonify({'status': 'Search started'})

async def run_search_and_ocr(query, delay):
    global response_storage
    context = ""
    if Search.decide_search(query):
        urls = Search.get_search_results(query, num_results=20)
        process_thread = threading.Thread(target=Search.process_urls, args=(urls, delay))
        process_thread.start()
        await asyncio.sleep(15)
        stop_flag.set()
        if process_thread.is_alive():
            process_thread.join(timeout=0)

        context = Search.get_context_from_ocr_results()

    model = Model(endpoint=API_ENDPOINT, region=REGION, project_id=PROJECT_ID)
    response = model.query_model_non_stream(query, context)  # Replaced with query_model_nonstream to just return the response
    response_storage = response


@app.route('/results', methods=['GET'])
def get_results():
    global response_storage
    return jsonify({'results': response_storage.splitlines()})

if __name__ == "__main__":
    app.run(debug=True)
