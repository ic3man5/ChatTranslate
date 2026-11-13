# ChatTranslate

A World of Warcraft addon that adds an English translation after Spanish chat
messages. Everything runs inside the game with a built-in dictionary, so there's
nothing to set up and nothing is sent anywhere.

```
[Party Leader] [Arturo]: hay que pullear menos [we need to pull less]
[Party] [Lucía]: no lo se, preguntale al lider [I don't know, ask him to the leader]
```

Made for **WoW Forever** (interface 16001). English messages are left alone.

## Install

1. Download this repository (**Code → Download ZIP**) and unzip it.
2. Copy the `ChatTranslate` folder into `World of Warcraft/_forever_/Interface/AddOns/`.
3. Restart the game. WoW only notices new addons when it starts, so `/reload` isn't enough the first time.

You should see `ChatTranslate loaded` in chat after logging in.

## Use

Spanish messages in Say, Yell, Party, Raid, Instance, Guild, Officer, Whisper and
chat channels get an `[English]` translation in light blue after them.

| Command | |
|---|---|
| `/ct` | Show status and help |
| `/ct on`, `/ct off` | Turn translations on or off |
| `/ct <spanish text>` | Translate some text yourself |

## How good is it?

Addons can't use the internet or run a translation model, so ChatTranslate looks
words and phrases up in a dictionary of 32k words and 15.5k common phrases, then
fixes the most common grammar differences (negation, object pronouns, dropped
accents). You get the gist, but it's rougher than a real translator:

| Spanish | ChatTranslate | Full model |
|---|---|---|
| no entiendo nada | I don't understand anything | I don't understand anything. |
| el healer no me cura | the healer doesn't heal me | The healer doesn't cure me. |
| tenemos al hunter sin flechas | we have to the hunter without arrows | We have the hunter without arrows. |

It knows common chat slang (`q`, `xq`, `xfa`, `tmb`), Argentine voseo (`vos`,
`sos`, `tenés`, `volvé`) and gamer Spanglish (`pullear`, `lootear`, `farmear`).

## Better translations with the desktop tool (optional)

The addon also keeps the last 300 Spanish lines in its saved variables. WoW writes
those to disk when you `/reload` or log out, and `wow_translate.py` translates them
with the full offline model (OPUS-MT), which reads much more naturally. The log
stays on your computer.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p models
curl -L -o models/es_en.argosmodel https://argos-net.com/v1/translate-es_en-1_9.argosmodel   # ~285 MB
(cd models && python3 -m zipfile -e es_en.argosmodel . && rm es_en.argosmodel)
.venv/bin/python wow_translate.py
```

On Linux it finds the game from the running `Wow.exe`. Elsewhere, pass the file
with `--saved "<WoW>/_forever_/WTF/Account/<ACCOUNT>/SavedVariables/ChatTranslate.lua"`.

## Rebuilding the dictionary

`build_dict.py` regenerates `ChatTranslate/Dict.lua`. It needs the model (above)
and two data files:

```sh
mkdir -p data
curl -L -o data/es_50k.txt https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/es/es_50k.txt
curl -L -o data/spa_sentences.tsv.bz2 https://downloads.tatoeba.org/exports/per_language/spa/spa_sentences.tsv.bz2
.venv/bin/python build_dict.py
```

The first run takes about 5 minutes; model output is cached in `build_cache.json`,
so later runs take seconds. Hand-written fixes go in the `PHRASES` and `WORDS`
tables at the top of `build_dict.py` and override the model.

## License

The code is MIT licensed (see `LICENSE`). The generated dictionary,
`ChatTranslate/Dict.lua`, is CC BY-SA 4.0 because it's built from:

- [FrequencyWords](https://github.com/hermitdave/FrequencyWords) by Hermit Dave (OpenSubtitles word frequencies), CC BY-SA 4.0
- [Tatoeba](https://tatoeba.org) Spanish sentences, CC BY 2.0 FR
- [OPUS-MT](https://github.com/Helsinki-NLP/Opus-MT) Spanish-English model by Jörg Tiedemann and Santhosh Thottingal, packaged by [Argos Translate](https://github.com/argosopentech/argos-translate), CC BY 4.0

See `ChatTranslate/LICENSE-Dictionary.txt` for details.
