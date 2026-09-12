# ANS Agent — инструкция

## Быстрый запуск
1. Клонируйте репозиторий.
2. Скопируйте .env.example в .env.
3. Установите Python 3.12+ и Git.
4. Установите зависимости: pip install -r requirements.txt
5. Установите и авторизуйте Claude Code CLI, затем проверьте команду claude.
6. Для локального запуска задайте ANS_WORKSPACE=./workspace.
7. Запустите python run.py.
8. Откройте http://localhost:8080.

## Провайдеры
Claude Code — основной coding executor.
OpenAI — planner/reviewer при наличии OPENAI_API_KEY.
Gemini — дополнительный provider при наличии GEMINI_API_KEY.
OpenRouter — free/fallback pool при наличии OPENROUTER_API_KEY.

Не публикуйте .env и API-ключи.

## Режимы
Chat — обычный ответ.
Agent — планирование, выполнение и review.
Autopilot — продолжение цикла до завершения или лимита.
Best of N — несколько решений и отдельный judge.

## Работа с проектом
Положите проект в workspace. Сначала дайте задачу на аудит. Затем разбивайте работу на крупные этапы и проверяйте Git Diff после каждого этапа.

Для игры можно использовать последовательность: audit → core loop → combat → UI → assets → audio → progression → tests/build.

## Безопасность
Workspace ограничен своей корневой директорией. Не монтируйте домашнюю директорию целиком. Перед production добавьте approval для destructive commands, secrets, deployment и сетевых операций.

## API
GET /health
GET /models
POST /route
GET /sessions
GET /sessions/{id}
GET /workspace/files
GET /workspace/file?path=...
GET /workspace/status
GET /workspace/diff
POST /run
WS /ws/{session_id}
