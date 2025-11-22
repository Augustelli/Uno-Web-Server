# Instalación y despliegue

## Prerrequisitos
- Sistema: Linux
- `python` 3.11+ y `pip`
- `docker` y `docker-compose` (opcional)
- Acceso al repositorio (rama `develop`)

## Estructura recomendada
Asegúrate de que el contexto de build contenga al menos:
- `requirements.txt`
- `src/` (contiene `client.py`, `config.py`, demás módulos)
- `deployment/Dockerfile.client`
- `.env.example`

Ejemplo:
- `requirements.txt`
- `src/client.py`
- `src/config.py`
- `deployment/Dockerfile.client`
- `.env` (local, no en repo)

## Pasos para desarrollo local
1. Crear y activar virtualenv:
\`\`\`bash
python3 -m venv .venv
source .venv/bin/activate
\`\`\`
2. Instalar dependencias:
\`\`\`bash
pip install -r requirements.txt
\`\`\`
3. Crear archivo de entorno:
\`\`\`bash
cp .env.example .env
# editar .env según necesidad (PORT, HOST, MAX_PLAYERS, TURN_TIMEOUT, CARDS_NUMBER)
\`\`\`
4. Ejecutar la aplicación cliente (ejemplo):
\`\`\`bash
python src/client.py
\`\`\`

Nota: el proyecto puede usar `python-dotenv` en `src/config.py` para cargar `.env`.

## Construir y ejecutar con Docker (cliente)
1. Desde la raíz del repositorio (muy importante, el contexto de build debe incluir `src/` y `requirements.txt`):
\`\`\`bash
docker build -f deployment/Dockerfile.client -t uno-client:latest .
\`\`\`
2. Ejecutar con archivo de entorno:
\`\`\`bash
docker run --env-file .env -it --rm --name uno-client uno-client:latest
\`\`\`

Si expones puertos, usa `-p HOST_PORT:CONTAINER_PORT` o variables del `.env`.

## Nota sobre el error de `COPY ../src/config.py /app`
Error típico:
\`\`\`
failed to compute cache key: "/src/config.py": not found
\`\`\`
Causa: Docker solo puede copiar archivos dentro del *build context*; usar `..` sale del contexto y falla. Solución:
- Ejecutar `docker build` desde la raíz del repo (donde están `requirements.txt` y `src/`).
- En el `Dockerfile` usar rutas dentro del contexto, por ejemplo:
\`\`\`dockerfile
COPY requirements.txt /app/requirements.txt
COPY src/ /app/
\`\`\`
No usar `COPY ../...`.

## Buenas prácticas
- No incluir `.env` en el repositorio; añadir `\`.env\`` a ` .gitignore`.
- Mantener ` .env.example\`` con las variables necesarias.
- No "hornear" secretos en la imagen; pasar variables en tiempo de ejecución con `--env-file` o `docker-compose`.
- Si el cliente y servidor necesitan imágenes separadas, crear `deployment/Dockerfile.server` y `deployment/Dockerfile.client` y construir ambas desde la raíz.

## Despliegue con docker-compose (opcional)
Ejemplo mínimo en `docker-compose.yml` (colocarlo en la raíz):
\`\`\`yaml
version: "3.8"
services:
  client:
    build:
      context: .
      dockerfile: deployment/Dockerfile.client
    env_file:
      - .env
    ports:
      - "${PORT}:${PORT}"
\`\`\`
Ejecutar:
\`\`\`bash
docker compose up --build
\`\`\`

## Troubleshooting rápido
- Si `COPY` falla: verificar ruta y contexto (ejecutar `pwd` antes de `docker build`).
- Si falta dependencia: verificar `requirements.txt` y `pip install`.
- Logs del contenedor: `docker logs -f uno-client`

Fin.