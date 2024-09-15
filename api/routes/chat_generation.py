from flask import Blueprint, jsonify, request, Response, stream_with_context
import anthropic
import openai
import os
import json

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

    general_system_prompt = "You are an assistant that creates animations with Manim. Manim is a mathematical animation engine that is used to create videos programmatically. You are running on Animo (www.animo.video), a tool to create videos with Manim."

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
                    if isinstance(chunk, anthropic.types.MessageStartEvent):
                        continue
                    if isinstance(chunk, anthropic.types.ContentBlockStartEvent):
                        continue
                    if isinstance(chunk, anthropic.types.ContentBlockDeltaEvent):
                        content = chunk.delta.text
                        if content:
                            yield content
            except Exception as e:
                print(f"Error in Anthropic API call: {str(e)}")
                yield f"Error: {str(e)}"

        return Response(
            stream_with_context(generate()), content_type="text/event-stream"
        )

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
                    yield content

        return Response(
            stream_with_context(generate()), content_type="text/event-stream"
        )
