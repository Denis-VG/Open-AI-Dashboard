"""
Модуль проверки установленных Python-пакетов из requirements.txt.

Использование:
    python check_requirements.py [--requirements requirements.txt] [--json]

Импорт:
    from check_requirements import check_requirements, PackageStatus
    
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class PackageStatus(Enum):
    """Статус проверки пакета."""
    OK = "ok"                    # Установлен, версия удовлетворяет требованию
    MISSING = "missing"          # Не установлен
    VERSION_MISMATCH = "version_mismatch"  # Установлен, но версия не подходит
    UNKNOWN = "unknown"          # Не удалось определить версию


@dataclass
class PackageResult:
    """Результат проверки одного пакета."""
    name: str
    required_spec: str           # Например: ">=3.10.0"
    installed_version: Optional[str] = None
    status: PackageStatus = PackageStatus.UNKNOWN
    message: str = ""

    @property
    def is_ok(self) -> bool:
        return self.status == PackageStatus.OK


@dataclass
class CheckResult:
    """Результат полной проверки всех пакетов."""
    results: List[PackageResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(r.is_ok for r in self.results) and len(self.errors) == 0

    @property
    def missing(self) -> List[PackageResult]:
        return [r for r in self.results if r.status == PackageStatus.MISSING]

    @property
    def mismatched(self) -> List[PackageResult]:
        return [r for r in self.results if r.status == PackageStatus.VERSION_MISMATCH]

    @property
    def ok(self) -> List[PackageResult]:
        return [r for r in self.results if r.status == PackageStatus.OK]


def _parse_requirement(line: str) -> Optional[Tuple[str, str]]:
    """Парсит одну строку требований, возвращает (имя_пакета, спецификация_версии)."""
    line = line.strip()
    # Убираем комментарии
    line = re.sub(r'\s*#.*$', '', line)
    if not line:
        return None
    # Разделяем имя пакета и спецификаторы версий
    # Поддерживаем: pkg, pkg==1.0, pkg>=1.0, pkg>=1.0,<2.0 и т.д.
    match = re.match(
        r'^([A-Za-z0-9_\-\.]+)\s*((?:[~=!<>]=?\s*[A-Za-z0-9\.\*\-]+(?:\s*,\s*)?)*)\s*$',
        line,
    )
    if not match:
        return None
    name = match.group(1).lower().replace('-', '_').replace('.', '_')
    spec = match.group(2).strip()
    return name, spec


def _parse_requirements_file(path: str | Path) -> List[Tuple[str, str]]:
    """Читает requirements.txt и возвращает список (имя_пакета, спецификация)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    requirements: List[Tuple[str, str]] = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            parsed = _parse_requirement(line)
            if parsed is not None:
                requirements.append(parsed)
    return requirements


def _get_installed_version(package_name: str) -> Optional[str]:
    """Возвращает установленную версию пакета или None."""
    # Пробуем несколько вариантов имени (importlib нормализует имена)
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        pass

    # Пробуем альтернативные написания
    alternatives = [
        package_name.replace('_', '-'),
        package_name.replace('-', '_'),
    ]
    for alt in alternatives:
        if alt == package_name:
            continue
        try:
            return importlib.metadata.version(alt)
        except importlib.metadata.PackageNotFoundError:
            pass

    return None


def _check_version(installed: str, spec: str) -> bool:
    """Проверяет, удовлетворяет ли установленная версия спецификации."""
    if not spec:
        return True  # Любая версия подходит

    # Разбираем спецификаторы, разделённые запятыми
    specifiers = [s.strip() for s in spec.split(',') if s.strip()]

    # Парсим установленную версию
    try:
        installed_tuple = tuple(int(x) for x in installed.split('.'))
    except (ValueError, TypeError):
        return False

    for s in specifiers:
        # Извлекаем оператор и версию
        m = re.match(r'^([~=!<>]=?)\s*([A-Za-z0-9\.\*\-]+)\s*$', s)
        if not m:
            continue
        op, target = m.group(1), m.group(2)
        try:
            target_tuple = tuple(int(x) for x in target.split('.'))
        except (ValueError, TypeError):
            return False

        if not _compare_versions(installed_tuple, op, target_tuple):
            return False

    return True


def _compare_versions(v1: tuple, op: str, v2: tuple) -> bool:
    """Сравнивает кортежи версий согласно оператору."""
    if op == '==':
        return v1 == v2
    elif op == '!=':
        return v1 != v2
    elif op == '>':
        return v1 > v2
    elif op == '>=':
        return v1 >= v2
    elif op == '<':
        return v1 < v2
    elif op == '<=':
        return v1 <= v2
    elif op == '~=':
        # Совместимый релиз: ~=3.10.0 означает >=3.10.0, ==3.10.*
        return v1 >= v2 and v1[:len(v2)] == v2[:len(v2)]
    return False


def check_requirements(requirements_path: str | Path = "requirements.txt") -> CheckResult:
    """Проверяет все пакеты из requirements.txt.

    Args:
        requirements_path: Путь к файлу требований.

    Returns:
        CheckResult с результатами проверки каждого пакета.
    """
    result = CheckResult()

    try:
        requirements = _parse_requirements_file(requirements_path)
    except FileNotFoundError as e:
        result.errors.append(str(e))
        return result
    except Exception as e:
        result.errors.append(f"Ошибка чтения файла: {e}")
        return result

    if not requirements:
        result.errors.append("Файл требований пуст или не содержит корректных записей")
        return result

    for name, spec in requirements:
        pkg_result = PackageResult(
            name=name,
            required_spec=spec or "любая",
        )

        installed = _get_installed_version(name)
        if installed is None:
            pkg_result.status = PackageStatus.MISSING
            pkg_result.message = f"[MISSING]  {name}  (требуется: {spec or 'любая'})"
        else:
            pkg_result.installed_version = installed
            if _check_version(installed, spec):
                pkg_result.status = PackageStatus.OK
                pkg_result.message = f"[OK]       {name} {installed}  (требуется: {spec or 'любая'})"
            else:
                pkg_result.status = PackageStatus.VERSION_MISMATCH
                pkg_result.message = (
                    f"[MISMATCH] {name}: установлена {installed}, требуется {spec}"
                )

        result.results.append(pkg_result)

    return result


def format_text_report(result: CheckResult) -> str:
    """Форматирует результат проверки в читаемый текстовый отчёт."""
    lines: List[str] = []

    if result.errors:
        lines.append("ОШИБКИ:")
        for err in result.errors:
            lines.append(f"  [!] {err}")
        lines.append("")

    total = len(result.results)
    ok_count = len(result.ok)
    missing_count = len(result.missing)
    mismatch_count = len(result.mismatched)

    lines.append(f"Проверено пакетов: {total}")
    lines.append(f"  OK:              {ok_count}")
    lines.append(f"  Не установлено:  {missing_count}")
    lines.append(f"  Несовместимо:    {mismatch_count}")
    lines.append("")

    for r in result.results:
        lines.append(f"  {r.message}")

    lines.append("")
    if result.all_ok:
        lines.append("Все требования выполнены.")
    else:
        lines.append("ВНИМАНИЕ: найдены несоответствия!")
        if result.missing:
            lines.append("\nУстановите недостающие пакеты:")
            for r in result.missing:
                spec_str = r.required_spec if r.required_spec != "любая" else ""
                lines.append(f"  pip install {r.name}{spec_str}")
        if result.mismatched:
            lines.append("\nОбновите несовместимые пакеты:")
            for r in result.mismatched:
                lines.append(f"  pip install '{r.name}{r.required_spec}'")

    return "\n".join(lines)


def format_json_report(result: CheckResult) -> str:
    """Форматирует результат проверки в JSON."""
    data = {
        "all_ok": result.all_ok,
        "total": len(result.results),
        "ok": len(result.ok),
        "missing": len(result.missing),
        "mismatched": len(result.mismatched),
        "errors": result.errors,
        "packages": [
            {
                "name": r.name,
                "required": r.required_spec,
                "installed": r.installed_version,
                "status": r.status.value,
                "message": r.message,
            }
            for r in result.results
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Проверка установленных Python-пакетов из requirements.txt",
    )
    parser.add_argument(
        "--requirements", "-r",
        default="requirements.txt",
        help="Путь к requirements.txt (по умолчанию: requirements.txt)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Вывести результат в формате JSON",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Только код возврата (0 = всё ok, 1 = есть проблемы)",
    )

    args = parser.parse_args()
    result = check_requirements(args.requirements)

    if args.quiet:
        sys.exit(0 if result.all_ok else 1)

    if args.json:
        print(format_json_report(result))
    else:
        print(format_text_report(result))

    sys.exit(0 if result.all_ok else 1)


if __name__ == "__main__":
    main()
