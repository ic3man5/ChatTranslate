"""Spanish -> English translator for chat logged by the ChatTranslate addon.

WoW only writes addon data to disk on /reload or logout, so each time you
/reload this picks up the Spanish lines the addon logged since the last one and
translates them with the offline OPUS-MT model, which reads much better than the
addon's in-game word-by-word version. Nothing touches the game process.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL_DIR = HERE / "models" / "translate-es_en-1_9"

# --- terminal colors --------------------------------------------------------
DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"
CHANNEL_COLORS = {
    "trade": "\033[38;5;216m",
    "general": "\033[38;5;216m",
    "lookingforgroup": "\033[38;5;216m",
    "party": "\033[38;5;111m",
    "instance": "\033[38;5;208m",
    "raid": "\033[38;5;208m",
    "guild": "\033[38;5;77m",
    "officer": "\033[38;5;34m",
    "whisper": "\033[38;5;213m",
    "say": "\033[38;5;255m",
    "yell": "\033[38;5;203m",
}

LINK = re.compile(r"\|H[^|]*\|h(.*?)\|h")  # |Hitem:...|h[Silk Pack]|h -> [Silk Pack]
ESCAPES = re.compile(r"\|c(?:[0-9a-fA-F]{8}|n[A-Za-z0-9_]+:)|\|r|\|T.*?\|t|\|A.*?\|a|\|K.*?\|k")


def clean(text):
    return ESCAPES.sub("", LINK.sub(r"\1", text)).replace("||", "|")


def channel_color(channel):
    key = re.sub(r"^\d+\.\s*", "", channel).split(" ")[0].lower()
    return CHANNEL_COLORS.get(key, "\033[38;5;250m")


# --- chat slang the model doesn't know --------------------------------------
SLANG = {
    "q": "que", "k": "que", "ke": "que", "xq": "porque", "pq": "porque", "porq": "porque",
    "xfa": "por favor", "porfa": "por favor", "plis": "por favor", "pls": "por favor",
    "tb": "también", "tmb": "también", "tbn": "también", "x": "por", "d": "de",
    "ntp": "no te preocupes", "npi": "ni idea", "bn": "bien", "dnd": "dónde",
    "salu2": "saludos", "grax": "gracias", "grs": "gracias", "msj": "mensaje",
    "sq": "es que", "oe": "oye", "tqm": "te quiero mucho", "toy": "estoy", "pa": "para",
}
LAUGH = re.compile(r"\b(?:ja){2,}j?a?\b|\b(?:je){2,}\b", re.IGNORECASE)


def expand_slang(text):
    text = LAUGH.sub("haha", text)
    return re.sub(r"\b\w+\b", lambda m: SLANG.get(m.group(0).lower(), m.group(0)), text)


SENTENCE_SPLIT = re.compile(r"(?<=[!?…])(?![!?…])\s*(?=\S)|(?<=\.)\s+(?=\S)")


# --- translation ------------------------------------------------------------
class Translator:
    def __init__(self, threads):
        import ctranslate2
        from sacremoses import MosesDetokenizer, MosesPunctNormalizer, MosesTokenizer
        from subword_nmt.apply_bpe import BPE

        self.model = ctranslate2.Translator(str(MODEL_DIR / "model"), device="cpu", inter_threads=1, intra_threads=threads)
        self.norm, self.tok, self.detok = MosesPunctNormalizer("es"), MosesTokenizer("es"), MosesDetokenizer("en")
        with open(MODEL_DIR / "bpe.model", encoding="utf-8") as f:
            self.bpe = BPE(f)

    def translate_many(self, texts):
        """Translates a batch of messages in one model call."""
        sentences, owners = [], []
        for i, text in enumerate(texts):
            for s in SENTENCE_SPLIT.split(expand_slang(text)):
                if s.strip():
                    sentences.append(s.strip())
                    owners.append(i)
        if not sentences:
            return list(texts)
        batch = [self.bpe.segment_tokens(self.tok.tokenize(self.norm.normalize(s), escape=False)) for s in sentences]
        results = self.model.translate_batch(batch, beam_size=2, max_decoding_length=256)
        out = [[] for _ in texts]
        for owner, r in zip(owners, results):
            out[owner].append(self.detok.detokenize(" ".join(r.hypotheses[0]).replace("@@ ", "").split()))
        return [" ".join(parts) for parts in out]


# --- reading the addon's SavedVariables -------------------------------------
TOKEN = re.compile(rb'"((?:[^"\\]|\\.)*)"|--[^\n]*|([{}])|(-?\d+(?:\.\d+)?)|([A-Za-z_]\w*)', re.S)


def lua_unescape(raw):
    def sub(m):
        e = m.group(1)
        if e.isdigit():
            return bytes([int(e) & 0xFF])
        return {b"n": b"\n", b"t": b"\t", b"r": b"\r"}.get(e) or e

    return re.sub(rb"\\(\d{1,3}|.)", sub, raw, flags=re.S).decode("utf-8", "replace")


def read_log(path):
    """Returns ChatTranslateLog entries as (time, channel, author, message) tuples."""
    data = path.read_bytes()
    start = data.find(b"ChatTranslateLog")
    if start < 0:
        return []
    entries, current, depth = [], [], 0
    for m in TOKEN.finditer(data, start + len(b"ChatTranslateLog")):
        string, brace, number, name = m.groups()
        if depth == 0 and name is not None:
            return []  # ChatTranslateLog = nil
        if brace == b"{":
            depth += 1
            if depth == 2:
                current = []
        elif brace == b"}":
            if depth == 2 and current and len(current) >= 4:
                entries.append(tuple(current[:4]))
            depth -= 1
            if depth <= 0:
                break
        elif depth == 2:
            if string is not None:
                current.append(lua_unescape(string))
            elif number is not None:
                current.append(int(float(number)))
    return entries


def find_game_dir():
    """The game folder of a running Wow.exe (Linux/Wine: read from /proc)."""
    for proc in Path("/proc").iterdir() if Path("/proc").is_dir() else []:
        if not proc.name.isdigit():
            continue
        try:
            if re.search(rb"[\\/]Wow\.exe(\s|$)", (proc / "cmdline").read_bytes().split(b"\0")[0]):
                return Path(os.readlink(proc / "cwd"))
        except OSError:
            continue
    sys.exit("Couldn't find a running WoW. Start the game, or pass --saved with the path to\n"
             "WTF/Account/<ACCOUNT>/SavedVariables/ChatTranslate.lua")


def find_saved_file():
    game = find_game_dir()
    accounts = sorted((game / "WTF" / "Account").glob("*/SavedVariables"), key=lambda p: p.stat().st_mtime)
    existing = [a / "ChatTranslate.lua" for a in accounts if (a / "ChatTranslate.lua").exists()]
    if existing:
        return max(existing, key=lambda p: p.stat().st_mtime)
    return (accounts[-1] if accounts else game / "WTF") / "ChatTranslate.lua"


def follow(path, recent_seconds):
    """Yields lists of entries that are new since the last time WoW saved the file."""
    seen, last_mtime, first = set(), None, True
    if not path.exists():
        print(f"{DIM}Waiting for the addon's first save — type {RESET}{BOLD}/reload{RESET}{DIM} in WoW.{RESET}")
    while True:
        try:
            mtime = path.stat().st_mtime_ns
        except FileNotFoundError:
            mtime = None
        if mtime is not None and mtime != last_mtime:
            last_mtime = mtime
            time.sleep(0.3)  # let WoW finish writing
            try:
                entries = read_log(path)
            except OSError:
                entries = []
            new = [e for e in entries if e not in seen]
            seen.update(entries)
            if first:
                new = [e for e in new if e[0] >= time.time() - recent_seconds]
                first = False
                print(f"{DIM}Watching {path}\nTranslations appear here each time you /reload.{RESET}\n")
            if new:
                yield new
        time.sleep(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saved", type=Path, help="path to SavedVariables/ChatTranslate.lua (default: found automatically)")
    ap.add_argument("--recent", type=int, default=30, help="on start, also show lines from the last N minutes (default 30)")
    ap.add_argument("--threads", type=int, default=2, help="CPU threads for translation (default 2)")
    args = ap.parse_args()

    try:
        os.nice(10)  # let the game win any fight for CPU
    except OSError:
        pass
    translator = Translator(args.threads)
    path = args.saved or find_saved_file()

    for entries in follow(path, args.recent * 60):
        messages = [clean(e[3]) for e in entries]
        for (stamp, channel, speaker, _), original, english in zip(entries, messages, translator.translate_many(messages)):
            color = channel_color(channel)
            tag = f"[{channel}] " if channel else ""
            print(f"{DIM}{time.strftime('%H:%M', time.localtime(stamp))}{RESET} {color}{tag}{BOLD}{speaker}{RESET}{color}: {english}{RESET}")
            print(f"      {DIM}{original}{RESET}")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
