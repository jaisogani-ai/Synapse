// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * `backend.scaffold_api` — full project scaffolders.
 *
 * Each scaffolder returns a complete, runnable starter project for one
 * framework, with the requested database driver, features, and deployment
 * target wired in. The output is plain {@link GeneratedFile}s that the caller
 * writes to disk verbatim; nothing here touches the filesystem.
 */

import type {
  Database,
  Deployment,
  Feature,
  Framework,
  GeneratedFile,
  Scaffold,
} from "./types.ts";

/** Options for {@link scaffoldApi}. */
export interface ScaffoldOptions {
  framework: Framework;
  /** Project name (used in package.json, README, etc.). */
  name?: string;
  features?: Feature[];
  database?: Database;
  deployment?: Deployment;
}

const DEFAULTS = {
  name: "synapse-app",
  features: [] as Feature[],
  database: "postgres" as Database,
  deployment: "docker" as Deployment,
};

/** Build a full backend scaffold for the requested framework. */
export function scaffoldApi(options: ScaffoldOptions): Scaffold {
  const cfg = { ...DEFAULTS, ...options };
  const features = cfg.features;
  const includeAuth = features.includes("auth");
  const includeRateLimit = features.includes("rate_limit");
  const includeWs = features.includes("websockets");
  const includeQueues = features.includes("queues");

  switch (cfg.framework) {
    case "fastapi":
      return fastapiScaffold(cfg.name, cfg.database, cfg.deployment, {
        includeAuth,
        includeRateLimit,
        includeWs,
        includeQueues,
      });
    case "express":
      return expressScaffold(cfg.name, cfg.database, cfg.deployment, {
        includeAuth,
        includeRateLimit,
        includeWs,
        includeQueues,
      });
    case "nestjs":
      return nestjsScaffold(cfg.name, cfg.database, cfg.deployment);
    case "django":
      return djangoScaffold(cfg.name, cfg.database, cfg.deployment);
    case "go-gin":
      return goGinScaffold(cfg.name, cfg.database, cfg.deployment);
    case "go-fiber":
      return goFiberScaffold(cfg.name, cfg.database, cfg.deployment);
  }
}

interface FeatureFlags {
  includeAuth: boolean;
  includeRateLimit: boolean;
  includeWs: boolean;
  includeQueues: boolean;
}

// ---- FastAPI --------------------------------------------------------------

function fastapiScaffold(
  name: string,
  db: Database,
  deployment: Deployment,
  flags: FeatureFlags,
): Scaffold {
  const dbUrlEnv = dbUrlExample(db);
  const requirements = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.6",
    "pydantic-settings>=2.5",
  ];
  if (db !== "sqlite") requirements.push("sqlalchemy>=2.0", "asyncpg>=0.29");
  if (db === "mongodb") requirements.push("motor>=3.5");
  if (flags.includeAuth) requirements.push("python-jose[cryptography]>=3.3", "passlib[bcrypt]>=1.7");
  if (flags.includeRateLimit) requirements.push("slowapi>=0.1.9");
  if (flags.includeQueues) requirements.push("redis>=5.0", "rq>=1.16");

  const main = `# SPDX-License-Identifier: Apache-2.0
"""FastAPI entrypoint for ${name}."""

from __future__ import annotations

from fastapi import FastAPI
${flags.includeRateLimit ? "from slowapi import Limiter\nfrom slowapi.util import get_remote_address\n" : ""}
${flags.includeAuth ? "from app.routes.auth import router as auth_router\n" : ""}
from app.routes.health import router as health_router
${flags.includeWs ? "from app.routes.ws import router as ws_router\n" : ""}
from app.settings import settings

app = FastAPI(title="${name}", version="0.1.0")
${flags.includeRateLimit ? 'limiter = Limiter(key_func=get_remote_address)\napp.state.limiter = limiter\n' : ""}
app.include_router(health_router)
${flags.includeAuth ? "app.include_router(auth_router, prefix='/auth', tags=['auth'])\n" : ""}${flags.includeWs ? "app.include_router(ws_router)\n" : ""}

@app.on_event("startup")
async def on_startup() -> None:
    """Verify config is sane before serving traffic."""
    assert settings.database_url, "DATABASE_URL must be set"
`;

  const settings = `# SPDX-License-Identifier: Apache-2.0
"""Typed app settings (pydantic-settings)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from environment / .env."""

    database_url: str = "${dbUrlEnv}"
    secret_key: str = "change-me"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
`;

  const healthRoute = `# SPDX-License-Identifier: Apache-2.0
"""Health endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
`;

  const files: GeneratedFile[] = [
    { path: "app/__init__.py", contents: "" },
    { path: "app/main.py", contents: main },
    { path: "app/settings.py", contents: settings },
    { path: "app/routes/__init__.py", contents: "" },
    { path: "app/routes/health.py", contents: healthRoute },
    { path: "requirements.txt", contents: requirements.join("\n") + "\n" },
    {
      path: ".env.example",
      contents: `DATABASE_URL=${dbUrlEnv}\nSECRET_KEY=change-me\n`,
    },
    {
      path: "README.md",
      contents: `# ${name}\n\nFastAPI scaffold generated by Synapse Backend Architect.\n\n\`\`\`bash\npython -m venv .venv && . .venv/bin/activate\npip install -r requirements.txt\nuvicorn app.main:app --reload\n\`\`\`\n`,
    },
  ];

  if (flags.includeAuth) {
    files.push({
      path: "app/routes/auth.py",
      contents: `# SPDX-License-Identifier: Apache-2.0
"""JWT auth router."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from jose import jwt
from pydantic import BaseModel

from app.settings import settings

router = APIRouter()


class TokenRequest(BaseModel):
    """Login payload."""

    username: str
    password: str


@router.post("/token")
async def issue_token(req: TokenRequest) -> dict[str, str]:
    """Issue a short-lived JWT."""
    if not req.username or not req.password:
        raise HTTPException(status_code=400, detail="missing credentials")
    payload = {
        "sub": req.username,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer"}
`,
    });
  }

  if (flags.includeWs) {
    files.push({
      path: "app/routes/ws.py",
      contents: `# SPDX-License-Identifier: Apache-2.0
"""WebSocket echo route."""
from fastapi import APIRouter, WebSocket

router = APIRouter()


@router.websocket("/ws")
async def echo(socket: WebSocket) -> None:
    """Echo incoming messages back to the client."""
    await socket.accept()
    try:
        while True:
            text = await socket.receive_text()
            await socket.send_text(text)
    except Exception:
        await socket.close()
`,
    });
  }

  if (flags.includeQueues) {
    files.push({
      path: "app/queue.py",
      contents: `# SPDX-License-Identifier: Apache-2.0
"""Redis-backed job queue (RQ)."""
import redis
from rq import Queue

from app.settings import settings

_connection = redis.from_url("redis://localhost:6379/0")
job_queue: Queue = Queue("default", connection=_connection)


def enqueue(func, *args, **kwargs) -> str:
    """Enqueue a job; returns the RQ job id."""
    job = job_queue.enqueue(func, *args, **kwargs)
    return job.id
`,
    });
  }

  if (deployment === "docker") {
    files.push(...dockerFiles(name, "python:3.11-slim", "uvicorn app.main:app --host 0.0.0.0 --port 8000"));
  }
  if (deployment === "k8s") files.push(k8sDeployment(name, 8000));

  return {
    name,
    files,
    notes: [
      "python -m venv .venv && source .venv/bin/activate",
      "pip install -r requirements.txt",
      "cp .env.example .env  # then edit",
      "uvicorn app.main:app --reload",
    ],
  };
}

// ---- Express --------------------------------------------------------------

function expressScaffold(
  name: string,
  db: Database,
  deployment: Deployment,
  flags: FeatureFlags,
): Scaffold {
  const deps: Record<string, string> = { express: "^4.21.0" };
  if (db === "postgres" || db === "mysql") deps.knex = "^3.1.0";
  if (db === "postgres") deps.pg = "^8.13.0";
  if (db === "mysql") deps.mysql2 = "^3.11.0";
  if (db === "mongodb") deps.mongodb = "^6.10.0";
  if (db === "sqlite") deps["better-sqlite3"] = "^11.3.0";
  if (flags.includeAuth) deps.jsonwebtoken = "^9.0.2";
  if (flags.includeRateLimit) deps["express-rate-limit"] = "^7.4.0";
  if (flags.includeWs) deps.ws = "^8.18.0";
  if (flags.includeQueues) deps.bullmq = "^5.13.0";

  const pkg = {
    name,
    version: "0.1.0",
    private: true,
    type: "module",
    main: "src/index.js",
    scripts: { start: "node src/index.js", dev: "node --watch src/index.js" },
    dependencies: deps,
  };

  const indexJs = `// SPDX-License-Identifier: Apache-2.0
// Express entrypoint for ${name}.
import express from "express";
${flags.includeRateLimit ? 'import rateLimit from "express-rate-limit";\n' : ""}${flags.includeAuth ? 'import { authRouter } from "./routes/auth.js";\n' : ""}import { healthRouter } from "./routes/health.js";

const app = express();
app.use(express.json());
${flags.includeRateLimit ? 'app.use(rateLimit({ windowMs: 60_000, max: 100 }));\n' : ""}app.use("/health", healthRouter);
${flags.includeAuth ? 'app.use("/auth", authRouter);\n' : ""}

const port = Number(process.env.PORT) || 3000;
app.listen(port, () => console.log("listening on", port));
`;

  const healthRoute = `// SPDX-License-Identifier: Apache-2.0
import { Router } from "express";
export const healthRouter = Router();
healthRouter.get("/", (_req, res) => res.json({ status: "ok" }));
`;

  const files: GeneratedFile[] = [
    { path: "package.json", contents: JSON.stringify(pkg, null, 2) + "\n" },
    { path: "src/index.js", contents: indexJs },
    { path: "src/routes/health.js", contents: healthRoute },
    {
      path: ".env.example",
      contents: `PORT=3000\nDATABASE_URL=${dbUrlExample(db)}\nJWT_SECRET=change-me\n`,
    },
    {
      path: "README.md",
      contents: `# ${name}\n\nExpress scaffold.\n\n\`\`\`bash\nnpm install\nnpm run dev\n\`\`\`\n`,
    },
  ];

  if (flags.includeAuth) {
    files.push({
      path: "src/routes/auth.js",
      contents: `// SPDX-License-Identifier: Apache-2.0
import { Router } from "express";
import jwt from "jsonwebtoken";
export const authRouter = Router();
authRouter.post("/token", (req, res) => {
  const { username, password } = req.body ?? {};
  if (!username || !password) return res.status(400).json({ error: "missing credentials" });
  const secret = process.env.JWT_SECRET ?? "change-me";
  const token = jwt.sign({ sub: username }, secret, { expiresIn: "15m" });
  res.json({ access_token: token, token_type: "bearer" });
});
`,
    });
  }

  if (flags.includeWs) {
    files.push({
      path: "src/ws.js",
      contents: `// SPDX-License-Identifier: Apache-2.0
import { WebSocketServer } from "ws";
export function attachWs(server) {
  const wss = new WebSocketServer({ server, path: "/ws" });
  wss.on("connection", (socket) => socket.on("message", (msg) => socket.send(msg)));
}
`,
    });
  }

  if (flags.includeQueues) {
    files.push({
      path: "src/queue.js",
      contents: `// SPDX-License-Identifier: Apache-2.0
import { Queue } from "bullmq";
export const jobQueue = new Queue("default", { connection: { host: "localhost", port: 6379 } });
`,
    });
  }

  if (deployment === "docker") {
    files.push(...dockerFiles(name, "node:20-alpine", "node src/index.js"));
  }
  if (deployment === "k8s") files.push(k8sDeployment(name, 3000));

  return {
    name,
    files,
    notes: ["npm install", "cp .env.example .env", "npm run dev"],
  };
}

// ---- NestJS / Django / Go-Gin / Go-Fiber (minimal but runnable) -----------

function nestjsScaffold(name: string, db: Database, deployment: Deployment): Scaffold {
  const pkg = {
    name,
    version: "0.1.0",
    private: true,
    scripts: { start: "ts-node src/main.ts" },
    dependencies: {
      "@nestjs/common": "^10.4.0",
      "@nestjs/core": "^10.4.0",
      "@nestjs/platform-express": "^10.4.0",
      "reflect-metadata": "^0.2.2",
      rxjs: "^7.8.1",
    },
    devDependencies: { typescript: "^5.7.0", "ts-node": "^10.9.2", "@types/node": "^20.0.0" },
  };
  const main = `// SPDX-License-Identifier: Apache-2.0
import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app.module";
async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  await app.listen(3000);
}
bootstrap();
`;
  const appModule = `// SPDX-License-Identifier: Apache-2.0
import { Module, Controller, Get } from "@nestjs/common";

@Controller("health")
class HealthController {
  @Get() health() { return { status: "ok" }; }
}

@Module({ controllers: [HealthController] })
export class AppModule {}
`;
  const files: GeneratedFile[] = [
    { path: "package.json", contents: JSON.stringify(pkg, null, 2) + "\n" },
    { path: "tsconfig.json", contents: '{"compilerOptions":{"target":"ES2022","module":"commonjs","experimentalDecorators":true,"emitDecoratorMetadata":true,"strict":true,"esModuleInterop":true,"outDir":"dist"}}\n' },
    { path: "src/main.ts", contents: main },
    { path: "src/app.module.ts", contents: appModule },
    { path: ".env.example", contents: `DATABASE_URL=${dbUrlExample(db)}\n` },
    { path: "README.md", contents: `# ${name}\n\nNestJS scaffold.\n\n\`\`\`bash\nnpm install\nnpm start\n\`\`\`\n` },
  ];
  if (deployment === "docker") {
    files.push(...dockerFiles(name, "node:20-alpine", "npx ts-node src/main.ts"));
  }
  if (deployment === "k8s") files.push(k8sDeployment(name, 3000));
  return { name, files, notes: ["npm install", "npm start"] };
}

function djangoScaffold(name: string, db: Database, deployment: Deployment): Scaffold {
  const settings = `# SPDX-License-Identifier: Apache-2.0
"""Minimal Django settings for ${name}."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "change-me"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = ["django.contrib.contenttypes", "django.contrib.auth", "core"]
MIDDLEWARE: list[str] = []
ROOT_URLCONF = "project.urls"
TEMPLATES: list[dict] = []
DATABASES = {"default": ${djangoDbConfig(db)}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
`;
  const urls = `# SPDX-License-Identifier: Apache-2.0
from django.http import JsonResponse
from django.urls import path
urlpatterns = [path("health", lambda r: JsonResponse({"status": "ok"}))]
`;
  const manage = `#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
import os, sys
from django.core.management import execute_from_command_line
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
if __name__ == "__main__":
    execute_from_command_line(sys.argv)
`;
  const files: GeneratedFile[] = [
    { path: "manage.py", contents: manage },
    { path: "project/__init__.py", contents: "" },
    { path: "project/settings.py", contents: settings },
    { path: "project/urls.py", contents: urls },
    { path: "core/__init__.py", contents: "" },
    { path: "core/models.py", contents: "# SPDX-License-Identifier: Apache-2.0\nfrom django.db import models  # noqa: F401\n" },
    { path: "requirements.txt", contents: "django>=5.0\n" },
    { path: "README.md", contents: `# ${name}\n\nDjango scaffold.\n\n\`\`\`bash\npip install -r requirements.txt\npython manage.py runserver\n\`\`\`\n` },
  ];
  if (deployment === "docker") files.push(...dockerFiles(name, "python:3.11-slim", "python manage.py runserver 0.0.0.0:8000"));
  if (deployment === "k8s") files.push(k8sDeployment(name, 8000));
  return { name, files, notes: ["pip install -r requirements.txt", "python manage.py runserver"] };
}

function goGinScaffold(name: string, db: Database, deployment: Deployment): Scaffold {
  const main = `// SPDX-License-Identifier: Apache-2.0
package main

import (
\t"net/http"

\t"github.com/gin-gonic/gin"
)

func main() {
\tr := gin.Default()
\tr.GET("/health", func(c *gin.Context) {
\t\tc.JSON(http.StatusOK, gin.H{"status": "ok"})
\t})
\t_ = r.Run(":8080")
}
`;
  return goScaffold(name, db, deployment, main, "github.com/gin-gonic/gin v1.10.0");
}

function goFiberScaffold(name: string, db: Database, deployment: Deployment): Scaffold {
  const main = `// SPDX-License-Identifier: Apache-2.0
package main

import "github.com/gofiber/fiber/v2"

func main() {
\tapp := fiber.New()
\tapp.Get("/health", func(c *fiber.Ctx) error {
\t\treturn c.JSON(fiber.Map{"status": "ok"})
\t})
\t_ = app.Listen(":8080")
}
`;
  return goScaffold(name, db, deployment, main, "github.com/gofiber/fiber/v2 v2.52.5");
}

function goScaffold(name: string, db: Database, deployment: Deployment, main: string, require: string): Scaffold {
  const files: GeneratedFile[] = [
    { path: "main.go", contents: main },
    { path: "go.mod", contents: `module ${name}\n\ngo 1.22\n\nrequire ${require}\n` },
    { path: ".env.example", contents: `DATABASE_URL=${dbUrlExample(db)}\n` },
    { path: "README.md", contents: `# ${name}\n\nGo scaffold.\n\n\`\`\`bash\ngo mod tidy\ngo run .\n\`\`\`\n` },
  ];
  if (deployment === "docker") files.push(...dockerFiles(name, "golang:1.22-alpine", "go run ."));
  if (deployment === "k8s") files.push(k8sDeployment(name, 8080));
  return { name, files, notes: ["go mod tidy", "go run ."] };
}

// ---- Shared helpers --------------------------------------------------------

function dbUrlExample(db: Database): string {
  switch (db) {
    case "postgres": return "postgres://user:pass@localhost:5432/app";
    case "mysql": return "mysql://user:pass@localhost:3306/app";
    case "mongodb": return "mongodb://localhost:27017/app";
    case "sqlite": return "sqlite:///./app.db";
  }
}

function djangoDbConfig(db: Database): string {
  switch (db) {
    case "postgres": return '{"ENGINE": "django.db.backends.postgresql", "NAME": "app"}';
    case "mysql": return '{"ENGINE": "django.db.backends.mysql", "NAME": "app"}';
    case "sqlite": return '{"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}';
    case "mongodb": return '{"ENGINE": "djongo", "NAME": "app"}';
  }
}

function dockerFiles(name: string, baseImage: string, runCmd: string): GeneratedFile[] {
  return [
    {
      path: "Dockerfile",
      contents: `# SPDX-License-Identifier: Apache-2.0
FROM ${baseImage}
WORKDIR /app
COPY . .
${baseImage.startsWith("python") ? "RUN pip install --no-cache-dir -r requirements.txt" : ""}
${baseImage.startsWith("node") ? "RUN npm ci --omit=dev || npm install --omit=dev" : ""}
${baseImage.startsWith("golang") ? "RUN go mod download" : ""}
CMD ${JSON.stringify(runCmd.split(" "))}
`,
    },
    {
      path: ".dockerignore",
      contents: "node_modules\n.venv\n__pycache__\n.git\n.env\n",
    },
  ];
}

function k8sDeployment(name: string, port: number): GeneratedFile {
  return {
    path: "k8s/deployment.yaml",
    contents: `# SPDX-License-Identifier: Apache-2.0
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${name}
spec:
  replicas: 2
  selector:
    matchLabels: { app: ${name} }
  template:
    metadata:
      labels: { app: ${name} }
    spec:
      containers:
        - name: ${name}
          image: ${name}:latest
          ports:
            - containerPort: ${port}
---
apiVersion: v1
kind: Service
metadata:
  name: ${name}
spec:
  selector: { app: ${name} }
  ports:
    - port: 80
      targetPort: ${port}
`,
  };
}
