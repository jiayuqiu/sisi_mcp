1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) Done
2. Clone & start **Dify** platform (Section 1) Done
3. Start up Dify platform
    Change prompt: 
    ```
    load `dify/docker/.env`, change the TRIGGER_URL to http://localhost:7080. Make the corresponding changes as well.
    ```

    Validation prompt:
    ```
    1. load `dify/docker/.env`. check list:
        - TRIGGER_URL should be http://localhost:7080
        - EXPOSE_NGINX_PORT should be 7080
    2. load `./.env`. check list:
        - DIFY_CHATFLOW_URL should be "http://localhost:7080/v1"
    ```
4. set Tools or MCP in dify
    - Set up custom tools
    - import DSL into dify studio
5. Generate a **Dify API key**
6. Fill in `sisimcp/.env` with your API keys
7. Run `docker compose up -d` inside `sisimcp/docker/`
8. Run backfill to run whole work flow.
   - command: `uv run python mcp_conductor/entry/main_backfill.py --start-date 2026-06-29 --end-date 2026-07-08 --sleep 1 --require-sync-data
`

Backup:
3. Generate a **Dify API key** (Section 2.1) 
4. Fill in `sisimcp/.env` with your API keys (Section 2.2) 
5. Run `docker compose up -d` inside `sisimcp/docker/` (Section 2.3) 
6. Import chatflow & workflow YAML files into Dify (Section 2.4) 
7. Open **http://localhost:3000** in your browser (Section 3) 