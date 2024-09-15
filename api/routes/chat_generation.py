from flask import Blueprint, jsonify, request, Response, stream_with_context
import anthropic
import openai
import os
import json
from api.prompts.manimDocs import manimDocs

chat_generation_bp = Blueprint("chat_generation", __name__)


@chat_generation_bp.route("/v1/chat/generation", methods=["POST"])
def generate_code_chat():
    """
    This endpoint generates code for animations using OpenAI or Anthropic.
    It supports both OpenAI and Anthropic models and returns a stream of content.
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

    general_system_prompt = """You are an assistant that creates animations with Manim. Manim is a mathematical animation engine that is used to create videos programmatically. You are running on Animo (www.animo.video), a tool to create videos with Manim.

# What the user can do?

The user can create a new project, add scenes, and generate the video. You can help the user to generate the video by creating the code for the scenes. The user can add custom rules for you, can select a different aspect ratio, and can change the model (from OpenAI GPT-4o to Anthropic Claude 3.5 Sonnet).

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
                error_message = f'0:"Error: {str(e)}"\n' if is_for_platform else f"Error: {str(e)}"
                yield error_message

        response = Response(stream_with_context(generate()), content_type="text/plain; charset=utf-8" if is_for_platform else "text/event-stream")
        if is_for_platform:
            response.headers['Transfer-Encoding'] = 'chunked'
        return response

    else:
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        def generate():
            stream = client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    if is_for_platform:
                        for char in content:
                            escaped_char = repr(char)[1:-1]
                            yield f'0:"{escaped_char}"\n'
                    else:
                        yield content

        response = Response(stream_with_context(generate()), content_type="text/plain; charset=utf-8" if is_for_platform else "text/event-stream")
        if is_for_platform:
            response.headers['Transfer-Encoding'] = 'chunked'
        return response
