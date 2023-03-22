import streamlit as st
from manim import *
import openai

from utils import *

st.set_page_config(
  page_title="Generator",
  page_icon="👋",
)

st.title(":art: Generative Manim")
st.write(":robot_face: Create beautiful and quick animations with GPT-3.5. :sparkles:")

prompt = st.text_area("Write your animation idea here. Use simple words.", "Draw a blue circle and convert it to a red square", max_chars=240)

openai_api_key=""
openai_model=""

if st.checkbox("Use own Open API Key (optional)"):
  openai_api_key = st.text_input("Paste your own [Open API Key](https://platform.openai.com/account/api-keys)", value="", type="password")
  openai_model = st.selectbox("Select the GPT model. If you don't have access to GPT-4, select GPT-3.5-Turbo", ["GPT-3.5-Turbo", "GPT-4"])

generates_code = st.button(":computer: Animate :sparkles:", type="primary")
show_code = st.checkbox("Show generated code")

code_response = ""

if generates_code:

  if not openai_model:
    openai_model = "gpt-4"

  if not prompt:
    st.error("Error: Please write a prompt to generate the video.")
    st.stop()

  # If prompt is less than 10 characters, it will be rejected
  if len(prompt) < 10:
    st.error("Error: Your prompt is too short. Please write a longer prompt.")
    st.stop()

  # If prompt exceeds 240 characters, it will be truncated
  if len(prompt) > 240 and not openai_api_key:
    st.error("Error: Your prompt is longer than 240 characters. Please shorten it, or use your own API key.")
    st.stop()

  # Prompt must be trimmed of spaces at the beginning and end
  prompt = prompt.strip()

  # Remove ", ', \ characters
  prompt = prompt.replace('"', '')
  prompt = prompt.replace("'", "")
  prompt = prompt.replace("\\", "")

  # If user has their own API key, use it
  if not openai_api_key:
    openai.api_key = st.secrets["openai_api_key"]
  else:
    openai.api_key = openai_api_key

  response = openai.ChatCompletion.create(
      model=openai_model.lower(),
      messages=[{"role": "system", "content": "Write Manim scripts for animations in Python. Generate code, not text. Do not explain code. Do not add comments. Do not use other library than Manim. At the end use 'self.play' ```from manim import *\n\nclass GenScene(Scene):```\n  def construct(self):\n  # Write here"},
                {"role": "user", "content": f"New Animation Request: {prompt}"}],
      max_tokens=300
  )

  code_response = extract_code(response.choices[0].message.content)

  code_response = remove_indentation(extract_construct_code(code_response))

  if show_code:
    st.text_area(label="Code generated: ",
                 value=code_response,
                 key="code_input")

  class GenScene(Scene):
    def construct(self):
      exec(code_response)

  GenScene().render()
  try:
    st.video("media/videos/1080p60.0/GenScene.mp4")
  except FileNotFoundError:
    st.error("Error: I couldn't find the generated video file. I know this is a bug and I'm working on it. Please reload the page.")
  except:
    st.error("Error: Something went wrong processing your prompt. Please reload the page.")

st.write('Made with :heart: by [Marcelo](https://github.com/360macky).')
st.write('[Source code](https://github.com/360macky/generative-manim) - [Report a bug](https://github.com/360macky/generative-manim/issues/new) - [Twitter](https://twitter.com/360macky) - [OpenAI Profile](https://community.openai.com/u/360macky/summary)')
