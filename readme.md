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
- **Token usage tracking** — per-chat bar: `Tokens: 1.9k (1.3k in / 0.6k out) · Cache: 60%`; global project stats in sidebar `Tokens: 1.9k (1.3k in / 0.6k out) · Cache: 60%`; global project stats in sidebar
- **Prompt caching** — Anthropic (explicit cache control) & DeepSeek (native); cache hit % in token bar
- **Project instructions** — Setup tab: append project-specific rules to system prompt (stored in `.ai/project_prompt.txt`)
- **Inline reasoning cards** — agent thoughts appear right before each tool call, not stuck at the top; approval buttons always visible
- **Agent status indicator** — 🟢 Ready / 🟡 Thinking · Reasoning · Exec with elapsed timer

### ⚠️ Alpha Status

**This is an early alpha release.** Please be aware that:

- Core features preserved, new capabilities added
- Bugs may still be present and not all edge cases have been tested
- APIs and interfaces may change without notice
- Use at your own risk in production environments

Contributions, bug reports, and feedback are welcome!

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

### ⚠️ Статус Альфа

**Это ранняя альфа-версия.** Пожалуйста, учитывайте, что:

- Основные функции сохранены, добавлены новые возможности
- Могут присутствовать баги, и не все сценарии использования протестированы
- API и интерфейсы могут изменяться без предупреждения
- Использование в production-среде — на ваш страх и риск

Приветствуются участие в разработке, баг-репорты и обратная связь!

### Лицензия

Проект сохраняет ту же лицензию, что и оригинальный репозиторий [Gitlawb/openclaude](https://github.com/Gitlawb/openclaude) — без каких-либо изменений.

---

© Original project: [Gitlawb/openclaude](https://github.com/Gitlawb/openclaude)
