import hashlib
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

import bcrypt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "todo.db"))


# --- База данных SQLite ---


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tokens (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (owner_id) REFERENCES users (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                list_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (owner_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (list_id) REFERENCES lists (id) ON DELETE CASCADE
            );
            """
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Todo System API", version="2.0.0", lifespan=lifespan)


# --- Аутентификация ---


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Передайте заголовок Authorization: Bearer <token>",
        )
    raw_token = authorization.removeprefix("Bearer ").strip()
    token_digest = hash_token(raw_token)

    with get_db() as conn:
        user = conn.execute(
            """
            SELECT u.id, u.username, u.created_at
            FROM tokens t
            JOIN users u ON u.id = t.user_id
            WHERE t.token_hash = ?
            """,
            (token_digest,),
        ).fetchone()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный или устаревший токен",
        )
    return dict(user)


# --- Pydantic-модели ---


class AuthRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ListCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)


class ListUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=300)


class TaskListResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    description: str
    tasks_count: int = 0


class TaskCreate(BaseModel):
    list_id: int
    title: str = Field(..., min_length=1, max_length=200)
    completed: bool = False


class TaskUpdate(BaseModel):
    list_id: Optional[int] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    completed: Optional[bool] = None


class Task(BaseModel):
    id: int
    list_id: int
    title: str
    completed: bool


def row_to_task(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "list_id": row["list_id"],
        "title": row["title"],
        "completed": bool(row["completed"]),
    }


# --- Роуты аутентификации ---


@app.post("/auth/register", response_model=UserResponse, status_code=201, tags=["Auth"])
def register(payload: AuthRequest) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    pw_hash = hash_password(payload.password)
    with get_db() as conn:
        exists = conn.execute("SELECT id FROM users WHERE username = ?", (payload.username,)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="Такой username уже занят")
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (payload.username, pw_hash, now),
        )
        user = conn.execute(
            "SELECT id, username, created_at FROM users WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return dict(user)


@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
def login(payload: AuthRequest) -> dict:
    with get_db() as conn:
        user = conn.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
            (payload.username,),
        ).fetchone()
        if not user or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Неверный логин или пароль")

        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO tokens (token_hash, user_id, created_at) VALUES (?, ?, ?)",
            (hash_token(raw_token), user["id"], now),
        )

    return {
        "access_token": raw_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "created_at": user["created_at"],
        },
    }


@app.get("/auth/me", response_model=UserResponse, tags=["Auth"])
def get_me(current_user: dict = Depends(get_current_user)) -> dict:
    return current_user


# --- CRUD для списков (Lists) ---


@app.get("/lists", response_model=List[TaskListResponse], tags=["Lists"])
def get_lists(current_user: dict = Depends(get_current_user)) -> List[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT l.id, l.owner_id, l.name, l.description, COUNT(t.id) AS tasks_count
            FROM lists l
            LEFT JOIN tasks t ON t.list_id = l.id
            WHERE l.owner_id = ?
            GROUP BY l.id
            ORDER BY l.id DESC
            """,
            (current_user["id"],),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/lists/{list_id}", response_model=TaskListResponse, tags=["Lists"])
def get_list(list_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT l.id, l.owner_id, l.name, l.description, COUNT(t.id) AS tasks_count
            FROM lists l
            LEFT JOIN tasks t ON t.list_id = l.id
            WHERE l.id = ? AND l.owner_id = ?
            GROUP BY l.id
            """,
            (list_id, current_user["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Список не найден")
    return dict(row)


@app.post("/lists", response_model=TaskListResponse, status_code=201, tags=["Lists"])
def create_list(payload: ListCreate, current_user: dict = Depends(get_current_user)) -> dict:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO lists (owner_id, name, description) VALUES (?, ?, ?)",
            (current_user["id"], payload.name, payload.description),
        )
        row = conn.execute(
            """
            SELECT l.id, l.owner_id, l.name, l.description, 0 AS tasks_count
            FROM lists l
            WHERE l.id = ?
            """,
            (cur.lastrowid,),
        ).fetchone()
    return dict(row)


@app.patch("/lists/{list_id}", response_model=TaskListResponse, tags=["Lists"])
def update_list(
    list_id: int,
    payload: ListUpdate,
    current_user: dict = Depends(get_current_user),
) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    params = list(updates.values()) + [list_id, current_user["id"]]

    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE lists SET {set_clause} WHERE id = ? AND owner_id = ?",
            params,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Список не найден")
        row = conn.execute(
            """
            SELECT l.id, l.owner_id, l.name, l.description, COUNT(t.id) AS tasks_count
            FROM lists l
            LEFT JOIN tasks t ON t.list_id = l.id
            WHERE l.id = ? AND l.owner_id = ?
            GROUP BY l.id
            """,
            (list_id, current_user["id"]),
        ).fetchone()
    return dict(row)


@app.delete("/lists/{list_id}", status_code=204, tags=["Lists"])
def delete_list(list_id: int, current_user: dict = Depends(get_current_user)) -> None:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM lists WHERE id = ? AND owner_id = ?",
            (list_id, current_user["id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Список не найден")


# --- CRUD для задач (Tasks) ---


@app.get("/tasks", response_model=List[Task], tags=["Tasks"])
def get_tasks(
    list_id: Optional[int] = None,
    completed: Optional[bool] = None,
    current_user: dict = Depends(get_current_user),
) -> List[dict]:
    query = "SELECT id, list_id, title, completed FROM tasks WHERE owner_id = ?"
    params: list = [current_user["id"]]

    if list_id is not None:
        query += " AND list_id = ?"
        params.append(list_id)
    if completed is not None:
        query += " AND completed = ?"
        params.append(int(completed))

    query += " ORDER BY id DESC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_task(r) for r in rows]


@app.get("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
def get_task(task_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, list_id, title, completed FROM tasks WHERE id = ? AND owner_id = ?",
            (task_id, current_user["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return row_to_task(row)


@app.post("/tasks", response_model=Task, status_code=201, tags=["Tasks"])
def create_task(task: TaskCreate, current_user: dict = Depends(get_current_user)) -> dict:
    with get_db() as conn:
        target_list = conn.execute(
            "SELECT id FROM lists WHERE id = ? AND owner_id = ?",
            (task.list_id, current_user["id"]),
        ).fetchone()
        if not target_list:
            raise HTTPException(status_code=404, detail="Указанный список не найден")

        cur = conn.execute(
            "INSERT INTO tasks (owner_id, list_id, title, completed) VALUES (?, ?, ?, ?)",
            (current_user["id"], task.list_id, task.title, int(task.completed)),
        )
        row = conn.execute(
            "SELECT id, list_id, title, completed FROM tasks WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return row_to_task(row)


@app.patch("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
def update_task(
    task_id: int,
    task: TaskUpdate,
    current_user: dict = Depends(get_current_user),
) -> dict:
    updates = {}
    if task.list_id is not None:
        with get_db() as conn:
            target_list = conn.execute(
                "SELECT id FROM lists WHERE id = ? AND owner_id = ?",
                (task.list_id, current_user["id"]),
            ).fetchone()
            if not target_list:
                raise HTTPException(status_code=404, detail="Новый список не найден")
        updates["list_id"] = task.list_id
    if task.title is not None:
        updates["title"] = task.title
    if task.completed is not None:
        updates["completed"] = int(task.completed)

    if not updates:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    params = list(updates.values()) + [task_id, current_user["id"]]

    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ? AND owner_id = ?",
            params,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        row = conn.execute(
            "SELECT id, list_id, title, completed FROM tasks WHERE id = ? AND owner_id = ?",
            (task_id, current_user["id"]),
        ).fetchone()
    return row_to_task(row)


@app.delete("/tasks/{task_id}", status_code=204, tags=["Tasks"])
def delete_task(task_id: int, current_user: dict = Depends(get_current_user)) -> None:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM tasks WHERE id = ? AND owner_id = ?",
            (task_id, current_user["id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Задача не найдена")


# --- HTML-страница ---


HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <title>Todo System — Списки и задачи</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 780px; margin: 32px auto; padding: 0 16px; background: #f6f7f9; }
    .card { background: #fff; border: 1px solid #d8dee4; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
    input, select, button { padding: 8px 10px; margin: 4px 4px 4px 0; border-radius: 6px; border: 1px solid #c5ccd4; }
    button { background: #1f6feb; color: #fff; border: none; cursor: pointer; }
    button.danger { background: #cf222e; }
    button.secondary { background: #57606a; }
    .row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #eee; }
    .done { text-decoration: line-through; color: #6e7781; }
    .muted { color: #57606a; font-size: 0.9em; }
  </style>
</head>
<body>
  <h1>Todo System</h1>
  <p class="muted">Связанные сущности: Users &rarr; Lists &rarr; Tasks. <a href="/docs">Открыть Swagger UI</a></p>

  <div class="card" id="auth-card">
    <h3>Регистрация / Вход</h3>
    <input id="username" placeholder="username" />
    <input id="password" type="password" placeholder="password" />
    <button onclick="auth('/auth/register')">Регистрация</button>
    <button onclick="auth('/auth/login')">Войти</button>
    <div id="auth-msg" style="color:#cf222e; margin-top:6px;"></div>
  </div>

  <div class="card" id="app-card" style="display:none;">
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <strong id="user-label"></strong>
      <button class="secondary" onclick="logout()">Выйти</button>
    </div>

    <h4>Списки (Lists)</h4>
    <input id="list-name" placeholder="Название списка (например, Учёба)" />
    <input id="list-desc" placeholder="Описание" />
    <button onclick="addList()">Создать список</button>
    <div id="lists-box" style="margin-top:8px;"></div>

    <hr />

    <h4>Задачи (Tasks)</h4>
    <select id="task-list-select" onchange="loadTasks()"></select>
    <input id="new-title" placeholder="Новая задача..." />
    <button onclick="addTask()">Добавить</button>
    <div id="tasks-list" style="margin-top:12px;"></div>
  </div>

  <script>
    let token = localStorage.getItem("todo_token") || "";

    function headers() {
      return { "Content-Type": "application/json", "Authorization": "Bearer " + token };
    }

    async function auth(url) {
      const username = document.getElementById("username").value.trim();
      const password = document.getElementById("password").value;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (!res.ok) {
        document.getElementById("auth-msg").textContent = data.detail || "Ошибка";
        return;
      }
      document.getElementById("auth-msg").textContent = "";
      if (url === "/auth/register") {
        return auth("/auth/login");
      }
      token = data.access_token;
      localStorage.setItem("todo_token", token);
      loadApp();
    }

    function logout() {
      token = "";
      localStorage.removeItem("todo_token");
      document.getElementById("app-card").style.display = "none";
      document.getElementById("auth-card").style.display = "block";
    }

    async function loadApp() {
      const me = await fetch("/auth/me", { headers: headers() });
      if (!me.ok) return logout();
      const user = await me.json();
      document.getElementById("user-label").textContent = "Аккаунт: " + user.username;
      document.getElementById("auth-card").style.display = "none";
      document.getElementById("app-card").style.display = "block";
      await loadLists();
      await loadTasks();
    }

    async function loadLists() {
      const res = await fetch("/lists", { headers: headers() });
      const lists = await res.json();
      const sel = document.getElementById("task-list-select");
      const prev = sel.value;
      sel.innerHTML = `<option value="">Все списки</option>` + lists.map(l =>
        `<option value="${l.id}">${l.name} (#${l.id})</option>`
      ).join("");
      if (prev) sel.value = prev;

      document.getElementById("lists-box").innerHTML = lists.map(l => `
        <div class="row">
          <div><strong>${l.name}</strong> <span class="muted">${l.description ? "— " + l.description : ""} (задач: ${l.tasks_count})</span></div>
          <button class="danger" onclick="deleteList(${l.id})">Удалить</button>
        </div>
      `).join("") || "<p class='muted'>Создай первый список выше</p>";
    }

    async function addList() {
      const name = document.getElementById("list-name").value.trim();
      const description = document.getElementById("list-desc").value.trim();
      if (!name) return;
      await fetch("/lists", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ name, description })
      });
      document.getElementById("list-name").value = "";
      document.getElementById("list-desc").value = "";
      await loadLists();
    }

    async function deleteList(id) {
      await fetch("/lists/" + id, { method: "DELETE", headers: headers() });
      await loadLists();
      await loadTasks();
    }

    async function loadTasks() {
      const listId = document.getElementById("task-list-select").value;
      const url = listId ? `/tasks?list_id=${listId}` : "/tasks";
      const res = await fetch(url, { headers: headers() });
      const tasks = await res.json();
      document.getElementById("tasks-list").innerHTML = tasks.map(t => `
        <div class="row">
          <div>
            <span class="${t.completed ? 'done' : ''}">${t.title}</span>
            <span class="muted">[список #${t.list_id}]</span>
          </div>
          <div>
            <button onclick="toggleTask(${t.id}, ${!t.completed})">${t.completed ? 'Вернуть' : 'Готово'}</button>
            <button class="danger" onclick="deleteTask(${t.id})">Удалить</button>
          </div>
        </div>
      `).join("") || "<p class='muted'>Задач пока нет</p>";
    }

    async function addTask() {
      const listId = Number(document.getElementById("task-list-select").value);
      const input = document.getElementById("new-title");
      const title = input.value.trim();
      if (!listId) {
        alert("Сначала выбери конкретный список в выпадающем списке");
        return;
      }
      if (!title) return;
      await fetch("/tasks", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ list_id: listId, title, completed: false })
      });
      input.value = "";
      await loadTasks();
      await loadLists();
    }

    async function toggleTask(id, completed) {
      await fetch("/tasks/" + id, {
        method: "PATCH",
        headers: headers(),
        body: JSON.stringify({ completed })
      });
      await loadTasks();
    }

    async function deleteTask(id) {
      await fetch("/tasks/" + id, { method: "DELETE", headers: headers() });
      await loadTasks();
      await loadLists();
    }

    if (token) loadApp();
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root() -> str:
    return HTML_PAGE