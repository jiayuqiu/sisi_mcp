# Quick Start

## 1. Set Dify Platform

### 1.1 Clone repo

```bash
$ git clone https://github.com/langgenius/dify.git
```

### 1.2 docker compose up

```bash
$ cd docker
$ cp .env.example .env
```

### 1.3 Set docker compose project name

add `COMPOSE_PROJECT_NAME=sisi-dify-platform` into `.env`

### 1.4 start up

```bash
$ docker compose up -d
```

## 2. Set mcp & backend api service

### 2.1 Set dify token

![Map to api key](./images/tutorial_api_key_generation.png)

![generate key](./images/generate_key.png)

### 2.1 set .env

```bash
$ cd docker
$ cp .env.example .env
$ # Replace 3 tokens.
```

### 2.2 
