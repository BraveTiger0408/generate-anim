from flask import Blueprint, jsonify, request, Response, stream_with_context
import anthropic
import openai
import os
import json
import subprocess
import shutil
import string
import random
import re
import base64
from api.prompts.manimDocs import manimDocs
from azure.storage.blob import BlobServiceClient
from PIL import Image
import io
import time
from openai import APIError

chat_generation_bp = Blueprint("chat_generation", __name__)


animo_functions = {
    "openai": [
        {
            "name": "get_preview",
            "description": "Get a preview of the video animation before generating it. Use this function always, before giving the final code to the user.And use it to generate frames of the video, so you can improve it over time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The code to get the preview of",
                    },
                    "class_name": {
                        "type": "string",
                        "description": "The name of the class to get the preview of",
                    }
                },
                "required": ["code", "class_name"],
            },
            "output": {"type": "string", "description": "Images URLs of the animation that will be inserted in the conversation"},
        }
    ],
    "anthropic": [
        # TODO: Add Anthropic-version functions
    ]
}


@chat_generation_bp.route("/v1/chat/generation", methods=["POST"])
def generate_code_chat():
    """
    This endpoint generates code for animations using OpenAI or Anthropic.
    It supports both OpenAI and Anthropic models and returns a stream of content.
    
    When calling this endpoint, enable `is_for_platform` to interact with the platform 'Animo'.
    """
    print("Received request for /v1/chat/generation")

    data = request.json
    print(f"Request data: {json.dumps(data, indent=2)}")

    messages = data.get("messages", [])
    global_prompt = data.get("globalPrompt", "")
    user_id = data.get("userId", "")
    scenes = data.get("scenes", [])
    project_title = data.get("projectTitle", "")
    engine = data.get("engine", "openai")
    selected_scenes = data.get("selectedScenes", [])
    is_for_platform = data.get("isForPlatform", False)
    
    print("messages")
    print(messages)

    general_system_prompt = """You are an assistant that creates animations with Manim. Manim is a mathematical animation engine that is used to create videos programmatically. You are running on Animo (www.animo.video), a tool to create videos with Manim.

# What the user can do?

The user can create a new project, add scenes, and generate the video. You can help the user to generate the video by creating the code for the scenes. The user can add custom rules for you, can select a different aspect ratio, and can change the model (from OpenAI GPT-4o to Anthropic Claude 3.5 Sonnet).

# Behavior Context

The user will ask you to generatte an animation, you should iterate while using the `get_preview` function. This function will generate a preview of the animation, and will be inserted in the conversation so you can see the frames of it, and enhance it across the time. You can make this iteration up to 4 times without user confirmation. Just use the `get_preview` until you are sure that the animation is ready.

FAQ
**Should the assistant generate the code first and then use the `get_preview` function?**
No, unless the user asks for it. Always use the `get_preview` function to generate the code. The user will see the code anyway, so there is no need to duplicate the work. Use the `get_preview` as your way to quickly draft the code and then iterate on it.

**Can the user see the code generated?**
Yes, even if you use the `get_preview` function, the code will be generated and visible for the user.

**Can the assistant propose a more efficient way to generate the animation?**
Yes, the assistant can propose a more efficient way to generate the animation. For example, the assistant can propose a different aspect ratio, a different model, or a different scene. If the change is too big, you should ask the user for confirmation. Act with initiative.

# Code Context

The following is an example of the code:
\`\`\`
from manim import *
from math import *

class GenScene(Scene):
  def construct(self):
      # Create a circle of color BLUE
      c = Circle(color=BLUE)
      # Play the animation of creating the circle
      self.play(Create(c))

\`\`\`

## Rules of programming

1. Always use comments to explain the next line of the code:

\`\`\`
# Create a sphere of color BLUE for the Earth
earth = Sphere(radius=1, checkerboard_colors=[BLUE_D, BLUE_E])
\`\`\`

This is needed to understand what you meant to do.

2. You can use TODO comments to mark places that you think can be improved, and you can come back later to them.

\`\`\`
# TODO: Add more colors to the cube later
\`\`\`

This is needed to understand what you could have done better.

3. Everytime there is a movement on the camera or on the objects, you should add a comment resalting the desired movement

\`\`\`
# With this movement we should see the difference between the both buildings
self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)
\`\`\`

This is needed to understand what you meant to reflect on the camera.

4. Unless described on this system prompt, always assume the user is not providing any image to you. That means, you should not use, for example:

\`\`\`
# Create a 3D grid of spheres
new_texture = "assets/random_texture.jpg"
\`\`\`

If `random_texture.jpg` is not provided, you should not use it. Otherwise the video will not work on the platform.

# Manim Library
{manimDocs}
"""

    messages.insert(0, {"role": "system", "content": general_system_prompt})

    if engine == "anthropic":
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        def convert_message_for_anthropic(message):
            if isinstance(message["content"], list):
                content = []
                for part in message["content"]:
                    if part.get("type") == "image_url":
                        content.append(
                            {"type": "image", "image": part["image_url"]["url"]}
                        )
                    else:
                        content.append(part)
                message["content"] = content
            return message

        # Extract system message and remove it from the messages list
        system_message = next(
            (msg["content"] for msg in messages if msg["role"] == "system"), None
        )
        anthropic_messages = [
            convert_message_for_anthropic(msg)
            for msg in messages
            if msg["role"] != "system"
        ]

        def generate():
            try:
                stream = client.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    messages=anthropic_messages,
                    system=system_message,
                    max_tokens=1000,
                    stream=True,
                )
                for chunk in stream:
                    if isinstance(chunk, anthropic.types.ContentBlockDeltaEvent):
                        content = chunk.delta.text
                        if content:
                            if is_for_platform:
                                for char in content:
                                    escaped_char = repr(char)[1:-1]
                                    yield f'0:"{escaped_char}"\n'
                            else:
                                yield content
            except Exception as e:
                print(f"Error in Anthropic API call: {str(e)}")
                error_message = f'0:"{escaped_char}"\n' if is_for_platform else f"Error: {str(e)}"
                yield error_message

        response = Response(stream_with_context(generate()), content_type="text/plain; charset=utf-8" if is_for_platform else "text/event-stream")
        if is_for_platform:
            response.headers['Transfer-Encoding'] = 'chunked'
            response.headers['x-vercel-ai-data-stream'] = 'v1'
        return response

    else:
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        
        def get_preview(code: str, class_name: str):
            """
            get_preview is a function that generates PNGs frames from a Manim script animation.
            
            IMPORTANT: This version of the function will only work for OpenAI models.
            """
            
            print("Generating preview")

            # Get the absolute path of the current script (in api/routes)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            api_dir = os.path.dirname(current_dir)  # This should be the /api directory
            
            # Create the temporary directory inside /api
            temp_dir = os.path.join(api_dir, "temp_manim")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Create the Python file in the temporary location
            file_name = f"{class_name}.py"
            file_path = os.path.join(temp_dir, file_name)
            with open(file_path, "w") as f:
                f.write(code)
            
            # Run the Manim command
            command = f"manim {file_path} {class_name} --format=png --media_dir {temp_dir} --custom_folders -pql --disable_caching"
            try:
                result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
                
                print(f"Result: {result}")
                
                # Create the previews directory if it doesn't exist
                previews_dir = os.path.join(api_dir, "public", "previews")
                os.makedirs(previews_dir, exist_ok=True)

                # Generate a random string for the subfolder
                random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
                
                # Move the generated PNGs to the previews directory
                source_dir = temp_dir
                destination_dir = os.path.join(previews_dir, random_string, class_name)
                
                # Find all PNG files in the source directory
                png_files = [f for f in os.listdir(source_dir) if f.endswith('.png')]
                
                if png_files:
                    os.makedirs(destination_dir, exist_ok=True)
                    image_list = []
                    for png_file in png_files:
                        shutil.move(os.path.join(source_dir, png_file), os.path.join(destination_dir, png_file))
                        # Extract the index from the filename
                        match = re.search(r'(\d+)\.png$', png_file)
                        if match:
                            index = int(match.group(1))
                            if index % 4 == 0:  # Only include frames where index is divisible by 5
                                image_path = os.path.join(destination_dir, png_file)
                                with Image.open(image_path) as img:
                                    # Calculate new dimensions (half the original size)
                                    width, height = img.size
                                    new_width = width // 4
                                    new_height = height // 4
                                    # Resize the image
                                    resized_img = img.resize((new_width, new_height), Image.LANCZOS)
                                    # Save the resized image to a bytes buffer
                                    buffer = io.BytesIO()
                                    resized_img.save(buffer, format="PNG")
                                    # Get the base64 encoding of the resized image
                                    base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
                                image_list.append({
                                    "path": image_path,
                                    "index": index,
                                    "base64": base64_image
                                })
                    image_list.sort(key=lambda x: x["index"])
                    return json.dumps({
                        "message": f"PNGs Preview generated successfully and moved to {destination_dir}",
                        "images": image_list
                    })
                else:
                    print(f"No PNG files found in: {source_dir}")
                    return json.dumps({
                        "error": f"No preview files generated at expected location: {source_dir}",
                        "images": []
                    })
            except subprocess.CalledProcessError as e:
                error_output = e.stdout + e.stderr
                print(f"Error running Manim command: {str(e)}")
                print(f"Command output:\n{error_output}")
                return json.dumps({
                    "error": f"ERROR. Error generating preview, please think on what could be the problem, and use `get_preview` to run the code again: {str(e)}\nCommand output:\n{error_output}",
                    "images": []
                })
            except Exception as e:
                print(f"Unexpected error: {str(e)}")
                return json.dumps({
                    "error": f"Unexpected error: {str(e)}",
                    "images": []
                })

        def generate():
            max_retries = 3
            retry_delay = 4  # seconds

            while True:
                for attempt in range(max_retries):
                    try:
                        stream = client.chat.completions.create(
                            model="gpt-4o",
                            messages=messages,
                            stream=True,
                            functions=animo_functions["openai"],
                            function_call="auto",
                        )
                        function_call_data = ""
                        function_name = ""
                        for chunk in stream:
                            if chunk.choices[0].delta.content:
                                content = chunk.choices[0].delta.content
                                if is_for_platform:
                                    for char in content:
                                        escaped_char = repr(char)[1:-1]
                                        yield f'0:"{escaped_char}"\n'
                                else:
                                    yield content
                            elif chunk.choices[0].delta.function_call:
                                function_call = chunk.choices[0].delta.function_call
                                if function_call.name:
                                    function_name = function_call.name
                                if function_call.arguments:
                                    function_call_data += function_call.arguments
                                    if is_for_platform:
                                        for char in function_call.arguments:
                                            escaped_char = repr(char)[1:-1]
                                            yield f'0:"{escaped_char}"\n'
                                    else:
                                        yield function_call.arguments
                        
                        # If we get here, the stream completed successfully
                        break
                    
                    except APIError as e:
                        if attempt < max_retries - 1:
                            print(f"APIError occurred: {str(e)}. Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                        else:
                            print(f"Max retries reached. APIError: {str(e)}")
                            yield json.dumps({"error": "Max retries reached due to API errors"})
                            return  # Exit the generator

                if function_call_data:
                    # Add the function call to messages
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "function_call": {
                            "name": function_name,
                            "arguments": function_call_data
                        }
                    })

                    # Yield the whole object back to the frontend
                    function_call_obj = json.dumps({
                        "role": "assistant",
                        "content": None,
                        "function_call": {
                            "name": function_name,
                            "arguments": function_call_data
                        }
                    })
                    if is_for_platform:
                        for char in function_call_obj:
                            escaped_char = repr(char)[1:-1]
                            yield f'0:"{escaped_char}"\n'
                    else:
                        yield function_call_obj

                    # Actually call get_preview
                    if function_name == "get_preview":
                        print(f"Calling get_preview with data: {function_call_data}")
                        args = json.loads(function_call_data)
                        result = get_preview(args['code'], args['class_name'])
                        result_json = json.loads(result)
                        function_response = {
                            "content": result_json.get("message", result_json.get("error")),
                            "name": "get_preview",
                            "role": "function"
                        }
                        messages.append(function_response)

                        # Yield the function response back to the frontend
                        function_response_obj = json.dumps(function_response)
                        if is_for_platform:
                            for char in function_response_obj:
                                escaped_char = repr(char)[1:-1]
                                yield f'0:"{escaped_char}"\n'
                        else:
                            yield function_response_obj

                        # Only create and send image_message if there are images
                        if result_json.get("images"):
                            # Create a new message with the images
                            image_message = {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "SUCCESS! These are the frames of the animation you generated. Please check all the frames and follow the rules: Text should not be overlapping, the space should be used efficiently, use different colors to represent different objects, plus other improvements you can think of. Remember to use the `get_preview` function to generate the code and iterate on it."
                                    }
                                ]
                            }
                            for image in result_json["images"]:
                                image_message["content"].append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image['base64']}"
                                    }
                                })
                            messages.append(image_message)

                            # Yield the image message back to the frontend
                            image_message_obj = json.dumps(image_message)
                            if is_for_platform:
                                for char in image_message_obj:
                                    escaped_char = repr(char)[1:-1]
                                    yield f'0:"{escaped_char}"\n'
                            else:
                                yield image_message_obj

                        # Trigger a new response from the assistant
                        continue  # This will start a new iteration of the while loop
                    else:
                        break  # Exit the loop if it's not a get_preview function call
                else:
                    break  # Exit the loop if there's no function call

            # Final message when there are no more function calls
            final_message = ""
            if is_for_platform:
                for char in final_message:
                    escaped_char = repr(char)[1:-1]
                    yield f'0:"{escaped_char}"\n'
            else:
                yield final_message

        print("Generating response")
        response = Response(stream_with_context(generate()), content_type="text/plain; charset=utf-8" if is_for_platform else "text/event-stream")
        if is_for_platform:
            response.headers['Transfer-Encoding'] = 'chunked'
            response.headers['x-vercel-ai-data-stream'] = 'v1'
        return response
