"""Builds the ChatTranslate addon's Spanish -> English word and phrase tables.

Words come from a 50k conversational frequency list (OpenSubtitles) plus the
OPUS-MT model's vocabulary; phrases are the most common 2-4 word sequences in
Tatoeba's everyday Spanish sentences. Each is translated with the offline model.
Hand-written entries below override it for chat phrases, slang and small words
the model glosses badly out of context. Writes Dict.lua and the TOC's file list.
"""

import bz2
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL_DIR = HERE / "models" / "translate-es_en-1_9"
DATA = HERE / "data"
OUT_DIR = HERE.parent  # the addon lives at the repository root
MAX_VOCAB = 26000  # model vocabulary is frequency ordered; the tail is mostly word fragments
MAX_FREQ_WORDS = 40000
NGRAM_LIMITS = {2: 12000, 3: 8000, 4: 4000}
# Constants are limited per function (65536 in LuaJIT, more in Lua 5.1), so Dict.lua wraps
# each block of entries in its own function. One file keeps the TOC unchanged, which
# matters because WoW only re-reads TOC files when the game restarts.
ENTRIES_PER_BLOCK = 15000

# Phrases ending in these glue badly onto the next word, so they're left to word-by-word.
BOUNDARY = set(
    "de la el los las un una unos unas en y e o u con del al mi tu su mis tus sus se lo le les me te nos a por para sin".split()
)
SEGMENT = re.compile(r"[^\wáéíóúüñ' ]+")
WORD_RE = re.compile(r"[a-záéíóúüñ]+")
CACHE = HERE / "build_cache.json"

# The model tends to end a fragment with an object it made up ("yo no tengo" -> "I don't
# have one"); such phrases are dropped unless the Spanish has a pronoun to account for it.
INVENTED_OBJECT = re.compile(r" (it|one|him|her|them|that)$")
HAS_PRONOUN = re.compile(r"\b(lo|la|los|las|le|les|uno|una|eso|esto|ello|él|ella|ellos|ellas|\w+(lo|la|los|las|le|les))\b")
NAMES = set("tom mary maría maria john juan ken ariel jim jack bob alice tony mike pedro carlos ana lucía lucia paul pablo josé jose luis miguel".split())

PHRASES = {
    "me gusta": "I like", "te gusta": "you like", "me encanta": "I love", "no lo se": "I don't know",
    "creo que": "I think", "tienes que": "you have to", "tenes que": "you have to",
    "tenemos que": "we have to", "que onda": "what's up", "a ver si": "let's see if",
    "lo mismo": "the same", "ya se": "I know", "no importa": "it doesn't matter",
    "te sigo": "I'm following you", "los sigo": "I'm following you", "vos solo": "by yourself",
    "me quede sin": "I ran out of", "nos quedamos sin": "we ran out of", "se hace tarde": "it's getting late",
    "no esta": "isn't", "no estoy": "I'm not", "no estamos": "we're not", "no estan": "they're not",
    "subir de nivel": "level up", "sube de nivel": "levels up",
    "por favor": "please", "por que": "why", "de nada": "you're welcome", "lo siento": "sorry",
    "no se": "I don't know", "no pasa nada": "no problem", "no te preocupes": "don't worry",
    "buenas noches": "good night", "buenos dias": "good morning", "buenas tardes": "good afternoon",
    "que tal": "how's it going", "como estas": "how are you", "como estan": "how are you all",
    "muchas gracias": "thanks a lot", "un momento": "one moment", "ahora vuelvo": "brb",
    "ya vuelvo": "brb", "me voy": "I'm leaving", "nos vemos": "see you", "hasta luego": "see you later",
    "tengo que": "I have to", "hay que": "we need to", "vamos a": "let's", "voy a": "I'm going to",
    "a ver": "let's see", "de acuerdo": "agreed", "claro que si": "of course", "por supuesto": "of course",
    "alguien sabe": "does anyone know", "me ayudas": "can you help me", "busco grupo": "looking for group",
    "buscamos tanque": "LF tank", "buscamos healer": "LF healer", "buscamos sanador": "LF healer",
    "otra vez": "again", "en serio": "seriously", "que pasa": "what's up", "que paso": "what happened",
    "es que": "it's that", "a lo mejor": "maybe", "tal vez": "maybe", "puede ser": "could be",
    "sin mana": "out of mana", "estoy muerto": "I'm dead", "me mori": "I died", "me muero": "I'm dying",
    "dame un momento": "give me a sec", "lo que": "what", "ya esta": "done", "ya voy": "coming",
    "espera un momento": "wait a moment", "no hay": "there isn't", "hay alguien": "is anyone",
    "alguien para": "anyone for", "quien me": "who can", "me puedes": "can you", "me podes": "can you",
    "me invitas": "can you invite me", "invitame": "invite me", "estoy listo": "I'm ready",
    "estamos listos": "we're ready", "no puedo": "I can't", "que hago": "what do I do",
    "donde esta": "where is", "donde estan": "where are", "cuanto cuesta": "how much",
    "cuanto vale": "how much", "a la vez": "at the same time", "de verdad": "really",
    "buena suerte": "good luck", "bien hecho": "well done", "buen trabajo": "good job",
    "que bueno": "nice", "que malo": "how bad", "muy bien": "very good", "mas o menos": "more or less",
    "no tengo": "I don't have", "no tenemos": "we don't have", "no quiero": "I don't want",
    "no puedes": "you can't", "no hay problema": "no problem", "me ayude": "help me",
    "me ayuden": "help me", "ayudame": "help me", "ayudenme": "help me", "se pone": "goes",
    "se fue": "left", "me fui": "I left", "se murio": "died", "nos morimos": "we died",
    "a matar": "to kill", "matar al": "kill the", "voy al": "I'm going to the", "de nuevo": "again",
    "ya casi": "almost", "casi muero": "I almost died", "sin vida": "low health", "que haces": "what are you doing",
}

WORDS = {
    # small words
    "de": "of", "la": "the", "el": "the", "los": "the", "las": "the", "y": "and", "e": "and",
    "en": "in", "que": "that", "del": "of the", "para": "for", "un": "a", "una": "a", "unos": "some",
    "unas": "some", "se": "", "lo": "it", "le": "him", "les": "them", "me": "me", "te": "you",
    "nos": "us", "mi": "my", "mis": "my", "tu": "your", "tus": "your", "su": "his", "sus": "their",
    "es": "is", "esta": "is", "estoy": "I am", "estas": "you are", "estamos": "we are",
    "estan": "they are", "soy": "I am", "eres": "you are", "somos": "we are", "son": "are",
    "no": "no", "por": "for", "con": "with", "sin": "without", "al": "to the", "a": "to", "o": "or",
    "u": "or", "pero": "but", "como": "how", "quien": "who", "donde": "where", "cuando": "when",
    "cuanto": "how much", "cual": "which", "porque": "because", "si": "if", "ya": "already",
    "muy": "very", "mas": "more", "menos": "less", "bien": "good", "mal": "bad", "hay": "there is",
    "tengo": "I have", "tienes": "you have", "tiene": "has", "tenemos": "we have",
    "necesito": "I need", "necesitamos": "we need", "quiero": "I want", "quieres": "do you want",
    "puedo": "I can", "puedes": "can you", "puede": "can", "podemos": "we can", "vamos": "let's go",
    "voy": "I'm going", "vas": "you go", "va": "goes", "hola": "hi", "gracias": "thanks",
    "alguien": "anyone", "nadie": "nobody", "todo": "all", "todos": "everyone", "aqui": "here",
    "ahi": "there", "alli": "there", "ahora": "now", "luego": "later", "despues": "after",
    "antes": "before", "tambien": "also", "solo": "only", "mucho": "a lot", "poco": "little",
    "otro": "another", "otra": "another", "este": "this", "ese": "that", "eso": "that",
    "esto": "this", "nada": "nothing", "algo": "something", "hoy": "today", "manana": "tomorrow",
    "yo": "I", "el": "the", "ella": "she", "ellos": "they", "usted": "you", "ustedes": "you all",
    # game words
    "grupo": "group", "mazmorra": "dungeon", "mazmorras": "dungeons", "tanque": "tank",
    "tanquear": "tank", "tankeo": "I tank", "sanador": "healer", "curandero": "healer",
    "mision": "quest", "misiones": "quests", "oro": "gold", "plata": "silver", "cobre": "copper",
    "gremio": "guild", "banda": "raid", "jefe": "boss", "botin": "loot", "nivel": "level",
    "subir": "go up", "hermano": "bro", "amigo": "friend", "amigos": "friends",
    "bueno": "good", "buenas": "hey", "vale": "ok", "dale": "go ahead", "venga": "come on",
    "espera": "wait", "esperen": "wait", "esperad": "wait", "ven": "come", "vente": "come",
    "muerto": "dead", "mori": "I died", "lento": "slow", "rapido": "fast", "cuidado": "careful",
    "perdon": "sorry", "invitar": "invite", "invita": "invite", "mascota": "pet",
    "montura": "mount", "bolsa": "bag", "bolsas": "bags", "vendo": "selling", "compro": "buying",
    "cambio": "trade", "busco": "looking for", "buscamos": "looking for", "falta": "need",
    "faltan": "need", "listo": "ready", "listos": "ready", "curar": "heal", "cura": "heal",
    "curame": "heal me", "aggro": "aggro", "mana": "mana", "pociones": "potions", "pocion": "potion",
    # Argentine / Rioplatense (voseo)
    "vos": "you", "sos": "you are", "tenes": "you have", "queres": "you want", "podes": "you can",
    "sabes": "you know", "decis": "you say", "estas": "you are", "anda": "go", "andate": "go away",
    "volve": "come back", "volves": "you come back", "veni": "come", "agarra": "grab",
    "agarras": "you grab", "agarrate": "grab", "mira": "look", "fijate": "check", "decime": "tell me",
    "che": "hey", "re": "really", "boludo": "dude", "pibe": "kid", "laburo": "work", "posta": "for real",
    "copado": "cool", "joya": "great", "bancame": "wait for me", "banca": "wait",
    # gamer Spanglish
    "pullear": "pull", "pullea": "pull", "pulleo": "I pull", "pulleas": "you pull", "pulleen": "pull",
    "lootear": "loot", "farmear": "farm", "buffear": "buff", "buffeame": "buff me", "healear": "heal",
    "hilear": "heal", "tanquea": "tanks", "stunear": "stun", "kitear": "kite", "resucitar": "resurrect",
    "resu": "res", "flechas": "arrows", "balas": "bullets",
    # chat slang
    "q": "that", "k": "that", "ke": "that", "xq": "because", "pq": "because", "porq": "because",
    "xfa": "please", "porfa": "please", "plis": "please", "pls": "please", "tb": "also",
    "tmb": "also", "tbn": "also", "x": "for", "d": "of", "ntp": "no worries", "npi": "no idea",
    "bn": "good", "dnd": "where", "salu2": "greetings", "grax": "thanks", "grs": "thanks",
    "msj": "message", "sq": "it's that", "oe": "hey", "tqm": "love you", "toy": "I'm",
    "pa": "for", "wey": "dude", "guey": "dude", "tio": "dude", "xd": "xD",
}

STRIP = str.maketrans("áéíóúüÁÉÍÓÚÜ", "aeiouuaeiouu")


def norm(s):
    return s.lower().translate(STRIP)


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def load_words():
    """Spanish words, most frequent first: subtitle frequency list, then model vocabulary."""
    words, seen = [], set()

    def add(w):
        if w not in seen and re.fullmatch(r"[a-záéíóúüñ]+", w) and (len(w) > 1 or w in "yeaou"):
            seen.add(w)
            words.append(w)

    with open(DATA / "es_50k.txt", encoding="utf-8") as f:
        for line in f:
            add(line.split(" ")[0].strip().lower())
            if len(words) >= MAX_FREQ_WORDS:
                break
    vocab = json.load(open(MODEL_DIR / "model" / "shared_vocabulary.json"))
    for t in [t for t in vocab if "@@" not in t][:MAX_VOCAB]:
        add(t)
    return words


def load_ngrams():
    """Most common n-grams in Tatoeba's Spanish sentences, as their most common spelling."""
    picked = []
    for n, limit in NGRAM_LIMITS.items():  # one pass per n keeps memory down
        counts = Counter()
        with bz2.open(DATA / "spa_sentences.tsv.bz2", "rt", encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                for segment in SEGMENT.split(parts[2].lower()):
                    toks = WORD_RE.findall(segment)
                    for i in range(len(toks) - n + 1):
                        gram = toks[i : i + n]
                        # chat drops accents, so "con él" would end up matching "con el"
                        if gram[-1] not in BOUNDARY and gram[0] not in ("y", "e", "o", "u") and "él" not in gram:
                            counts[" ".join(gram)] += 1
        by_key = {}
        for surface, c in counts.most_common(limit * 2):
            key = norm(surface)
            if key not in by_key:  # most_common order: first spelling seen is the most common one
                by_key[key] = (surface, c)
        best = sorted(by_key.values(), key=lambda sc: -sc[1])[:limit]
        picked += [s for s, _ in best]
        print(f"  {n}-grams: kept {len(best)}, least common seen {best[-1][1]} times", file=sys.stderr)
    return picked


class Model:
    def __init__(self):
        import ctranslate2
        from sacremoses import MosesDetokenizer
        from subword_nmt.apply_bpe import BPE

        self.tr = ctranslate2.Translator(str(MODEL_DIR / "model"), device="cpu", inter_threads=1, intra_threads=2)
        self.detok = MosesDetokenizer("en")
        with open(MODEL_DIR / "bpe.model", encoding="utf-8") as f:
            self.bpe = BPE(f)

    def translate(self, texts, beam, label):
        cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
        todo = [t for t in dict.fromkeys(texts) if f"{beam}|{t}" not in cache]
        t0 = time.time()
        for i in range(0, len(todo), 128):
            chunk = todo[i : i + 128]
            batch = [self.bpe.segment_tokens(t.split()) for t in chunk]
            for t, r in zip(chunk, self.tr.translate_batch(batch, beam_size=beam, max_decoding_length=24)):
                cache[f"{beam}|{t}"] = self.detok.detokenize(" ".join(r.hypotheses[0]).replace("@@ ", "").split())
            if i % (128 * 40) == 0:
                print(f"  {label}: {i + len(chunk)}/{len(todo)} new, {time.time() - t0:.0f}s", file=sys.stderr)
        if todo:
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        return [cache[f"{beam}|{t}"] for t in texts]


def clean_output(src, out, max_words):
    out = out.strip(" .,!?¿¡;:")
    low = out.lower()
    if not out or low == src or low == norm(src) or len(out.split()) > max_words:
        return None
    if not re.fullmatch(r"[A-Za-z' ,-]+", out):
        return None
    return out if out == "I" or out.startswith(("I ", "I'")) else low


def write_lua(words, phrases):
    for old in OUT_DIR.glob("Dict*.lua"):
        old.unlink()
    entries = [("p", k, v) for k, v in sorted(phrases.items())] + [("w", k, v) for k, v in sorted(words.items())]
    with open(OUT_DIR / "Dict.lua", "w", encoding="utf-8") as f:
        f.write("-- Generated by build_dict.py. Keys are lowercase with accents removed (ñ kept).\n")
        f.write("local _, ns = ...\nns.words, ns.phrases = {}, {}\n")
        for start in range(0, len(entries), ENTRIES_PER_BLOCK):
            f.write("do\nlocal function load(w, p)\n")
            for table, k, v in entries[start : start + ENTRIES_PER_BLOCK]:
                f.write(f"{table}[{lua_str(k)}]={lua_str(v)}\n")
            f.write("end\nload(ns.words, ns.phrases)\nend\n")
    toc = OUT_DIR / "ChatTranslate.toc"
    header = [l for l in toc.read_text(encoding="utf-8").splitlines() if l.startswith("##")]
    toc.write_text("\n".join(header) + "\n\nDict.lua\nChatTranslate.lua\n", encoding="utf-8")
    return -(-len(entries) // ENTRIES_PER_BLOCK)


def main():
    try:
        os.nice(19)
    except OSError:
        pass
    t0 = time.time()
    words = load_words()
    ngrams = load_ngrams()
    model = Model()

    word_table = {}
    for w, out in zip(words, model.translate(words, 1, "words")):
        out = clean_output(w, out, 3)
        if out:
            word_table.setdefault(norm(w), out)
    for k, v in WORDS.items():
        word_table[norm(k)] = v

    phrase_table = {}
    for g, raw in zip(ngrams, model.translate(ngrams, 2, "phrases")):
        if NAMES & set(g.split()) or any(w[:1].isupper() and not w.startswith("I") for w in raw.split()[1:]):
            continue  # Tatoeba is full of "Tom" and "Mary"
        out = clean_output(g, raw, 2 * len(g.split()) + 1)
        if out and INVENTED_OBJECT.search(out) and not HAS_PRONOUN.search(g):
            continue
        literal = " ".join(word_table.get(norm(t), t) for t in g.split())
        if out and out != literal:  # skip phrases word-by-word already gets right
            phrase_table.setdefault(norm(g), out)
    for k, v in PHRASES.items():
        phrase_table[norm(k)] = v

    blocks = write_lua(word_table, phrase_table)
    print(f"{len(word_table)} words, {len(phrase_table)} phrases in {blocks} blocks, {time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
