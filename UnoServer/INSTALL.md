# INSTALL.md

Guía rápida (en español) para **clonar**, **instalar** y **lanzar** el servidor y el cliente de UNO. Incluye ejecución directa con Python y despliegue con Docker/Docker Compose.

---

## 1) Requisitos

* **Python 3.11+**
* (Opcional) **pipx/virtualenv** para aislar dependencias
* (Opcional) **Docker** y **Docker Compose** para despliegue en contenedores

---

## 2) Clonar el repositorio

```bash
git clone https://github.com/Augustelli/Uno-Web-Server.git
cd Uno-Web-Server
```

---

## 3) Variables de entorno (configuración)

Crea un archivo **`.env`** en la raíz o exporta estas variables en tu entorno. Valores sugeridos:

```ini
PORT=8000
MAX_PLAYERS=2
TURN_TIMEOUT=120
HOST=0.0.0.0
CARDS_NUMBER=2
LOG_DB_DSN=dbname=game_db user=postgres password=Sup3rSecret0 host=localhost port=5432
DB_TABLE_CREATION_QUERY="
CREATETABLE IF NOT EXISTS logs (
  id bigseria  created_at timestamptz NOT NULL DEFAULT now(),
  level text NOT NULL,
  logger_name text,
  process_name text,
  thread_name text,
  message text,
  game_id text,
  player_id text,
  extra jsonb
);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs (created_at DESC);
"
```

> Si no defines el `.env`, la app usa estos mismos **valores por defecto**.

---

## 4) Instalación (entorno Python)

### 4.1 Crear entorno virtual (opcional, recomendado)

```bash
python -m venv .venv
# Linux/Mac:
source .venv/bin/activate
# Windows (PowerShell):
# .\.venv\Scripts\Activate.ps1
```

### 4.2 Instalar dependencias

```bash
pip install -r requirements.txt
```

---

## 5) Ejecución con Python (desarrollo local)

En **dos terminales** distintas:

### Servidor

```bash
python3 src/server.py
```

Verás logs como “Escuchando en … / Servidor listo…”.

### Cliente (CLI)

```bash
python3 src/client.py
```

Sigue el menú interactivo para **listar**, **crear** o **unirte** a una partida.

> Puedes abrir **varias** terminales cliente para simular varios jugadores.

---

## 6) Despliegue con Docker / Docker Compose

### 6.1 Docker Compose (recomendado)

Desde la raíz del repo:

```bash
docker compose -f deployment/docker-compose.yaml up -d
```

Esto levantará los servicios definidos en `deployment/docker-compose.yaml` (e.g., servidor, y cualquier dependencia de logging si está incluida).

### 6.2 Construir imágenes manualmente

Desde la raíz del repo:

```bash
docker build -f deployment/Dockerfile.server -t ghcr.io/Augustelli/Uno-Web-Server:server-1 .
docker build -f deployment/Dockerfile.client -t ghcr.io/Augustelli/Uno-Web-Server:server-1 .
```

> **Nota:** normalmente se usarían **tags diferentes** para servidor y cliente (por ejemplo `:server-1` y `:client-1`).
> Si deseas diferenciarlas, puedes usar:
>
> ```bash
> docker build -f deployment/Dockerfile.server -t ghcr.io/Augustelli/Uno-Web-Server:server-1 .
> docker build -f deployment/Dockerfile.client -t ghcr.io/Augustelli/Uno-Web-Server:client-1 .
> ```

---

7) Usar Makefile (opcional)

Si tienes `make` instalado, puedes usar los siguientes comandos:
```bash

make run-server
make run-client:
make build
make run-docker-server
make run-docker-client
make run-docker-db
make setup
make clean

```