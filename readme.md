# Open AI Dashboard (Python)

[English](#english) | [Русский](#русский)

---

## English

This is a fork of [Gitlawb/openclaude](https://github.com/Gitlawb/openclaude) — an open-source desktop dashboard for Claude AI.

The original project used **Node.js** for its dashboard component. This fork rewrites the dashboard in **Python**, eliminating the Node.js dependency entirely and making the stack more lightweight and Python-native.

### Quick Start

It is **recommended to use a virtual environment** to isolate dependencies:

```bash
# Create and activate a virtual environment
python -m venv venv

# On Linux/macOS:
source venv/bin/activate

# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Required packages (see `requirements.txt`):
- **aiohttp** (>=3.10.0) — async HTTP client/server
- **psutil** (>=6.0.0) — system monitoring utilities

### Features

- **Agent & Chat modes** — toggle between simple chat and tool-calling agent (file ops, shell commands)
- **Normal / Limitless** — require approval for writes, or auto-execute everything
- **Edit, copy & delete messages** — hover any user message for ✏️ 📋 🗑️; editing truncates history and resends
- **Chats per project** — history stored in `{work_dir}/.ai/chats/`, isolated from other projects
- **Custom system prompt** — Setup tab: define your own agent rules (leave blank for defaults)
- **Multiple AI providers** — OpenAI, Anthropic, Gemini, DeepSeek, Ollama, LM Studio, OpenRouter, NVIDIA NIM
- **Configuration profiles** — save and switch between provider setups
- **Token usage tracking** — per-chat bar: `Tokens: 1.9k (1.3k in / 0.6k out) · Cache: 60%`; global project stats in sidebar
- **Prompt caching** — Anthropic (explicit cache control) & DeepSeek (native); cache hit % in token bar
- **Project instructions** — Setup tab: append project-specific rules to system prompt (stored in `.ai/project_prompt.txt`)
- **Inline reasoning cards** — agent thoughts appear right before each tool call, not stuck at the top; approval buttons always visible
- **Agent status indicator** — 🟢 Ready / 🟡 Thinking · Reasoning · Exec with elapsed timer
- **Chat attachments** — attach files to a message (text attachments up to 200 KB each); stored separately so conversation history shows links, not inline content
- **@-mentions** — type `@` in the agent input to autocomplete files and folders from the working directory
- **Code-block copy & download** — one-click copy or save buttons on code blocks in assistant replies
- **Editable chat titles** — rename conversations inline; date/time shown in the conversation list
- **Collapsible reasoning** — collapse agent reasoning into a compact toggle
- **DeepSeek reasoning support** — `reasoning_content` rendered for DeepSeek reasoning models; extended API timeout (up to 5 min) so long thinking runs aren't cut off
- **Request cancellation** — stop an in-flight stream at any time
- **File listing tool** — agent can list files/dirs inside the working directory
- **Strict path confinement** — tool access is confined to the working directory (`..` traversal and symlink escapes blocked)
- **Resilience fixes** — user messages persist even when the assistant reply fails; Save & Resend works even when the text is unchanged; non-numeric usage fields are skipped safely

### ⚠️ Beta Status

**This is a beta release.** Please be aware that:

- Core features are stable and well tested
- Some edge cases may still exist
- APIs and interfaces may change, but less frequently than in alpha
- Use at your own risk in production environments

Contributions, bug reports, and feedback are welcome!

### ⚠️ Limitless Agent Mode — Sandbox Required

In **agent mode with the Limitless setting** the agent can execute shell commands and file operations **without approval**. It is **strictly recommended to run it only inside a sandbox or virtual machine**:

- LLMs can hallucinate or misinterpret input, producing destructive commands (deleting files, overwriting data, etc.)
- The agent has access to the working directory and can modify the files of the system and working prompts (`system prompt`, `.ai/project_prompt.txt`, etc.)
- Incorrect or malformed user input can lead to unintended side effects

Never run Limitless agent mode on your main machine with important data.

### License

This project retains the same license as the original [Gitlawb/openclaude](https://github.com/Gitlawb/openclaude) repository — no changes have been made to the licensing terms.

---

## Русский

Это форк проекта [Gitlawb/openclaude](https://github.com/Gitlawb/openclaude) — открытого десктопного дашборда для Claude AI.

Оригинальный проект использовал **Node.js** для компонента дашборда. В этом форке дашборд переписан на **Python**, что полностью убирает зависимость от Node.js и делает стек более лёгким и нативным для Python-экосистемы.

### Быстрый старт

**Рекомендуется использовать виртуальное окружение** для изоляции зависимостей:

```bash
# Создать и активировать виртуальное окружение
python -m venv venv

# На Linux/macOS:
source venv/bin/activate

# На Windows:
venv\Scripts\activate

# Установить зависимости
pip install -r requirements.txt
```

Необходимые пакеты (см. `requirements.txt`):
- **aiohttp** (>=3.10.0) — асинхронный HTTP клиент/сервер
- **psutil** (>=6.0.0) — утилиты для мониторинга системы

### Возможности

- **Agent и Chat режимы** — переключение между простым чатом и агентом с инструментами (файлы, команды)
- **Normal / Limitless** — запрос подтверждения для записи или авто-выполнение
- **Редактирование, копирование и удаление сообщений** — наведите на сообщение: ✏️ 📋 🗑️; при редактировании история обрезается и переотправляется
- **Чаты по проектам** — история в `{work_dir}/.ai/chats/`, изолирована от других проектов
- **Настраиваемый system prompt** — вкладка Setup: собственные инструкции для агента (пусто — используются стандартные)
- **Множество AI-провайдеров** — OpenAI, Anthropic, Gemini, DeepSeek, Ollama, LM Studio, OpenRouter, NVIDIA NIM
- **Профили конфигураций** — сохраняйте и переключайтесь между настройками провайдеров
- **Учёт токенов** — строка внизу чата: `Tokens: 1.9k (1.3k in / 0.6k out) · Cache: 60%`; глобальная статистика по проекту в сайдбаре
- **Кэширование промптов** — Anthropic (явное) и DeepSeek (авто); процент попаданий в кэш в токен-баре
- **Инструкции проекта** — вкладка Setup: добавление правил проекта в system prompt (файл `.ai/project_prompt.txt`)
- **Inline-карточки рассуждений** — мысли агента перед каждым действием, а не вверху; кнопки подтверждения всегда видны
- **Индикатор статуса агента** — 🟢 Ready / 🟡 Thinking · Reasoning · Exec с таймером
- **Вложения в чат** — прикрепляйте файлы к сообщению (текстовые вложения до 200 КБ); хранятся отдельно, поэтому в истории чата показываются ссылки, а не инлайн-содержимое
- **@-упоминания** — ввод `@` в поле агента подставляет файлы и папки рабочей директории (автодополнение)
- **Копирование и скачивание кода** — кнопки копирования/сохранения на блоках кода в ответах ассистента
- **Редактируемые заголовки чатов** — переименование диалогов на месте; дата/время в списке диалогов
- **Сворачиваемые рассуждения** — сворачивание блока рассуждений агента в компактный переключатель
- **Поддержка DeepSeek reasoning** — вывод `reasoning_content` для reasoning-моделей DeepSeek; увеличенный таймаут API (до 5 минут), чтобы длинные размышления не обрывались
- **Отмена запроса** — остановка активного стрима в любой момент
- **Инструмент листинга файлов** — агент может выводить список файлов/папок внутри рабочей директории
- **Строгое ограничение путей** — доступ инструментов ограничен рабочей директорией (обходы через `..` и симлинки блокируется)
- **Фиксы надёжности** — сообщение пользователя сохраняется, даже если ответ ассистента не удался; Save & Resend работает даже при неизменном тексте; некорректные поля usage безопасно пропускаются

### ⚠️ Статус Бета

**Это бета-версия.** Пожалуйста, учитывайте, что:

- Основные функции стабильны и протестированы
- Отдельные краевые случаи могут ещё встречаться
- API и интерфейсы могут меняться, но реже, чем в альфа-версии
- Использование в production-среде — на ваш страх и риск

Приветствуются участие в разработке, баг-репорты и обратная связь!

### ⚠️ Режим агента Limitless — требуется песочница

В **режиме агента с настройкой Limitless** агент может выполнять shell-команды и файловые операции **без подтверждения**. **Строго рекомендуется запускать его только внутри песочницы или виртуальной машины**:

- LLM могут галлюцинировать или неверно интерпретировать ввод, что приводит к разрушительным командам (удаление файлов, перезапись данных и т.п.)
- Агент имеет доступ к рабочей директории и может изменять файлы системного и рабочего промтов (`system prompt`, `.ai/project_prompt.txt` и др.)
- Некорректный или повреждённый ввод пользователя может привести к непреднамеренным побочным эффектам

Никогда не запускайте режим агента Limitless на основной машине с важными данными.

### Лицензия

Проект сохраняет ту же лицензию, что и оригинальный репозиторий [Gitlawb/openclaude](https://github.com/Gitlawb/openclaude) — без каких-либо изменений.

---

© Original project: [Gitlawb/openclaude](https://github.com/Gitlawb/openclaude)
