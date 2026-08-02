# OpenClaude Dashboard (Python)

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

### ⚠️ Alpha Status

**This is an early alpha release.** Please be aware that:

- Not all features from the original project have been implemented yet
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

### ⚠️ Статус Альфа

**Это ранняя альфа-версия.** Пожалуйста, учитывайте, что:

- Не все функции оригинального проекта ещё реализованы
- Могут присутствовать баги, и не все сценарии использования протестированы
- API и интерфейсы могут изменяться без предупреждения
- Использование в production-среде — на ваш страх и риск

Приветствуются участие в разработке, баг-репорты и обратная связь!

### Лицензия

Проект сохраняет ту же лицензию, что и оригинальный репозиторий [Gitlawb/openclaude](https://github.com/Gitlawb/openclaude) — без каких-либо изменений.

---

© Original project: [Gitlawb/openclaude](https://github.com/Gitlawb/openclaude)
