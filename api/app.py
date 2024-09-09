"""
GM (Generative Manim) API is licensed under the Apache License, Version 2.0
"""

import os
import time
import re
from subprocess import run, PIPE, Popen, CalledProcessError
import subprocess
import urllib.parse
import requests
from flask import Flask, jsonify, request, Response, url_for
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
import threading
from openai import OpenAI
import anthropic
from flask_cors import CORS
import sys
import traceback
import json
import shutil
from flask import request

load_dotenv()
app = Flask(__name__, static_folder="public", static_url_path="/public")
CORS(app)

USE_LOCAL_STORAGE = os.getenv("USE_LOCAL_STORAGE", "true") == "true"
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8080")


@app.route("/")
def hello_world():
    return "Generative Manim Processor"


@app.route("/generate-code", methods=["POST"])
def generate_code():
    body = request.json
    prompt_content = body.get("prompt", "")
    model = body.get("model", "gpt-4o")

    general_system_prompt = """
You are an assistant that knows about Manim. Manim is a mathematical animation engine that is used to create videos programmatically.

The following is an example of the code:
\`\`\`
from manim import *
from math import *

class GenScene(Scene):
def construct(self):
    c = Circle(color=BLUE)
    self.play(Create(c))

\`\`\`

# Rules
1. Always use GenScene as the class name, otherwise, the code will not work.
2. Always use self.play() to play the animation, otherwise, the code will not work.
3. Do not use text to explain the code, only the code.
4. Do not explain the code, only the code.
    """

    if model.startswith("claude-"):
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        messages = [{"role": "user", "content": prompt_content}]
        try:
            response = client.messages.create(
                model=model,
                max_tokens=1000,
                temperature=0.2,
                system=general_system_prompt,
                messages=messages,
            )

            # Extract the text content from the response
            code = "".join(block.text for block in response.content)

            return jsonify({"code": code})

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    else:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        messages = [
            {"role": "system", "content": general_system_prompt},
            {"role": "user", "content": prompt_content},
        ]

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
            )

            code = response.choices[0].message.content

            return jsonify({"code": code})

        except Exception as e:
            return jsonify({"error": str(e)}), 500


def upload_to_azure_storage(file_path: str, video_storage_file_name: str) -> str:
    """
    Uploads the video to Azure Blob Storage and returns the URL.
    """
    cloud_file_name = f"{video_storage_file_name}.mp4"

    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=cloud_file_name
    )

    # Upload the video file
    with open(file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)

    # Construct the URL of the uploaded blob
    blob_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{cloud_file_name}"
    return blob_url


def move_to_public_folder(file_path: str, video_storage_file_name: str, base_url: str | None = None) -> str:
    """
    Moves the video to the public folder and returns the URL.
    """
    public_folder = os.path.join(os.path.dirname(__file__), "public")
    os.makedirs(public_folder, exist_ok=True)

    new_file_name = f"{video_storage_file_name}.mp4"
    new_file_path = os.path.join(public_folder, new_file_name)

    shutil.move(file_path, new_file_path)

    # Use the provided base_url if available, otherwise fall back to BASE_URL
    url_base = base_url if base_url else BASE_URL
    video_url = f"{url_base.rstrip('/')}/public/{new_file_name}"
    return video_url


def get_frame_config(aspect_ratio):
    if aspect_ratio == "16:9":
        return (3840, 2160), 14.22
    elif aspect_ratio == "9:16":
        return (1080, 1920), 8.0
    elif aspect_ratio == "1:1":
        return (1080, 1080), 8.0
    else:
        return (3840, 2160), 14.22


@app.route("/code-to-video", methods=["POST"])
def code_to_video():
    with app.app_context():
        code = request.json.get("code")
        file_name = request.json.get("file_name")
        file_class = request.json.get("file_class")

        user_id = request.json.get("user_id", "anonymous")
        project_name = request.json.get("project_name")
        iteration = request.json.get("iteration")

        # Aspect Ratio can be: "16:9" (default), "1:1", "9:16"
        aspect_ratio = request.json.get("aspect_ratio")

        # Stream the percentage of animation it shown in the error
        stream = request.json.get("stream", False)

        video_storage_file_name = f"video-{user_id}-{project_name}-{iteration}"

        if not code:
            return jsonify(error="No code provided"), 400

        # Determine frame size and width based on aspect ratio
        frame_size, frame_width = get_frame_config(aspect_ratio)

        # Modify the Manim script to include configuration settings
        modified_code = f"""
from manim import *
from math import *
config.frame_size = {frame_size}
config.frame_width = {frame_width}

{code}
        """

        # Write the code to a file with the specified file_name
        if not file_name.endswith(".py"):
            file_name = f"{file_name}.py"
        with open(file_name, "w") as f:
            f.write(modified_code)

        def render_video():
            with app.app_context():
                try:
                    command_list = [
                        "manim",
                        file_name,
                        file_class,
                        "--format=mp4",
                        "--media_dir",
                        ".",
                        "--custom_folders",
                    ]

                    process = subprocess.Popen(
                        command_list,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=os.path.dirname(os.path.realpath(__file__)),
                        text=True,
                        bufsize=1,  # Ensure the output is in text mode and line-buffered
                    )
                    current_animation = -1
                    current_percentage = 0
                    error_output = []
                    in_error = False

                    while True:
                        output = process.stdout.readline()
                        error = process.stderr.readline()

                        if output == "" and error == "" and process.poll() is not None:
                            break

                        if output:
                            print("STDOUT:", output.strip())
                        if error:
                            print("STDERR:", error.strip())
                            error_output.append(error.strip())

                        # Check for start of error
                        if "Traceback (most recent call last)" in error:
                            in_error = True
                            continue

                        # If we're in an error state, keep accumulating the error message
                        if in_error:
                            if error.strip() == "":
                                # Empty line might indicate end of traceback
                                in_error = False
                                full_error = "\n".join(error_output)
                                yield f'{{"error": {json.dumps(full_error)}}}\n'
                                return
                            continue

                        animation_match = re.search(r"Animation (\d+):", error)
                        if animation_match:
                            new_animation = int(animation_match.group(1))
                            if new_animation != current_animation:
                                current_animation = new_animation
                                current_percentage = 0
                                yield f'{{"animationIndex": {current_animation}, "percentage": 0}}\n'

                        percentage_match = re.search(r"(\d+)%", error)
                        if percentage_match:
                            new_percentage = int(percentage_match.group(1))
                            if new_percentage != current_percentage:
                                current_percentage = new_percentage
                                yield f'{{"animationIndex": {current_animation}, "percentage": {current_percentage}}}\n'

                    if process.returncode == 0:
                        video_file_path = os.path.join(
                            f"{file_class or 'GenScene'}.mp4"
                        )
                        if USE_LOCAL_STORAGE:
                            # Pass request.host_url if available
                            base_url = (
                                request.host_url
                                if request and hasattr(request, "host_url")
                                else None
                            )
                            video_url = move_to_public_folder(
                                video_file_path, video_storage_file_name, base_url
                            )
                        else:
                            video_url = upload_to_azure_storage(
                                video_file_path, video_storage_file_name
                            )
                        print(f"Video URL: {video_url}")
                        if stream:
                            yield f'{{ "video_url": "{video_url}" }}\n'
                            sys.stdout.flush()
                        else:
                            yield {
                                "message": "Video generation completed",
                                "video_url": video_url,
                            }
                    else:
                        full_error = "\n".join(error_output)
                        yield f'{{"error": {json.dumps(full_error)}}}\n'

                except Exception as e:
                    print(f"Unexpected error: {str(e)}")
                    traceback.print_exc()
                    yield f'{{"error": "Unexpected error occurred: {str(e)}"}}\n'
                finally:
                    # Remove the temporary Python file
                    try:
                        if os.path.exists(file_name):
                            os.remove(file_name)
                            print(f"Removed temporary file: {file_name}")
                    except Exception as e:
                        print(f"Error removing temporary file {file_name}: {e}")

                    try:
                        if os.path.exists(file_name):
                            os.remove(file_name)
                            print(f"Removed temporary file: {file_name}")
                    except Exception as e:
                        print(f"Error removing temporary file {file_name}: {e}")

        if stream:
            # TODO: If the `render_video()` fails, or it's sending {"error"}, be sure to add `500`
            return Response(
                render_video(), content_type="text/event-stream", status=207
            )
        else:
            video_url = None
            try:
                for result in render_video():  # Iterate through the generator
                    print(f"Generated result: {result}")  # Debug print
                    if isinstance(result, dict):
                        if "video_url" in result:
                            video_url = result["video_url"]
                        elif "error" in result:
                            raise Exception(result["error"])

                if video_url:
                    return (
                        jsonify(
                            {
                                "message": "Video generation completed",
                                "video_url": video_url,
                            }
                        ),
                        200,
                    )
                else:
                    return (
                        jsonify(
                            {
                                "message": "Video generation completed, but no URL was found"
                            }
                        ),
                        200,
                    )
            except StopIteration:
                if video_url:
                    return (
                        jsonify(
                            {
                                "message": "Video generation completed",
                                "video_url": video_url,
                            }
                        ),
                        200,
                    )
                else:
                    return (
                        jsonify(
                            {
                                "message": "Video generation completed, but no URL was found"
                            }
                        ),
                        200,
                    )
            except Exception as e:
                print(f"Error in non-streaming mode: {e}")
                return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=False, host="0.0.0.0", port=port)
