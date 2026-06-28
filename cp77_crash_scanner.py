#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CP77 Crash Scanner — desktop log & compatibility scanner for
Cyberpunk 2077 (Mod Organizer 2). Bilingual UI (RU/EN).

GUI:    python cp77_crash_scanner.py
Self-test: python cp77_crash_scanner.py --scan
Report: python cp77_crash_scanner.py --report
"""

__version__ = "1.1.0"

import os
import re
import sys
import json
import threading
import datetime as dt

# В режиме PyInstaller --windowed stdout/stderr == None; запись туда роняет exe.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

DEFAULT_INSTANCE = r"C:\ExGame\ModOrganizer_Cyberpunk2077\MO2_Exposition"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_config.json")
MAX_READ_BYTES = 4 * 1024 * 1024
REPORT_PER_LOG_CAP = 400 * 1024
VORTEX_APPDATA = os.path.join(os.environ.get("APPDATA", ""), "Vortex")

# --- классификация строк ------------------------------------------------------
ERROR_RE = re.compile(
    r"\b(error|fatal|exception|panic|failed|failure|could ?not|cannot|unable|"
    r"crash|assert|abort|stack overflow|access violation|null pointer|"
    r"not found|missing|mismatch|incompatible|unsupported)\b", re.IGNORECASE)
WARN_RE = re.compile(r"\b(warn|warning|deprecated|outdated|skipping|skipped)\b", re.IGNORECASE)
NOISE_RE = re.compile(
    r"(no error|0 error|errors: 0|without error|error handler|errorlog|"
    r"on error|error_|error code 0\b|"
    r"set3DListenerAttributes.*?invalid object handle|"
    r"FMOD::Channel.*?->stop\(\).*?invalid object handle)",
    re.IGNORECASE)
# Explicit log-level tags take priority over heuristic regex (e.g. "[warning] Type mismatch" → WARN, not ERROR)
EXPLICIT_ERROR_RE = re.compile(r"\[(error|fatal|critical)\b", re.IGNORECASE)
EXPLICIT_WARN_RE  = re.compile(r"\[(warn(?:ing)?)\b", re.IGNORECASE)

COSMETIC_RE = re.compile(
    r"(DynamicMesh.*(failed to instantiate|invalid path))|"
    r"(decals?_\w+@shared)|"
    r"(Material \".*?\" of \"\d+\" failed to instantiate)|"
    r"(appearance .*? not found)", re.IGNORECASE)
LOAD_FAIL_RE = re.compile(
    r"failed to (load|compile|initialize|attach)|could ?not load|compilation failed|"
    r"unsupported game version|requires game version|incompatible|not compatible|"
    r"wrong version|version mismatch|failed to resolve", re.IGNORECASE)

VERSION_PATTERNS = [
    # RED4ext log: "[RED4ext] RED4ext (v1.30.0) is initializing..."
    ("RED4ext",  re.compile(r"RED4ext\s*\(?v?\s*([0-9][0-9.]+)", re.IGNORECASE)),
    # CET log: "CET version v1.37.1 [HEAD]" or "Cyber Engine Tweaks v1.x"
    ("Cyber Engine Tweaks", re.compile(r"(?:Cyber Engine Tweaks|CET)\s*(?:version\s*)?v?\s*([0-9]+\.[0-9.]+)", re.IGNORECASE)),
    # RED4ext log: "ArchiveXL (version: 1.26.8, author(s): ...) has been loaded"
    ("ArchiveXL", re.compile(r"ArchiveXL\s*\(?(?:version:\s*|v?\s*)([0-9][0-9.]+)", re.IGNORECASE)),
    # RED4ext log: "TweakXL (version: 1.11.3, ...) has been loaded"
    ("TweakXL",  re.compile(r"TweakXL\s*\(?(?:version:\s*|v?\s*)([0-9][0-9.]+)", re.IGNORECASE)),
    # RED4ext log: "Codeware (version: 1.20.3, ...) has been loaded"
    ("Codeware", re.compile(r"Codeware\s*\(?(?:version:\s*|v?\s*)([0-9][0-9.]+)", re.IGNORECASE)),
    # redscript logs don't include version; pattern kept for future log format changes
    ("redscript", re.compile(r"redscript\s*[:(]?\s*v?\s*([0-9][0-9.]+)", re.IGNORECASE)),
    # RED4ext log: "Product version: 2.31" / CET log: "Game version 3.0.80.51928"
    ("Game",     re.compile(r"(?:Product|game)\s+version[:\s]+([0-9][0-9.]+)", re.IGNORECASE)),
]
DEFAULT_RECOMMENDED = {
    "RED4ext": "1.27.0", "Cyber Engine Tweaks": "1.35.0", "ArchiveXL": "1.21.0",
    "TweakXL": "1.11.3", "Codeware": "1.20.3", "redscript": "0.5.27",
}
CORE_FRAMEWORKS = ["RED4ext", "Cyber Engine Tweaks", "ArchiveXL", "TweakXL", "Codeware", "redscript"]

HEURISTICS = [
    (re.compile(r"redscript.*?(error|failed to compile|compilation failed)", re.I), "prob_redscript"),
    # Only match DLL plugin failures — Python (.py) files are MO2 UI plugins, not RED4ext plugins
    (re.compile(r"failed to (load|initialize).*?\.dll\b", re.I), "prob_plugin"),
    (re.compile(r"(unsupported|incompatible).*?(game|version)", re.I), "prob_version"),
    (re.compile(r"could ?not find.*?(class|type|method|function|field)", re.I), "prob_missing_class"),
    (re.compile(r"access violation|stack overflow|null pointer|0xC0000005", re.I), "prob_av"),
    (re.compile(r"(missing|not found).*?\.archive", re.I), "prob_archive"),
    # NCA companion spawn state machine — causes location-specific crashes (Lizzie's, El Coyote, etc.)
    (re.compile(r"\[NCA\].*?(error|unexpected spawn state|effect not found)", re.I), "prob_nca_spawn"),
]

# Files that are documentation/licenses, not log files — skip scanning them for errors
SKIP_STEMS = frozenset({
    "thirdpartynotices", "license", "licence", "changelog", "readme",
    "credits", "notice", "notices", "eula", "copying", "authors",
})

# --- i18n ---------------------------------------------------------------------
CURRENT_LANG = "ru"
TR = {
    "instance": {"ru": "MO2 инстанс (необяз. для Vortex):", "en": "MO2 instance (optional for Vortex):"},
    "game": {"ru": "Игра:", "en": "Game:"},
    "language": {"ru": "Язык:", "en": "Language:"},
    "only_recent": {"ru": "Только последняя сессия (±2ч)", "en": "Only last session (±2h)"},
    "hide_cos": {"ru": "Скрывать косметику", "en": "Hide cosmetic"},
    "embed_raw": {"ru": "Вкладывать сырые логи в отчёт", "en": "Embed raw logs in report"},
    "scan": {"ru": "🔍  СКАНИРОВАТЬ", "en": "🔍  SCAN"},
    "export": {"ru": "📄  ОТЧЁТ В 1 ФАЙЛ", "en": "📄  REPORT TO 1 FILE"},
    "ready": {"ru": "Готов к сканированию.", "en": "Ready to scan."},
    "pick_inst": {"ru": "Папка инстанса MO2", "en": "MO2 instance folder"},
    "pick_game": {"ru": "Папка игры Cyberpunk 2077", "en": "Cyberpunk 2077 game folder"},
    "tab_sum": {"ru": "  Сводка  ", "en": "  Summary  "},
    "tab_grp": {"ru": "  По модам  ", "en": "  By mod  "},
    "tab_lf": {"ru": "  Не загрузилось ⚠  ", "en": "  Didn't load ⚠  "},
    "tab_err": {"ru": "  Все ошибки  ", "en": "  All errors  "},
    "tab_comp": {"ru": "  Совместимость  ", "en": "  Compatibility  "},
    "tab_dmp": {"ru": "  Дампы и логи  ", "en": "  Dumps & logs  "},
    "col_modsrc": {"ru": "Мод / источник", "en": "Mod / source"},
    "col_errors": {"ru": "Ошибки (×повторы)", "en": "Errors (×repeats)"},
    "col_warn": {"ru": "Предупр.", "en": "Warnings"},
    "col_type": {"ru": "Тип", "en": "Type"},
    "col_n": {"ru": "×N", "en": "×N"},
    "col_msg": {"ru": "Сообщение", "en": "Message"},
    "col_name": {"ru": "Имя", "en": "Name"},
    "col_when": {"ru": "Изменён", "en": "Changed"},
    "col_size": {"ru": "Размер", "en": "Size"},
    "lf_hint": {"ru": "Это готовый отчёт о несовместимых модах: что не загрузилось/не скомпилировалось.",
                "en": "This is a ready compatibility report: what failed to load / compile."},
    "scanning": {"ru": "Сканирую…", "en": "Scanning…"},
    "scan_done": {"ru": "Готово: {} логов · {} видов ошибок ({}×) · не загрузилось: {} · дампов: {}",
                  "en": "Done: {} logs · {} error types ({}×) · failed to load: {} · dumps: {}"},
    "scan_err": {"ru": "Ошибка: {}", "en": "Error: {}"},
    "scan_err_t": {"ru": "Ошибка сканирования", "en": "Scan error"},
    "exp_need_scan": {"ru": "Сначала нажми «Сканировать».", "en": "Press “Scan” first."},
    "exp_title": {"ru": "Сохранить отчёт одним файлом", "en": "Save report to one file"},
    "exp_making": {"ru": "Формирую отчёт…", "en": "Generating report…"},
    "exp_saved_status": {"ru": "Отчёт сохранён: {} ({})", "en": "Report saved: {} ({})"},
    "exp_done_t": {"ru": "Готово", "en": "Done"},
    "exp_done_msg": {"ru": "Отчёт сохранён ({}):\n{}\n\nОткрыть папку с файлом?",
                     "en": "Report saved ({}):\n{}\n\nOpen containing folder?"},
    "exp_err": {"ru": "Ошибка экспорта: {}", "en": "Export error: {}"},
    "exp_err_t": {"ru": "Ошибка экспорта", "en": "Export error"},
    "export_t": {"ru": "Экспорт", "en": "Export"},
    "sum_h": {"ru": "СВОДКА", "en": "SUMMARY"},
    "sum_logs": {"ru": "Просканировано логов: {}", "en": "Logs scanned: {}"},
    "sum_err": {"ru": "Значимых ошибок: ", "en": "Significant errors: "},
    "sum_types_total": {"ru": "{} видов / {} всего\n", "en": "{} types / {} total\n"},
    "sum_warn": {"ru": "Предупреждений: ", "en": "Warnings: "},
    "sum_cos": {"ru": "Косметика (декали/материалы): {} видов / {} всего {}\n",
                "en": "Cosmetic (decals/materials): {} types / {} total {}\n"},
    "hidden": {"ru": "[скрыта]", "en": "[hidden]"},
    "sum_lf": {"ru": "Не загрузилось/не скомпилировалось: ", "en": "Failed to load/compile: "},
    "sum_dmp": {"ru": "Крэш-дампов: {}\n", "en": "Crash dumps: {}\n"},
    "sum_top": {"ru": "ТОП модов по ошибкам", "en": "TOP mods by errors"},
    "sum_no_err": {"ru": "  ✓ значимых ошибок нет", "en": "  ✓ no significant errors"},
    "sum_causes": {"ru": "ВОЗМОЖНЫЕ ПРИЧИНЫ ВЫЛЕТОВ", "en": "POSSIBLE CRASH CAUSES"},
    "sum_no_causes": {"ru": "  ✓ типовых причин не найдено.\n", "en": "  ✓ no typical causes found.\n"},
    "lf_none": {"ru": "✓ Ничего не упало при загрузке — несовместимых модов не найдено.",
                "en": "✓ Nothing failed at load — no incompatible mods found."},
    "cosmetic_w": {"ru": "косметика", "en": "cosmetic"},
    "comp_h": {"ru": "ВЕРСИИ ФРЕЙМВОРКОВ", "en": "FRAMEWORK VERSIONS"},
    "comp_game": {"ru": "Версия игры: {}\n", "en": "Game version: {}\n"},
    "not_detected": {"ru": "не определён (нет в логах)", "en": "not detected (not in logs)"},
    "guide_ge": {"ru": "ориентир ≥", "en": "reference ≥"},
    "comp_note": {"ru": "\n⚠ «ориентир» — это ПРИМЕРНЫЕ свежие версии, не жёсткое требование. "
                        "Правь их под свой патч в scanner_config.json → \"recommended\".\n",
                  "en": "\n⚠ “reference” values are APPROXIMATE up-to-date versions, not hard requirements. "
                        "Edit them for your patch in scanner_config.json → \"recommended\".\n"},
    "comp_folders": {"ru": "Просканированные папки:", "en": "Scanned folders:"},
    "prob_redscript": {"ru": "Ошибка компиляции redscript — частая причина чёрного экрана/вылета при загрузке. "
                             "Обычно виноват устаревший скрипт-мод.",
                       "en": "redscript compilation error — a common cause of black screen/crash on load. "
                             "Usually an outdated script mod."},
    "prob_plugin": {"ru": "Плагин RED4ext не загрузился — мод несовместим с патчем игры или нет зависимости.",
                    "en": "A RED4ext plugin failed to load — mod is incompatible with the game patch or a dependency is missing."},
    "prob_version": {"ru": "Несовпадение версий — мод собран под другой патч. Обнови мод или фреймворк.",
                     "en": "Version mismatch — mod built for a different patch. Update the mod or framework."},
    "prob_missing_class": {"ru": "Скрипт ссылается на отсутствующий класс/метод — нужен фреймворк-зависимость или новее мод.",
                           "en": "A script references a missing class/method — a framework dependency or newer mod is required."},
    "prob_av": {"ru": "Жёсткий краш движка (access violation) — чаще конфликт архив-модов или битый .archive.",
                "en": "Hard engine crash (access violation) — usually an archive-mod conflict or a broken .archive."},
    "prob_archive": {"ru": "Не найден .archive — неполная установка или отсутствует зависимость.",
                     "en": "Missing .archive — incomplete install or a missing dependency."},
    "prob_nca_spawn": {"ru": "NCA (Night City Allies): сбой стейт-машины компаньонов. "
                             "Вызывает вылеты в конкретных локациях (Lizzie's, El Coyote и т.п.). "
                             "Переустанови NCA свежей версией.",
                       "en": "NCA (Night City Allies): companion spawn state machine error. "
                             "Causes location-specific crashes (Lizzie's, El Coyote, etc.). "
                             "Reinstall NCA with the latest version."},
    "prob_redscript_lbl":     {"ru": "ошибка компиляции redscript",        "en": "redscript compile error"},
    "prob_plugin_lbl":        {"ru": "плагин RED4ext не загрузился",        "en": "RED4ext plugin failed to load"},
    "prob_version_lbl":       {"ru": "несовместимая версия (не тот патч)",  "en": "version mismatch (wrong patch)"},
    "prob_missing_class_lbl": {"ru": "отсутствует класс/метод в скриптах", "en": "missing class/method in scripts"},
    "prob_av_lbl":            {"ru": "краш движка (access violation)",      "en": "engine crash (access violation)"},
    "prob_archive_lbl":       {"ru": "отсутствует .archive",                "en": "missing .archive file"},
    "prob_nca_spawn_lbl":     {"ru": "NCA: сбой стейт-машины компаньонов", "en": "NCA: companion state machine error"},
    "vortex_status":   {"ru": "Vortex:", "en": "Vortex:"},
    "vortex_found":    {"ru": "обнаружен ✓  ({})", "en": "detected ✓  ({})"},
    "vortex_missing":  {"ru": "не найден (MO2-поле обязательно)", "en": "not found (MO2 field required)"},
}


def T(key, *args):
    d = TR.get(key)
    s = (d.get(CURRENT_LANG) or d.get("ru")) if d else key
    return s.format(*args) if args else s


# --- модель -------------------------------------------------------------------
class Finding:
    __slots__ = ("source", "severity", "text", "count", "cosmetic", "is_load_fail", "path", "line_no")

    def __init__(self, source, severity, text, cosmetic, is_load_fail, path, line_no):
        self.source = source
        self.severity = severity
        self.text = text.rstrip()
        self.count = 1
        self.cosmetic = cosmetic
        self.is_load_fail = is_load_fail
        self.path = path
        self.line_no = line_no


class ScanResult:
    def __init__(self):
        self.findings = []
        self.by_source = {}
        self.load_fails = []
        self.dumps = []
        self.versions = {}
        self.recommended = {}
        self.problems = []
        self.scanned_files = 0
        self.log_files = []
        self.roots = []
        self.err_unique = self.err_occ = 0
        self.warn_unique = self.warn_occ = 0
        self.cosmetic_unique = self.cosmetic_occ = 0


# --- утилиты ------------------------------------------------------------------
def load_config():
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def parse_game_path(instance_dir):
    ini = os.path.join(instance_dir or "", "ModOrganizer.ini")
    if not os.path.isfile(ini):
        return None
    try:
        with open(ini, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip().startswith("gamePath="):
                    val = line.split("=", 1)[1].strip()
                    m = re.search(r"@ByteArray\((.*)\)", val)
                    if m:
                        val = m.group(1)
                    return val.replace("\\\\", "\\").strip()
    except Exception:
        return None
    return None


def _win_file_version(path):
    try:
        import ctypes
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return None
        p, n = ctypes.c_void_p(), ctypes.c_uint()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(p), ctypes.byref(n)):
            return None
        nums = ctypes.cast(p, ctypes.POINTER(ctypes.c_ushort * 8)).contents
        a, b, c = nums[1], nums[0], nums[3]
        return f"{a}.{b}.{c}"
    except Exception:
        return None


def detect_vortex_dir():
    cp_dir = os.path.join(VORTEX_APPDATA, "cyberpunk2077")
    return cp_dir if os.path.isdir(cp_dir) else None


def collect_scan_dirs(instance_dir, game_dir):
    dirs = []
    if instance_dir:
        dirs += [os.path.join(instance_dir, "overwrite"),
                 os.path.join(instance_dir, "logs"),
                 os.path.join(instance_dir, "crashDumps")]
    if game_dir:
        dirs += [os.path.join(game_dir, "red4ext", "logs"),
                 os.path.join(game_dir, "r6", "logs"),
                 os.path.join(game_dir, "bin", "x64", "plugins"),
                 os.path.join(game_dir, "bin", "x64")]
    vortex_dir = detect_vortex_dir()
    if vortex_dir:
        dirs.append(vortex_dir)
    return [d for d in dirs if os.path.isdir(d)]


def read_tail(path, max_bytes=MAX_READ_BYTES):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()
            return f.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"<read error: {e}>"


def read_capped(path, cap):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            truncated = size > cap
            if truncated:
                f.seek(size - cap)
                f.readline()
            return f.read().decode("utf-8", errors="replace"), truncated, size
    except Exception as e:
        return f"<read error: {e}>", False, 0


DATE_SUFFIX = re.compile(r"-\d{4}-\d{2}-\d{2}.*$")
BRACKET_PREFIX = re.compile(r"^\s*(\[[^\]]*\]\s*)+")
REDS_MOD = re.compile(r"([^\\/]+)[\\/].+\.reds", re.IGNORECASE)
CET_MOD = re.compile(r"[\\/]cyber_engine_tweaks[\\/]mods[\\/]([^\\/]+)[\\/]", re.IGNORECASE)


def norm_text(text):
    return BRACKET_PREFIX.sub("", text).strip().lower()


def source_for(path, text):
    low = path.replace("\\", "/").lower()
    base = os.path.basename(path)
    stem = DATE_SUFFIX.sub("", base)
    stem = re.sub(r"\.(log|txt)$", "", stem, flags=re.IGNORECASE)
    m = CET_MOD.search(path)
    if m:
        return "CET: " + m.group(1)
    if "cyber_engine_tweaks" in low:
        return "CET (core)"
    if "redscript" in base.lower() or "/r6/logs/" in low:
        mm = REDS_MOD.match(text.strip())
        if mm:
            return "redscript: " + mm.group(1).strip()
        return "redscript"
    fw_map = {"archivexl": "ArchiveXL", "tweakxl": "TweakXL",
              "codeware": "Codeware", "red4ext": "RED4ext (loader)"}
    if stem.lower() in fw_map:
        return fw_map[stem.lower()]
    if "/red4ext/logs/" in low:
        return "RED4ext: " + stem
    return stem or base


def vtuple(v):
    parts = re.findall(r"\d+", v or "")
    return tuple(int(x) for x in parts) if parts else None


def version_status(installed, recommended):
    if not installed:
        return "unknown"
    iv, rv = vtuple(installed), vtuple(recommended)
    if not iv or not rv:
        return "ok"
    n = max(len(iv), len(rv))
    iv += (0,) * (n - len(iv))
    rv += (0,) * (n - len(rv))
    return "old" if iv < rv else "ok"


def scan(instance_dir, game_dir, recent_only=False):
    res = ScanResult()
    cfg = load_config()
    res.recommended = {**DEFAULT_RECOMMENDED, **(cfg.get("recommended") or {})}
    res.roots = collect_scan_dirs(instance_dir, game_dir)

    _seen_paths: set = set()
    log_paths = []
    for d in res.roots:
        for root, _, files in os.walk(d):
            for name in files:
                full = os.path.join(root, name)
                # Deduplicate: bin/x64/plugins is walked twice (via bin/x64 and directly)
                if full in _seen_paths:
                    continue
                _seen_paths.add(full)
                low = name.lower()
                if low.endswith(".dmp"):
                    try:
                        st = os.stat(full)
                        res.dumps.append((full, st.st_mtime, st.st_size))
                    except OSError:
                        pass
                elif low.endswith((".log", ".txt")):
                    # Skip documentation/license files — they are not logs
                    stem = re.sub(r"\.(log|txt)$", "", low)
                    if stem in SKIP_STEMS:
                        continue
                    try:
                        mt = os.path.getmtime(full)
                    except OSError:
                        mt = 0
                    log_paths.append((full, mt))

    if recent_only and log_paths:
        newest = max(mt for _, mt in log_paths)
        cutoff = newest - 2 * 3600
        log_paths = [(p, mt) for p, mt in log_paths if mt >= cutoff]

    log_paths.sort(key=lambda x: x[1], reverse=True)
    res.log_files = log_paths

    raw = {}
    seen: set = set()
    for path, mt in log_paths:
        res.scanned_files += 1
        content = read_tail(path)
        for name, pat in VERSION_PATTERNS:
            if name not in res.versions:
                m = pat.search(content)
                if m:
                    res.versions[name] = m.group(1)
        for i, line in enumerate(content.splitlines(), 1):
            if not line.strip():
                continue
            sev = None
            # Explicit [error]/[warning] tags in the log format take priority over heuristic regexes.
            # This prevents e.g. "[warning] Type mismatch..." from being mis-classified as ERROR.
            if EXPLICIT_ERROR_RE.search(line) and not NOISE_RE.search(line):
                sev = "ERROR"
            elif EXPLICIT_WARN_RE.search(line):
                sev = "WARN"
            elif ERROR_RE.search(line) and not NOISE_RE.search(line):
                sev = "ERROR"
            elif WARN_RE.search(line):
                sev = "WARN"
            if not sev:
                continue
            cosmetic = bool(COSMETIC_RE.search(line))
            src = source_for(path, line)
            key = (sev, src, norm_text(line))
            f = raw.get(key)
            if f:
                f.count += 1
                continue
            is_lf = (sev == "ERROR" and not cosmetic and bool(LOAD_FAIL_RE.search(line)))
            raw[key] = Finding(src, sev, line, cosmetic, is_lf, path, i)
            for hpat, pkey in HEURISTICS:
                if not cosmetic and hpat.search(line):
                    pair = (src, pkey)
                    if pair not in seen:
                        seen.add(pair)
                        res.problems.append(pair)

    if "redscript" not in res.versions and game_dir:
        for rspath in [
            os.path.join(game_dir, "engine", "tools", "scc.exe"),
            os.path.join(game_dir, "tools", "redmod", "bin", "scc.exe"),
        ]:
            if os.path.isfile(rspath):
                ver = _win_file_version(rspath)
                if ver:
                    res.versions["redscript"] = ver
                    break

    findings = list(raw.values())
    findings.sort(key=lambda f: (not f.is_load_fail, f.severity != "ERROR", -f.count))
    res.findings = findings
    res.load_fails = [f for f in findings if f.is_load_fail]

    for f in findings:
        agg = res.by_source.setdefault(f.source, {"err_u": 0, "warn_u": 0, "err_o": 0,
                                                   "warn_o": 0, "cos_o": 0, "samples": []})
        if f.severity == "ERROR":
            if f.cosmetic:
                res.cosmetic_unique += 1
                res.cosmetic_occ += f.count
                agg["cos_o"] += f.count
            else:
                res.err_unique += 1
                res.err_occ += f.count
                agg["err_u"] += 1
                agg["err_o"] += f.count
        else:
            res.warn_unique += 1
            res.warn_occ += f.count
            agg["warn_u"] += 1
            agg["warn_o"] += f.count
        if len(agg["samples"]) < 40:
            agg["samples"].append(f)

    res.dumps.sort(key=lambda x: x[1], reverse=True)
    return res


# --- сводный отчёт ------------------------------------------------------------
def build_report(res, instance, game, include_raw=True):
    L = []
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    L += ["=" * 72, "CP77 CRASH SCANNER — REPORT", f"Date: {now}",
          f"MO2 instance: {instance}", f"Game: {game}",
          f"Game version: {res.versions.get('Game', '-')}", "=" * 72, "",
          f"Logs scanned: {res.scanned_files}",
          f"Significant errors: {res.err_unique} types / {res.err_occ} total",
          f"Cosmetic: {res.cosmetic_unique} types / {res.cosmetic_occ} total",
          f"Failed to load/compile: {len(res.load_fails)}",
          f"Crash dumps: {len(res.dumps)}", ""]

    L.append("--- FRAMEWORK VERSIONS ---")
    for name in CORE_FRAMEWORKS:
        st = version_status(res.versions.get(name), res.recommended.get(name))
        inst = res.versions.get(name)
        if st == "unknown":
            L.append(f"  [?] {name}: not detected")
        elif st == "old":
            L.append(f"  [OUTDATED?] {name}: {inst} (reference >= {res.recommended.get(name)})")
        else:
            L.append(f"  [OK] {name}: {inst}")
    L.append("")

    if res.problems:
        L.append("--- POSSIBLE CRASH CAUSES ---")
        for src, pkey in res.problems:
            L.append(f"  * [{src}] {TR[pkey]['en']}")
        L.append("")

    L.append(f"--- FAILED TO LOAD / COMPILE ({len(res.load_fails)}) ---")
    if not res.load_fails:
        L.append("  (none)")
    for f in res.load_fails:
        L.append(f"  [{f.source}] x{f.count}  {f.text.strip()}")
    L.append("")

    L.append("--- TOP MODS BY ERRORS ---")
    for src, a in sorted(res.by_source.items(), key=lambda kv: -kv[1]["err_o"]):
        if a["err_o"] > 0:
            L.append(f"  {a['err_o']:>6}x  {src}  ({a['err_u']} types)")
    L.append("")

    L.append("--- ALL SIGNIFICANT ERRORS (deduped, no cosmetic) ---")
    for f in res.findings:
        if not f.cosmetic:
            L.append(f"  [{f.severity}] x{f.count} [{f.source}] {f.text.strip()}")
    L.append("")

    if res.dumps:
        L.append("--- CRASH DUMPS ---")
        for p, mt, size in res.dumps:
            when = dt.datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M:%S")
            L.append(f"  {when}  {os.path.basename(p)}  ({size} bytes)  {p}")
        L.append("")

    if include_raw:
        L += ["", "=" * 72, "RAW LOGS", "=" * 72]
        for p, mt in res.log_files:
            data, trunc, size = read_capped(p, REPORT_PER_LOG_CAP)
            when = dt.datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M:%S") if mt else "?"
            note = "  (truncated to last 400KB)" if trunc else ""
            L += ["", "#" * 72, f"# FILE: {p}", f"# changed: {when}  size: {size} bytes{note}",
                  "#" * 72, data]
    return "\n".join(L)


# --- CLI ----------------------------------------------------------------------
def _utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run_cli():
    _utf8_stdout()
    cfg = load_config()
    inst = cfg.get("instance", DEFAULT_INSTANCE)
    game = cfg.get("game") or parse_game_path(inst)
    print(f"Instance: {inst}\nGame: {game}")
    res = scan(inst, game)
    print(f"\nLogs: {res.scanned_files} | dumps: {len(res.dumps)}")
    print(f"Significant errors: {res.err_unique} types / {res.err_occ} total")
    print(f"Cosmetic (hidden): {res.cosmetic_unique} types / {res.cosmetic_occ} total")
    print(f"Versions: {res.versions}")
    print("\nTOP sources by errors:")
    for src, a in sorted(res.by_source.items(), key=lambda kv: -kv[1]["err_o"])[:10]:
        if a["err_o"]:
            print(f"  {a['err_o']:6d}x  {src}")
    print(f"\nFAILED TO LOAD/COMPILE: {len(res.load_fails)}")
    for f in res.load_fails[:15]:
        print(f"  [{f.source}] x{f.count}  {f.text[:140]}")
    return 0


def run_report_cli():
    _utf8_stdout()
    cfg = load_config()
    inst = cfg.get("instance", DEFAULT_INSTANCE)
    game = cfg.get("game") or parse_game_path(inst)
    res = scan(inst, game)
    out = os.path.join(os.path.dirname(CONFIG_PATH),
                       f"CP77_report_{dt.datetime.now():%Y%m%d_%H%M%S}.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_report(res, inst, game, include_raw=True))
    print(f"Report saved: {out} ({os.path.getsize(out)} bytes)")
    return 0


# --- GUI ----------------------------------------------------------------------
def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    global CURRENT_LANG
    BG = "#1e1f22"; FG = "#e6e6e6"; ACC = "#4cc38a"; ERRC = "#ff6b6b"; WARNC = "#ffd166"; PANEL = "#2b2d31"
    GITHUB_URL = "https://github.com/dw1rf"

    cfg = load_config()
    CURRENT_LANG = cfg.get("lang", "ru")
    inst0 = cfg.get("instance", DEFAULT_INSTANCE)
    state = {"result": None,
             "instance": inst0,
             "game": cfg.get("game") or parse_game_path(inst0) or ""}

    root = tk.Tk()
    root.title("CP77 Crash Scanner")
    root.geometry("1180x760")
    root.configure(bg=BG)

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background=BG, foreground=FG, fieldbackground=PANEL)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("TButton", background=PANEL, foreground=FG, padding=6)
    style.map("TButton", background=[("active", ACC)], foreground=[("active", "#101010")])
    style.configure("TCheckbutton", background=BG, foreground=FG)
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=FG,
                    selectbackground=ACC, selectforeground="#101010")
    style.map("TCombobox",
              fieldbackground=[("readonly", PANEL), ("disabled", BG)],
              foreground=[("readonly", FG), ("disabled", "#666")],
              selectbackground=[("readonly", ACC)],
              selectforeground=[("readonly", "#101010")])
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=PANEL, foreground=FG, padding=(13, 7))
    style.map("TNotebook.Tab", background=[("selected", ACC)], foreground=[("selected", "#101010")])
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=22, borderwidth=0)
    style.configure("Treeview.Heading", background=BG, foreground=ACC, font=("Segoe UI", 9, "bold"))
    style.map("Treeview", background=[("selected", "#3a5f4a")])

    inst_var = tk.StringVar(value=state["instance"])
    game_var = tk.StringVar(value=state["game"])
    recent_var = tk.BooleanVar(value=False)
    hide_cos_var = tk.BooleanVar(value=True)
    incl_raw_var = tk.BooleanVar(value=True)
    status_var = tk.StringVar(value=T("ready"))

    holder = {}  # ссылки на пересоздаваемые виджеты

    def human_size(n):
        for u in ("Б", "КБ", "МБ", "ГБ") if CURRENT_LANG == "ru" else ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.0f} {u}"
            n /= 1024
        return f"{n:.1f} TB"

    def build_ui():
        for w in root.winfo_children():
            w.destroy()
        paths = {}

        top = ttk.Frame(root, padding=10); top.pack(fill="x")

        def pick_instance():
            d = filedialog.askdirectory(title=T("pick_inst"), initialdir=inst_var.get() or "C:/")
            if d:
                inst_var.set(d)
                g = parse_game_path(d)
                if g:
                    game_var.set(g)

        def pick_game():
            d = filedialog.askdirectory(title=T("pick_game"), initialdir=game_var.get() or "C:/")
            if d:
                game_var.set(d)

        ttk.Label(top, text=T("instance")).grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=inst_var, width=72).grid(row=0, column=1, padx=6, sticky="we")
        ttk.Button(top, text="…", width=3, command=pick_instance).grid(row=0, column=2)
        ttk.Label(top, text=T("game")).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(top, textvariable=game_var, width=72).grid(row=1, column=1, padx=6, sticky="we", pady=(6, 0))
        ttk.Button(top, text="…", width=3, command=pick_game).grid(row=1, column=2, pady=(6, 0))
        top.columnconfigure(1, weight=1)

        # язык — обрамляем в LabelFrame для видимой рамки
        lang_frame = tk.LabelFrame(top, text=T("language"), bg=BG, fg=ACC,
                                   bd=1, relief="solid", padx=6, pady=2)
        lang_frame.grid(row=0, column=3, padx=(10, 0), sticky="e")
        lang_cb = ttk.Combobox(lang_frame, width=10, state="readonly", values=["Русский", "English"])
        lang_cb.set("Русский" if CURRENT_LANG == "ru" else "English")
        lang_cb.pack()

        def on_lang(_e):
            global CURRENT_LANG
            CURRENT_LANG = "ru" if lang_cb.get() == "Русский" else "en"
            c = load_config(); c["lang"] = CURRENT_LANG; save_config(c)
            build_ui()
            if state["result"]:
                holder["render"](state["result"])
        lang_cb.bind("<<ComboboxSelected>>", on_lang)

        optrow = ttk.Frame(top); optrow.grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Checkbutton(optrow, text=T("only_recent"), variable=recent_var).pack(side="left")
        ttk.Checkbutton(optrow, text=T("hide_cos"), variable=hide_cos_var,
                        command=lambda: state["result"] and holder["render"](state["result"])).pack(side="left", padx=(16, 0))
        ttk.Checkbutton(optrow, text=T("embed_raw"), variable=incl_raw_var).pack(side="left", padx=(16, 0))

        nb = ttk.Notebook(root); nb.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        tab_sum = ttk.Frame(nb, padding=10); nb.add(tab_sum, text=T("tab_sum"))
        sum_text = tk.Text(tab_sum, bg=PANEL, fg=FG, wrap="word", relief="flat", font=("Consolas", 10),
                           cursor="xterm")
        sum_text.pack(fill="both", expand=True)
        for tag, col in (("h", ACC), ("err", ERRC), ("warn", WARNC), ("ok", ACC)):
            sum_text.tag_config(tag, foreground=col)
        sum_text.tag_config("h", font=("Segoe UI", 12, "bold"))

        def _block_edit(e):
            if e.state & 4 or e.keysym in (
                    "Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End"):
                return
            return "break"
        sum_text.bind("<Key>", _block_edit)

        tab_grp = ttk.Frame(nb, padding=6); nb.add(tab_grp, text=T("tab_grp"))
        gtree = ttk.Treeview(tab_grp, columns=("err", "warn"), show="tree headings")
        gtree.heading("#0", text=T("col_modsrc")); gtree.column("#0", width=560, anchor="w")
        gtree.heading("err", text=T("col_errors")); gtree.column("err", width=160, anchor="center")
        gtree.heading("warn", text=T("col_warn")); gtree.column("warn", width=110, anchor="center")
        gtree.tag_configure("ERR", foreground=ERRC); gtree.tag_configure("WARN", foreground=WARNC)
        gv = ttk.Scrollbar(tab_grp, orient="vertical", command=gtree.yview); gtree.configure(yscrollcommand=gv.set)
        gtree.pack(side="left", fill="both", expand=True); gv.pack(side="right", fill="y")

        tab_lf = ttk.Frame(nb, padding=6); nb.add(tab_lf, text=T("tab_lf"))
        ttk.Label(tab_lf, text=T("lf_hint")).pack(anchor="w", pady=(0, 4))
        lftree = ttk.Treeview(tab_lf, columns=("src", "cnt", "msg"), show="headings")
        for c, w, t in [("src", 240, T("col_modsrc")), ("cnt", 60, T("col_n")), ("msg", 760, T("col_msg"))]:
            lftree.heading(c, text=t); lftree.column(c, width=w, anchor="w")
        lftree.tag_configure("LF", foreground=ERRC)
        lv = ttk.Scrollbar(tab_lf, orient="vertical", command=lftree.yview); lftree.configure(yscrollcommand=lv.set)
        lftree.pack(side="left", fill="both", expand=True); lv.pack(side="right", fill="y")

        tab_err = ttk.Frame(nb, padding=6); nb.add(tab_err, text=T("tab_err"))
        tree = ttk.Treeview(tab_err, columns=("sev", "cnt", "src", "text"), show="headings")
        for c, w, t in [("sev", 60, T("col_type")), ("cnt", 55, T("col_n")),
                        ("src", 220, T("col_modsrc")), ("text", 760, T("col_msg"))]:
            tree.heading(c, text=t); tree.column(c, width=w, anchor="w")
        tree.tag_configure("ERROR", foreground=ERRC); tree.tag_configure("WARN", foreground=WARNC)
        ev = ttk.Scrollbar(tab_err, orient="vertical", command=tree.yview); tree.configure(yscrollcommand=ev.set)
        tree.pack(side="left", fill="both", expand=True); ev.pack(side="right", fill="y")

        tab_comp = ttk.Frame(nb, padding=10); nb.add(tab_comp, text=T("tab_comp"))
        comp_text = tk.Text(tab_comp, bg=PANEL, fg=FG, wrap="word", relief="flat", font=("Consolas", 10),
                            cursor="xterm")
        comp_text.pack(fill="both", expand=True)
        comp_text.bind("<Key>", _block_edit)
        comp_text.tag_config("h", foreground=ACC, font=("Segoe UI", 12, "bold"))
        comp_text.tag_config("ok", foreground=ACC); comp_text.tag_config("bad", foreground=ERRC)
        comp_text.tag_config("warn", foreground=WARNC)

        tab_dmp = ttk.Frame(nb, padding=6); nb.add(tab_dmp, text=T("tab_dmp"))
        dtree = ttk.Treeview(tab_dmp, columns=("type", "name", "when", "size"), show="headings")
        for c, w, t in [("type", 70, T("col_type")), ("name", 360, T("col_name")),
                        ("when", 160, T("col_when")), ("size", 100, T("col_size"))]:
            dtree.heading(c, text=t); dtree.column(c, width=w, anchor="w")
        dv = ttk.Scrollbar(tab_dmp, orient="vertical", command=dtree.yview); dtree.configure(yscrollcommand=dv.set)
        dtree.pack(side="left", fill="both", expand=True); dv.pack(side="right", fill="y")

        def open_path(p):
            try:
                os.startfile(p)  # noqa
            except Exception as e:
                messagebox.showerror("Error", str(e))

        for tv in (tree, lftree, dtree, gtree):
            tv.bind("<Double-1>", lambda e, t=tv: (t.focus() in paths) and open_path(paths[t.focus()]))

        def render(res):
            hide_cos = hide_cos_var.get()
            paths.clear()

            sum_text.delete("1.0", "end")
            sum_text.insert("end", T("sum_h") + "\n", "h")
            sum_text.insert("end", "\n" + T("sum_logs", res.scanned_files) + "\n")
            sum_text.insert("end", T("sum_err"))
            sum_text.insert("end", T("sum_types_total", res.err_unique, res.err_occ), "err")
            sum_text.insert("end", T("sum_warn"))
            sum_text.insert("end", T("sum_types_total", res.warn_unique, res.warn_occ), "warn")
            sum_text.insert("end", T("sum_cos", res.cosmetic_unique, res.cosmetic_occ,
                                     T("hidden") if hide_cos else ""))
            sum_text.insert("end", T("sum_lf"))
            sum_text.insert("end", f"{len(res.load_fails)}\n", "err" if res.load_fails else "ok")
            sum_text.insert("end", T("sum_dmp", len(res.dumps)), "err" if res.dumps else "ok")

            sum_text.insert("end", "\n" + T("sum_top") + "\n", "h")
            shown = 0
            for src, a in sorted(res.by_source.items(), key=lambda kv: -kv[1]["err_o"]):
                if a["err_o"] <= 0:
                    continue
                sum_text.insert("end", f"\n  {a['err_o']:>6}×  {src}", "err")
                shown += 1
                if shown >= 12:
                    break
            if not shown:
                sum_text.insert("end", "\n" + T("sum_no_err"), "ok")

            sum_text.insert("end", "\n\n" + T("sum_causes") + "\n", "h")
            if res.problems:
                for src, pkey in res.problems:
                    lbl = T(pkey + "_lbl") if (pkey + "_lbl") in TR else pkey
                    sum_text.insert("end", f"\n  ⚠  {src}", "warn")
                    sum_text.insert("end", f"  →  {lbl}\n")
            else:
                sum_text.insert("end", "\n" + T("sum_no_causes"), "ok")

            gtree.delete(*gtree.get_children())
            for src, a in sorted(res.by_source.items(), key=lambda kv: -(kv[1]["err_o"])):
                if hide_cos and a["err_o"] == 0 and a["warn_o"] == 0:
                    continue
                errlabel = f"{a['err_u']} ({a['err_o']}×)" if a["err_u"] else (T("cosmetic_w") if a["cos_o"] else "—")
                parent = gtree.insert("", "end", text=src, values=(errlabel, a["warn_o"] or "—"),
                                      tags=("ERR" if a["err_o"] else ("WARN" if a["warn_o"] else ""),))
                for f in a["samples"]:
                    if hide_cos and f.cosmetic:
                        continue
                    child = gtree.insert(parent, "end", text=f"   ×{f.count}  {f.text[:150]}",
                                         values=("", ""), tags=(f.severity,))
                    paths[child] = f.path

            lftree.delete(*lftree.get_children())
            if not res.load_fails:
                lftree.insert("", "end", values=("—", "", T("lf_none")))
            for f in res.load_fails:
                iid = lftree.insert("", "end", values=(f.source, f.count, f.text[:500]), tags=("LF",))
                paths[iid] = f.path

            tree.delete(*tree.get_children())
            for f in res.findings:
                if hide_cos and f.cosmetic:
                    continue
                iid = tree.insert("", "end", values=(f.severity, f.count, f.source, f.text[:500]), tags=(f.severity,))
                paths[iid] = f.path

            comp_text.delete("1.0", "end")
            comp_text.insert("end", T("comp_h") + "\n", "h")
            comp_text.insert("end", "\n" + T("comp_game", res.versions.get("Game", "—")))
            for name in CORE_FRAMEWORKS:
                st = version_status(res.versions.get(name), res.recommended.get(name))
                inst = res.versions.get(name)
                if st == "unknown":
                    mark, txt, tag = "?", T("not_detected"), "bad"
                elif st == "old":
                    mark, txt, tag = "⚠", f"{inst}  ({T('guide_ge')} {res.recommended.get(name)})", "warn"
                else:
                    mark, txt, tag = "✓", inst, "ok"
                comp_text.insert("end", f"\n  {mark} {name}: ")
                comp_text.insert("end", txt + "\n", tag)
            comp_text.insert("end", T("comp_note"), "warn")
            vortex_path = detect_vortex_dir()
            comp_text.insert("end", "\n\n" + T("vortex_status") + "  ")
            if vortex_path:
                comp_text.insert("end", T("vortex_found", vortex_path) + "\n", "ok")
            else:
                comp_text.insert("end", T("vortex_missing") + "\n", "warn")

            comp_text.insert("end", "\n" + T("comp_folders") + "\n", "h")
            for d in res.roots:
                comp_text.insert("end", f"\n  • {d}")

            dtree.delete(*dtree.get_children())
            for p, mt, size in res.dumps:
                when = dt.datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M:%S")
                iid = dtree.insert("", "end", values=("DUMP", os.path.basename(p), when, human_size(size)))
                paths[iid] = p
            for p, mt in res.log_files:
                when = dt.datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M:%S") if mt else "?"
                try:
                    size = human_size(os.path.getsize(p))
                except OSError:
                    size = "?"
                iid = dtree.insert("", "end", values=("LOG", os.path.basename(p), when, size))
                paths[iid] = p

        holder["render"] = render

        def do_scan():
            inst, game = inst_var.get().strip(), game_var.get().strip()
            c = load_config(); c.update({"instance": inst, "game": game, "lang": CURRENT_LANG}); save_config(c)
            status_var.set(T("scanning")); scan_btn.config(state="disabled")

            def worker():
                try:
                    res = scan(inst, game, recent_only=recent_var.get())
                    state["result"] = res

                    def done():
                        render(res)
                        status_var.set(T("scan_done", res.scanned_files, res.err_unique,
                                         res.err_occ, len(res.load_fails), len(res.dumps)))
                        scan_btn.config(state="normal")
                    root.after(0, done)
                except Exception as e:
                    msg = str(e)
                    root.after(0, lambda: (status_var.set(T("scan_err", msg)),
                                           scan_btn.config(state="normal"),
                                           messagebox.showerror(T("scan_err_t"), msg)))
            threading.Thread(target=worker, daemon=True).start()

        def do_export():
            res = state["result"]
            if not res:
                messagebox.showinfo(T("export_t"), T("exp_need_scan"))
                return
            fname = f"CP77_report_{dt.datetime.now():%Y%m%d_%H%M%S}.txt"
            path = filedialog.asksaveasfilename(
                title=T("exp_title"), defaultextension=".txt", initialfile=fname,
                initialdir=os.path.dirname(CONFIG_PATH), filetypes=[("Text", "*.txt"), ("All", "*.*")])
            if not path:
                return
            status_var.set(T("exp_making"))

            def worker():
                try:
                    text = build_report(res, inst_var.get(), game_var.get(), include_raw=incl_raw_var.get())
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(text)
                    size = os.path.getsize(path)

                    def done():
                        status_var.set(T("exp_saved_status", path, human_size(size)))
                        if messagebox.askyesno(T("exp_done_t"), T("exp_done_msg", human_size(size), path)):
                            open_path(os.path.dirname(path))
                    root.after(0, done)
                except Exception as e:
                    msg = str(e)
                    root.after(0, lambda: (status_var.set(T("exp_err", msg)),
                                           messagebox.showerror(T("exp_err_t"), msg)))
            threading.Thread(target=worker, daemon=True).start()

        scan_btn = ttk.Button(top, text=T("scan"), command=do_scan)
        scan_btn.grid(row=1, column=3, padx=(10, 0), pady=(6, 0), sticky="e")
        ttk.Button(top, text=T("export"), command=do_export).grid(row=2, column=3, padx=(10, 0), pady=(6, 0), sticky="e")

        bottom = ttk.Frame(root); bottom.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(bottom, textvariable=status_var, anchor="w").pack(side="left", fill="x", expand=True)

        def open_github(e=None):
            import webbrowser; webbrowser.open(GITHUB_URL)

        gh_lbl = tk.Label(bottom, text="GitHub ↗", fg=ACC, bg=BG, cursor="hand2",
                          font=("Segoe UI", 9, "underline"))
        gh_lbl.pack(side="right")
        gh_lbl.bind("<Button-1>", open_github)

        if state["result"]:
            render(state["result"])

    build_ui()
    if os.path.isdir(inst_var.get()):
        root.after(350, lambda: _auto_scan(state, inst_var, game_var, recent_var, holder, root, status_var))

    root.mainloop()


def _auto_scan(state, inst_var, game_var, recent_var, holder, root, status_var):
    if state["result"] is not None:
        return
    status_var.set(T("scanning"))

    def worker():
        try:
            res = scan(inst_var.get().strip(), game_var.get().strip(), recent_only=recent_var.get())
            state["result"] = res
            root.after(0, lambda: (holder["render"](res),
                                   status_var.set(T("scan_done", res.scanned_files, res.err_unique,
                                                    res.err_occ, len(res.load_fails), len(res.dumps)))))
        except Exception as e:
            root.after(0, lambda: status_var.set(T("scan_err", str(e))))
    threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    if "--scan" in sys.argv:
        sys.exit(run_cli())
    if "--report" in sys.argv:
        sys.exit(run_report_cli())
    run_gui()
