-- ChatTranslate: appends a rough English gloss to Spanish chat and logs those
-- lines to SavedVariables, where wow_translate.py picks them up after a /reload.

local _, ns = ...

local MAX_LOG = 300
local COLOR = "|cff8fd0ff"

local EVENTS = {
    CHAT_MSG_SAY = "Say", CHAT_MSG_YELL = "Yell", CHAT_MSG_EMOTE = "Emote",
    CHAT_MSG_PARTY = "Party", CHAT_MSG_PARTY_LEADER = "Party",
    CHAT_MSG_RAID = "Raid", CHAT_MSG_RAID_LEADER = "Raid", CHAT_MSG_RAID_WARNING = "Raid",
    CHAT_MSG_INSTANCE_CHAT = "Instance", CHAT_MSG_INSTANCE_CHAT_LEADER = "Instance",
    CHAT_MSG_GUILD = "Guild", CHAT_MSG_OFFICER = "Officer",
    CHAT_MSG_WHISPER = "Whisper", CHAT_MSG_CHANNEL = "Channel",
}

local function set(list)
    local s = {}
    for word in list:gmatch("%S+") do s[word] = true end
    return s
end

-- Common English and gaming words. They count against a line being Spanish even when
-- the Spanish dictionary happens to contain them too (come, can, red, has...).
local ENGLISH = set([[
    the and you is are to of for with i my it that this lfm lfg wts wtb lf have has was what who
    where how can anyone need just your be do don't dont im i'm on at or if get got will would
    like they we he she not all any so go come here there now one up out down in back pull wait
    okay yes yeah yep nope lol lmao rofl ty thx thanks np gg brb afk oom heal tank dps mob mobs
    boss run sorry sec plz nice good great bad too us our them their his her him did does done
    cant can't its it's about from but then than when why which some more much very really still
    again also only last first next time way give take make let lets let's know think want see
    look try use keep stop help kill die dead died man guys guy bro dude sure cool damn hey hi
    hello bye gl hf wp ez idk imo tbh omg wtf btw inv invite quest group dungeon gold silver
    sell buy trade please am was were been being an by off over under after before right left
    ready rdy omw ill i'll you're youre were we're thats that's what's whats
]])
-- Ambiguous between the two languages; ignored when deciding.
local NEUTRAL = set("a no me ok x pls o mana solo d k")

local ACCENTS = {
    ["\195\161"] = "a", ["\195\169"] = "e", ["\195\173"] = "i", ["\195\179"] = "o", ["\195\186"] = "u",
    ["\195\188"] = "u", ["\195\129"] = "a", ["\195\137"] = "e", ["\195\141"] = "i", ["\195\147"] = "o",
    ["\195\154"] = "u", ["\195\156"] = "u", ["\195\145"] = "\195\177",
}

local function norm(word)
    return (word:lower():gsub("\195[\128-\191]", ACCENTS))
end

local function isLaugh(n)
    return #n >= 4 and (n:match("^j[aj]+$") or n:match("^j[ej]+$")) ~= nil
end

local function tokenize(text)
    local items, pos = {}, 1
    while true do
        local s, e = text:find("[%w\128-\255']+", pos)
        if not s then return items, text:sub(pos) end
        local word = text:sub(s, e)
        items[#items + 1] = { sep = text:sub(pos, s - 1), word = word, norm = norm(word) }
        pos = e + 1
    end
end

local function looksSpanish(raw, items)
    if raw:find("\195\177") or raw:find("\195\145") or raw:find("\194\191") or raw:find("\194\161") then
        return true -- ñ Ñ ¿ ¡
    end
    local es, en, counted = 0, 0, 0
    for _, it in ipairs(items) do
        local n = it.norm
        if not (isLaugh(n) or NEUTRAL[n] or n:find("^%d+$")) then
            counted = counted + 1
            if ENGLISH[n] then
                en = en + 1
            elseif ns.words[n] or it.word:find("\195[\161\169\173\179\186]") then -- á é í ó ú
                es = es + 1
            end
        end
    end
    -- at least half the words Spanish, and clearly more Spanish than English
    return es >= 1 and es * 2 >= counted and es >= en * 2
end

-- Small grammar fixes applied after the dictionary lookup. Spanish puts object
-- pronouns before the verb and negates with a bare "no", and drops "qué"'s accent
-- in chat, so a word-for-word gloss gets these consistently wrong.
local SUBJECT = set("i you we they he she it")
local SUBJECT_WORD = { yo = "i", tu = "you", vos = "you", usted = "you", nosotros = "we", ellos = "they", ella = "she" }
local OBJECT = { me = "me", te = "you", nos = "us", le = "him", les = "them", lo = "it", la = "it", los = "them", las = "them" }
local ALWAYS_CLITIC = set("me te nos le les") -- the others double as articles
local REFLEXIVE = { me = "i", te = "you", nos = "we" } -- clitic is the verb's own subject: "nos perdimos"
local INDEFINITE = set("nobody someone anyone everyone everybody somebody")
local QUE = set("que q k ke")
local AUX = {}
for _, a in ipairs({ "I am", "you are", "we are", "they are", "is", "are", "I want", "you want", "do you want",
    "I can", "can you", "you can", "we can", "I need", "we need", "I'm going", "I'm going to", "let's",
    "I have to", "you have to", "we have to", "we need to" }) do
    AUX[a] = true
end
local NEGATIONS = { -- checked in order, so longer forms come first
    { "there is", "there isn't" }, { "I am", "I'm not" }, { "I'm", "I'm not" }, { "you are", "you're not" },
    { "we are", "we're not" }, { "they are", "they're not" }, { "it is", "it isn't" }, { "it's", "it's not" },
    { "is", "isn't" }, { "are", "aren't" }, { "I can", "I can't" }, { "you can", "you can't" },
    { "we can", "we can't" }, { "can you", "can't you" }, { "can", "can't" }, { "I will", "I won't" },
}

local function negate(text, afterNoun)
    if text:find("n't") or text:find("^not? ") or text:find("^never") then return text end
    for _, pair in ipairs(NEGATIONS) do
        local from = pair[1]
        if text == from or text:sub(1, #from + 1) == from .. " " then
            return pair[2] .. text:sub(#from + 1)
        end
    end
    local subj, rest = text:match("^(%S+) (.+)$")
    if subj and SUBJECT[subj:lower()] then
        return subj .. ((subj == "he" or subj == "she" or subj == "it") and " doesn't " or " don't ") .. rest
    end
    return (afterNoun and "doesn't " or "not ") .. text
end

-- Next chunk that has text, if only spaces separate it from chunk i.
local function nextChunk(out, i)
    for j = i + 1, #out do
        if not out[j].sep:find("^%s*$") then return nil end
        if out[j].text ~= "" then return j end
    end
end

local function prevChunk(out, i)
    for j = i - 1, 1, -1 do
        if out[j].text ~= "" then return j end
    end
end

local function firstWord(text)
    return (text:match("^(%S+)") or ""):lower()
end

-- True when chunk p ends a noun phrase like "the healer" or "nobody".
local function isNounPhrase(out, p)
    if not p then return false end
    if INDEFINITE[out[p].text] then return true end
    local before = prevChunk(out, p)
    return before ~= nil and out[before].text == "the"
end

local function fixGrammar(out)
    for i, c in ipairs(out) do -- "que" opening a sentence or question is "what"
        if c.single and QUE[c.norm] and (i == 1 or c.sep:find("[%?%.!\3]")) then c.text = "what" end
    end
    for i, c in ipairs(out) do -- "lo tengo" -> "I have it", "me ayudas" -> "help me"
        local obj = c.single and OBJECT[c.norm]
        local j = obj and nextChunk(out, i)
        if j and out[j].known and (ALWAYS_CLITIC[c.norm] or SUBJECT[firstWord(out[j].text)]) then
            if REFLEXIVE[c.norm] ~= firstWord(out[j].text) then
                local target = AUX[out[j].text] and nextChunk(out, j) or j
                out[target].text = out[target].text .. " " .. obj
            end
            c.text = ""
        end
    end
    for i, c in ipairs(out) do -- "no tengo" -> "I don't have"
        local j = c.single and c.norm == "no" and nextChunk(out, i)
        if j then
            out[j].text = negate(out[j].text, isNounPhrase(out, prevChunk(out, i)))
            c.text = ""
        end
    end
    for i, c in ipairs(out) do -- "yo tengo" -> "I have", not "I I have"
        local subj = firstWord(c.text)
        local p = SUBJECT[subj] and prevChunk(out, i)
        if p and out[p].single and (out[p].text:lower() == subj or SUBJECT_WORD[out[p].norm] == subj) then
            out[p].text = ""
        elseif p and firstWord(out[p].text) == subj and (out[p].text:find("n't$") or out[p].text:find(" not$")) then
            c.text = c.text:gsub("^%S+%s*", "") -- "I don't" + "I have" -> "I don't have"
        elseif p and (subj == "he" or subj == "she" or subj == "it") and isNounPhrase(out, p) then
            c.text = c.text:gsub("^%S+%s*", "") -- "nobody he told me" -> "nobody told me"
        end
    end
end

local function gloss(items, tail)
    local out, i, n = {}, 1, #items
    while i <= n do
        local matched = false
        for len = math.min(4, n - i + 1), 2, -1 do
            local key = items[i].norm
            for j = i + 1, i + len - 1 do key = key .. " " .. items[j].norm end
            local phrase = ns.phrases[key]
            if phrase then
                out[#out + 1] = { sep = items[i].sep, text = phrase, norm = key, single = false, known = true }
                i, matched = i + len, true
                break
            end
        end
        if not matched then
            local it = items[i]
            local word = ns.words[it.norm]
            if word == nil and isLaugh(it.norm) then word = "haha" end
            out[#out + 1] = { sep = it.sep, text = word or it.word, norm = it.norm, single = true, known = word ~= nil }
            i = i + 1
        end
    end
    fixGrammar(out)
    local parts = {}
    for _, c in ipairs(out) do parts[#parts + 1] = c.sep .. c.text end
    parts[#parts + 1] = tail
    local text = table.concat(parts):gsub("\3", ""):gsub("%s%s+", " "):gsub(" ([,%.!%?])", "%1")
    return (text:gsub("^%s+", ""):gsub("%s+$", ""))
end

-- Returns the English gloss, or nil when the message doesn't look Spanish.
local function translate(msg, force)
    local links = {}
    local function protect(link)
        links[#links + 1] = link
        return "\1" .. #links .. "\2"
    end
    local text = msg:gsub("|c%x%x%x%x%x%x%x%x|H.-|h.-|h|r", protect):gsub("|cn[^:]*:|H.-|h.-|h|r", protect)
    text = text:gsub("|H.-|h.-|h", protect)
    -- drop textures and ¡; ¿ becomes a marker so "qué" after it reads as a question
    text = text:gsub("|T.-|t", ""):gsub("\194\161", ""):gsub("\194\191", "\3")
    local items, tail = tokenize(text)
    if #items == 0 or not (force or looksSpanish(msg, items)) then return nil end
    -- placeholder digits were tokenized as words; put the links back afterwards
    local result = gloss(items, tail):gsub("\1(%d+)\2", function(i) return (links[tonumber(i)] or "") .. COLOR end)
    return result
end
ns.translate = translate

local function log(event, author, channelName, msg)
    local label = EVENTS[event]
    if event == "CHAT_MSG_CHANNEL" and channelName and channelName ~= "" then label = channelName end
    local entries = ChatTranslateLog
    entries[#entries + 1] = { time(), label, author or "", msg }
    while #entries > MAX_LOG do table.remove(entries, 1) end
end

local cache, cacheSize = {}, 0

local function filter(self, event, msg, author, ...)
    if not ChatTranslateSettings or not ChatTranslateSettings.enabled or type(msg) ~= "string" then
        return false
    end
    local lineID = select(9, ...) -- arg11; the filter runs once per chat window, so translate each line once
    local english = lineID and cache[lineID]
    if english == nil then
        local ok, result = pcall(translate, msg)
        english = ok and result or false
        if lineID then
            if cacheSize > 500 then cache, cacheSize = {}, 0 end
            cache[lineID], cacheSize = english, cacheSize + 1
        end
        if english then pcall(log, event, author, select(2, ...), msg) end
    end
    if english and english ~= "" then
        return false, msg .. " " .. COLOR .. "[" .. english .. "]|r", author, ...
    end
    return false
end

local addFilter = (ChatFrameUtil and ChatFrameUtil.AddMessageEventFilter) or ChatFrame_AddMessageEventFilter

local frame = CreateFrame("Frame")
frame:RegisterEvent("ADDON_LOADED")
frame:SetScript("OnEvent", function(self, _, name)
    if name ~= "ChatTranslate" then return end
    self:UnregisterEvent("ADDON_LOADED")
    ChatTranslateLog = ChatTranslateLog or {}
    ChatTranslateSettings = ChatTranslateSettings or { enabled = true }
    for event in pairs(EVENTS) do addFilter(event, filter) end
    local count = 0
    for _ in pairs(ns.words) do count = count + 1 end
    print(COLOR .. "ChatTranslate|r loaded (" .. count .. " words). Spanish chat gets an " .. COLOR
        .. "[English]|r translation. Type /ct for options.")
end)

SLASH_CHATTRANSLATE1 = "/ct"
SLASH_CHATTRANSLATE2 = "/chattranslate"
SlashCmdList.CHATTRANSLATE = function(input)
    input = (input or ""):gsub("^%s+", ""):gsub("%s+$", "")
    if input == "on" or input == "off" then
        ChatTranslateSettings.enabled = input == "on"
        print(COLOR .. "ChatTranslate|r " .. input)
    elseif input ~= "" then
        print(COLOR .. "ChatTranslate|r " .. (translate(input, true) or ""))
    else
        print(COLOR .. "ChatTranslate|r is " .. (ChatTranslateSettings.enabled and "on" or "off")
            .. ", " .. #ChatTranslateLog .. " lines logged.")
        print("  /ct on | off  - turn translations on or off")
        print("  /ct <text>    - translate some Spanish text")
    end
end
