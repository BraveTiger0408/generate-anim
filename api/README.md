# 🔬 Generative Manim API (Animation Processing Interface)

The Animation Processing Interface or API is a REST API that can be used to generate Manim scripts using LLMs and render videos from Python code. This is the API used on [Generative Manim Demo](https://generative-manim.vercel.app/) and [Animo](https://animo.video) under the hood.

## 🚀 Concept

We are creating the software that enables you to transform ideas, concepts, and more into animated videos.

Generative Manim API (Animation Processing Interface) empowers you to generate Manim scripts using LLMs and render videos from Python code. This allows seamless integration into your website, app, or any kind of project that requires animations. Happy coding!

## 🤖 Animo

[Animo](https://animo.video) allows you to use this API as your own Animation Processing Interface. That way, you can have more control and flexibility over the animations you generate. To connect to your own server from Animo, set up this server, and enable **Use Local Server** in the **Settings** tab of your Animo project.

![Preview on Use Local Server](./../.github/use_local_server.png)

## 📦 Installation

### Prerequisites

Altough Docker is not required, it is recommended to make sure you have the necessary tools to render videos or to generate code.

- [Docker](https://www.docker.com/)
- [Docker Compose](https://docs.docker.com/compose/)

### Steps

1. **Clone the repository:**

```bash
git clone https://github.com/360macky/generative-manim.git
```

2. **Install the requirements on the `/api` directory:**

```bash
cd api
pip install -r requirements.txt
```

2. **Build the Docker image:**

```bash
docker build -t generative-manim-api .

```

3. **Run the Docker container:**

```bash
docker run -p 8080:8080 generative-manim-api
```

4. **Wohoo!** 🎉 Congratulations! You have the API running.

Now that you have the API running, you can use it to generate Manim scripts and render videos. Or you can interact with it using the [Animo](https://animo.video) platform. Remember to enable **Use Local Server** in the **Settings** tab of your Animo project. And when required, paste the HTTP URL to the API.
