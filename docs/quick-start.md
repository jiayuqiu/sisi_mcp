# Quick Start

## 1. Set Dify Platform

### 1.1 Clone repo

```bash
$ git clone https://github.com/langgenius/dify.git
$ git checkout -b release/e-1.11.4 origin/release/e-1.11.4
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

### 2.2 start up

```bash
$ docker compose up -d
```

### 2.3 import chatflow & workflow & custom tool

#### 2.3.1 Chatflow

![import config yaml](images/import_app_yaml.png)

- import config from `mcp_conductor/resources/dify/sisi_expert_chat.yml`
- import config from `mcp_conductor/resources/dify/sisi_expert_workflow.yml`

#### 2.3.2 Workflow

TODO

#### 2.3.3 custom tool

![click create custom tool](images/create_custom_tool_step_1.png)
![config tool](images/create_custom_tool_step_2.png)

- tool config files are under `mcp_conductor/resources/dify`

#### 2.3.5 Troble shoot

In this dify version, Node of custom tool might lose input parameters settings. so need to delete them and re-create.

- delete old nodes of custom tool
![re-create custom tool node](images/recreate_custom_tool_node_1.png)

- re-create node
![how to add node](images/create_custom_tool_step_2.png)

- setting `detectAnomaly node`
![detect anomaly node](images/detect_anomaly_setting.png)

- setting `analyzeAnomalyReason node`
![analyzeAnomalyReason node](images/anlyze_anomaly_reason.png)


## 3. Set frontend_nextjs

### 3.1 install nodejs

Please refer to `https://nodejs.org/en/download`

### 3.2 Set .env.local

```bash
$ cd frontend_nextjs
$ cp .env.local.example .env.local
$ vim .env.local

# replace DIFY_API_KEY with your api token
# The token is generated in Section $2
```

### 3.2 start frontend service

```
$ cd frontend_nextjs
$ npm install  # just for first run
$ npm run dev  # run in dev mode

## 4. Done

Browser http://localhost:3000 to chat with sisi-expert.
